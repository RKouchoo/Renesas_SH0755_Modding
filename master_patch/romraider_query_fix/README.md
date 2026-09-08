# RomRaider pending-selection repair

The September 8 capture had all 22 idle headings but no samples. RomRaider
polled only channels manually reselected after connection. Its pending query
queues applied removals after additions, losing selections during a
definition/profile reload. See [the connection audit](../LOGGER_CONNECTION_AUDIT.md).

`query-selection.patch` contains the minimal `QueryManagerImpl` change and
five JUnit regression cases. It is already applied to the local source at
`/Users/regan/Dev/RomRaider`. The staged `launch.sh` was left intact.
`ProfileReloadCheck.java` independently reads the real definition and both
profiles, replays queued selection/reload events, and calls RomRaider's A8
builder without starting a query thread or opening a serial port.

## Installed files

- Normal JAR: `/Users/regan/Dev/RomRaider/build/linux/lib/RomRaider.jar`
- Original backup: `/Users/regan/Dev/RomRaider/build/backups/RomRaider-before-query-fix-20260908.jar`
- Original SHA-256: `4b27634a54a7b03c934cfa73886e4ce1b37fcfc737d1bba01d069bbc5ddeb882`
- Repaired SHA-256: `c6037c007d4d1e5652d2df1b554b2943f76522a057653462c32447f0d4107aba`

Only `com/romraider/logger/ecu/comms/manager/QueryManagerImpl.class` differs
inside the JAR. It was compiled with the installed Zulu Java 8 JDK, source
and target 1.6, against the existing application and dependencies. The
candidate passed the tests before atomically replacing the normal JAR.
No running application was restarted, no serial connection was opened and
no ECU command was sent by these checks.

Fully quit RomRaider and reopen it with the usual launcher to load the fix.
Load `D2WD610H_idle_diagnostic_profile.xml` and verify actual CSV rows with
ignition on and engine off before the next engine capture. The ROM BIN and
adapter firmware are unchanged.

## Repeat the offline checks

Run from `/Users/regan/Dev/RomRaider`; `rr_check` names a new temporary build
directory. The `Settings` constructor reads screen dimensions, so this test
uses the desktop Java runtime without `-Djava.awt.headless=true`. It creates
no window and substitutes fresh settings without loading/saving user settings.

```sh
rr_jdk=/Library/Java/JavaVirtualMachines/zulu-8.jdk/Contents/Home
rr_check=$(mktemp -d /tmp/romraider-query-check.XXXXXX)
rr_audit=/Users/regan/Dev/Renesas_SH0755_modding/master_patch
"$rr_jdk/bin/javac" -source 1.6 -target 1.6 \
  -cp 'build/linux/lib/RomRaider.jar:lib/common/*:lib/testing/*' \
  -d "$rr_check" \
  src/test/java/com/romraider/logger/ecu/comms/manager/QueryManagerImplTest.java \
  "$rr_audit/romraider_query_fix/ProfileReloadCheck.java"
"$rr_jdk/bin/java" \
  -cp "$rr_check:build/linux/lib/RomRaider.jar:lib/common/*:lib/testing/*" \
  org.junit.runner.JUnitCore \
  com.romraider.logger.ecu.comms.manager.QueryManagerImplTest
"$rr_jdk/bin/java" \
  -cp "$rr_check:build/linux/lib/RomRaider.jar:lib/common/*" \
  ProfileReloadCheck "$rr_audit/D2WD610H_master_logger.xml" \
  "$rr_audit/D2WD610H_idle_diagnostic_profile.xml" \
  "$rr_audit/D2WD610H_afterstart_diagnostic_profile.xml"
```

Expected: five tests pass; 22/17 channels survive reload, each producing a
43-address, 136-byte request with a valid checksum. The same JUnit tests on
the original backup fail three lost-selection cases. These checks do not by
themselves establish an ECU connection or complete live capture.

The subsequent 12:36 user retest confirms the repaired idle profile on the
live link: all 22 channels populate 1,786 CSV rows, and the full 43-address
request receives valid complete responses. The separate after-start profile
has not been validated in a live capture. See the
[September 8 log review](../../logs/20260908_idle_review.md).

The same `ProfileReloadCheck` also passes for
`D2WD610H_idle_recovery_profile.xml`: 19 channels, 38 view subscriptions,
43 addresses and a checksum-valid 136-byte request. Pass that profile as an
additional argument to the command above. Its direct transient/base-factor
capture is not yet live-validated; see [the recovery audit](../IDLE_RECOVERY_AUDIT.md).
