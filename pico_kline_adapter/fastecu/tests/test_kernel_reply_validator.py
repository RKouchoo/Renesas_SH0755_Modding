#!/usr/bin/env python3
"""Compile and exercise the actual FastECU K-line helpers without ECU access.

Uses the sibling FastECU checkout by default. Requires macOS clang++ and QtCore
from Homebrew qtbase. Compiles a temporary fixture executable from stdin; it
does not build FastECU, load its UI, or access USB/serial devices.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


CPP_PREFIX = r"""
#include <cstddef>
#include <cstdint>
#include <cassert>
#include <vector>
#include <QtCore/QByteArray>
#include <QtCore/QString>
#include <QtCore/QFileInfo>
#include "kernelcomms.h"
"""

CPP_TESTS = r"""
std::vector<uint8_t> frame(std::initializer_list<uint8_t> payload) {
    std::vector<uint8_t> data = {0xbe,0xef,uint8_t(payload.size()>>8),uint8_t(payload.size())};
    data.insert(data.end(), payload);
    uint8_t sum=0; for(auto b:data) sum=uint8_t(sum+b);
    data.push_back(sum); return data;
}
QByteArray idFrame(const QByteArray &identity) {
    QByteArray data;
    data.append(char(0xbe)); data.append(char(0xef));
    data.append(char((identity.size()+1)>>8)); data.append(char(identity.size()+1));
    data.append(char(0x41)); data.append(identity);
    uint8_t sum=0; for(auto b:data) sum=uint8_t(sum+uint8_t(b));
    data.append(char(sum)); return data;
}
int main() {
    auto ack=frame({0x61});
    assert(checkKernelFrame(ack.data(),ack.size(),0x21,0)==KernelFrameStatus::Valid);
    auto crc=frame({0x42,0x12,0x34,0x56,0x78});
    assert(checkKernelFrame(crc.data(),crc.size(),0x02,4)==KernelFrameStatus::Valid);
    auto volts=frame({0x44,0x02,0x30,0x02,0x30});
    assert(checkKernelFrame(volts.data(),volts.size(),0x04,4)==KernelFrameStatus::Valid);
    auto nrc=frame({0x7f,0x21,0x06});
    assert(checkKernelFrame(nrc.data(),nrc.size(),0x21,0)==KernelFrameStatus::Negative);
    assert(checkKernelFrame(nullptr,0,0x21,0)==KernelFrameStatus::Short);
    auto bad=ack; bad[0]=0;
    assert(checkKernelFrame(bad.data(),bad.size(),0x21,0)==KernelFrameStatus::Header);
    bad=crc; bad.pop_back();
    assert(checkKernelFrame(bad.data(),bad.size(),0x02,4)==KernelFrameStatus::Length);
    bad=crc; bad.push_back(0);
    assert(checkKernelFrame(bad.data(),bad.size(),0x02,4)==KernelFrameStatus::Length);
    bad=ack; bad.back()^=1;
    assert(checkKernelFrame(bad.data(),bad.size(),0x21,0)==KernelFrameStatus::Checksum);
    assert(checkKernelFrame(ack.data(),ack.size(),0x20,0)==KernelFrameStatus::Command);
    assert(checkKernelFrame(crc.data(),crc.size(),0x02,2)==KernelFrameStatus::Payload);
    QByteArray qack(reinterpret_cast<const char*>(ack.data()),ack.size());
    assert(kernelReplyError(qack,0x21,0).isEmpty());
    QByteArray qnrc(reinterpret_cast<const char*>(nrc.data()),nrc.size());
    assert(kernelReplyError(qnrc,0x21,0).contains("flash initialization failed"));
    assert(kernelReplyError(qnrc,0x21,0).contains("0x06"));

    const QString dedicated="/tmp/ssmk_kline_sh7055_180_d2wd.bin";
    const QString generic="/tmp/ssmk_kline_sh7055.bin";
    assert(isDedicatedD2wdKernel(dedicated));
    assert(!isDedicatedD2wdKernel(generic));
    static const char expected[]="FastECU SH7055 180nm D2WD610H K-Line v1.01";
    const QByteArray exact(expected,sizeof(expected));
    assert(exact.size()==43);
    assert(idFrame(exact).size()==49);
    assert(kernelIdentityError(idFrame(exact),dedicated).isEmpty());
    assert(!kernelIdentityError(idFrame(exact.left(exact.size()-1)),dedicated).isEmpty());
    QByteArray doubled=exact; doubled.append('\0');
    assert(!kernelIdentityError(idFrame(doubled),dedicated).isEmpty());
    const auto oldId=idFrame(QByteArray("FastECU Subaru SH7055 K-Line Kernel v1.00"));
    assert(!kernelIdentityError(oldId,dedicated).isEmpty());
    assert(kernelIdentityError(oldId,generic).isEmpty());
    auto damaged=idFrame(exact); damaged[damaged.size()-1]=char(damaged.back()^1);
    assert(!kernelIdentityError(damaged,dedicated).isEmpty());
    assert(!kernelIdentityError(QByteArray(),dedicated).isEmpty());

    // Cover every input alignment, high-bit bytes, and multiple complete words.
    for(int size=0;size<=65;++size) {
        QByteArray input;
        for(int i=0;i<size;++i) input.append(char((i*157+129)&255));
        auto payload=prepareKernelUpload(input);
        assert(payload.size()==((size+2+3)&~3));
        assert(payload.left(size)==input);
        uint16_t sum=0;
        for(int i=0;i<payload.size();i+=4) {
            const uint32_t word=(uint32_t(uint8_t(payload[i]))<<24) |
                                (uint32_t(uint8_t(payload[i+1]))<<16) |
                                (uint32_t(uint8_t(payload[i+2]))<<8) |
                                uint32_t(uint8_t(payload[i+3]));
            sum=uint16_t(sum+word);
        }
        assert(sum==0x5aa5);
    }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=Path(__file__).resolve().parents[4] / "FastECU",
        help="FastECU checkout containing the reviewed helpers",
    )
    parser.add_argument("--qt-prefix", type=Path, help="Homebrew qtbase prefix")
    args = parser.parse_args()
    compiler = shutil.which("clang++")
    if compiler is None:
        parser.error("clang++ is required")
    qt_prefix = args.qt_prefix
    if qt_prefix is None:
        qt_prefix = Path(subprocess.check_output(
            ["brew", "--prefix", "qtbase"], text=True
        ).strip())
    source_file = args.source_dir / "modules/ecu/flash_ecu_subaru_denso_sh705x_kline.cpp"
    source = source_file.read_text()
    match = re.search(r"^namespace \{\n.*?^\} // namespace$", source, re.M | re.S)
    if match is None or "kernelIdentityError" not in match.group(0):
        parser.error("reviewed K-line helper namespace was not found")
    with tempfile.TemporaryDirectory(prefix="fastecu-kline-test-") as build_dir:
        executable = Path(build_dir) / "kernel_reply_test"
        subprocess.run(
            [compiler, "-std=c++17", "-F" + str(qt_prefix / "lib"),
             "-framework", "QtCore", "-I" + str(args.source_dir),
             "-x", "c++", "-", "-o", str(executable)],
            input=CPP_PREFIX + match.group(0) + CPP_TESTS, text=True, check=True,
        )
        subprocess.run([str(executable)], check=True)
    print("PASS: actual reply validator, error formatter, dedicated kernel identity, "
          "and upload alignment/checksum fixtures; no ECU I/O.")


if __name__ == "__main__":
    main()
