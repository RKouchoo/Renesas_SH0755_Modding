#!/usr/bin/env python3
"""Record bounded, offline fixture coverage for the documentation audit.

This observes the existing verifier; it does not model ECU timing or turn a
stubbed peripheral access into proof of physical output behavior.
"""
from __future__ import annotations

from collections import defaultdict
from functools import wraps
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import verify_master_patch as verifier  # noqa: E402
from test_hook_execution import Machine  # noqa: E402


def main():
    current_test = ["verifier"]
    accesses = defaultdict(lambda: {"pcs": set(), "tests": set()})
    visited = defaultdict(set)
    image_hashes = {}
    images = {}
    original_run = unittest.TestCase.run

    def run_test(self, result=None):
        previous = current_test[0]
        current_test[0] = self.id()
        try:
            return original_run(self, result)
        finally:
            current_test[0] = previous

    unittest.TestCase.run = run_test

    def image_key(machine):
        image = getattr(machine, "image", None)
        if not isinstance(image, bytes):
            return "component_or_mutable_fixture"
        identity = id(image)
        if identity not in image_hashes:
            digest = hashlib.sha256(image).hexdigest()
            image_hashes[identity] = digest
            images[identity] = image  # Prevent id reuse during this run.
        return image_hashes[identity]

    def wrap_step(original):
        @wraps(original)
        def step(self, *args, **kwargs):
            stack = getattr(self, "_audit_step_stack", None)
            if stack is None:
                self._audit_step_stack = stack = []
            stack.append(self.pc)
            visited[image_key(self)].add(self.pc)
            try:
                return original(self, *args, **kwargs)
            finally:
                stack.pop()
        return step

    def wrap_access(original, operation):
        @wraps(original)
        def access(self, address, *args, **kwargs):
            stack = getattr(self, "_audit_step_stack", ())
            depth = getattr(self, "_audit_access_depth", 0)
            self._audit_access_depth = depth + 1
            try:
                result = original(self, address, *args, **kwargs)
                if stack and not depth and 0xFFFF6000 <= address <= 0xFFFFFFFF:
                    size = (args[0] if args else kwargs["size"]) if operation == "read" else (
                        args[1] if len(args) > 1 else kwargs.get("size", 4))
                    record = accesses[(image_key(self), address, size, operation)]
                    record["pcs"].add(stack[-1])
                    record["tests"].add(current_test[0])
                return result
            finally:
                self._audit_access_depth = depth
        return access

    def descendants(cls):
        yield cls
        for child in cls.__subclasses__():
            yield from descendants(child)

    for cls in set(descendants(Machine)):
        for method in ("step", "read", "write"):
            if method in cls.__dict__:
                original = cls.__dict__[method]
                setattr(cls, method, wrap_step(original) if method == "step" else
                        wrap_access(original, method))

    verifier.main()
    destination = ROOT / "docs/reference/evidence/fixture_accesses.json"
    destination.write_text(json.dumps({
        "command": "python3 -B tools/trace_audit_fixtures.py",
        "limits": [
            "Only the existing offline fixtures and supplied inputs are covered.",
            "Coverage includes negative controls; image hashes separate immutable variants.",
            "A visited PC can be intercepted by a fixture; this is not an instruction-retirement trace.",
            "Accesses made by simulated callees are included; initial setup outside step is excluded.",
            "No physical sensor, scheduler latency, injector on-time or full ECU execution is measured.",
        ],
        "visited_pcs": {image: [f"{pc:08X}" for pc in sorted(pcs)]
                        for image, pcs in sorted(visited.items())},
        "accesses": [{"image": key[0], "address": f"{key[1]:08X}",
                      "size": key[2], "operation": key[3],
                      "pcs": [f"{pc:08X}" for pc in sorted(value["pcs"])],
                      "tests": sorted(value["tests"])}
                     for key, value in sorted(accesses.items())],
    }, indent=2) + "\n")
    print(f"Documentation fixture evidence: {len(accesses)} access groups -> {destination}")


if __name__ == "__main__":
    main()
