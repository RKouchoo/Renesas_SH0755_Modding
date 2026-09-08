"""Independent value vectors and exact bounding checks for the test FPU."""
from fractions import Fraction
from io import StringIO
import random
import unittest

import sh2e_test_fpu as fpu
from test_hook_execution import Machine, bits, number


class FpuTests(unittest.TestCase):
    def instruction(self, opcode, registers, expected, destination=2):
        cpu = Machine()
        cpu.write(cpu.pc, opcode, 2)
        for index, value in registers.items():
            cpu.fr[index] = value
        cpu.step()
        self.assertEqual(cpu.fr[destination], expected)
        return cpu

    def test_manual_division_and_rounding_vectors(self):
        # Manual section 7.3.4: FR5=4 / FR6=3 -> 3FAAAAAA, not 3FAAAAAB.
        self.instruction(0xF563, {5: 0x40800000, 6: 0x40400000}, 0x3FAAAAAA, 5)
        self.instruction(0xF230, {2: 0x3F800000, 3: bits(3 * 2**-25)}, 0x3F800000)
        self.instruction(0xF230, {2: 0xBF800000, 3: bits(-3 * 2**-25)}, 0xBF800000)
        self.instruction(0xF231, {2: 0x3F800000, 3: bits(2**-100)}, 0x3F7FFFFF)
        self.assertNotEqual(bits(1 + 3 * 2**-25), 0x3F800000)  # Old nearest model fails.

    def test_fmac_rounds_twice_and_handles_destination_alias(self):
        self.instruction(0xF23E, {0: 0x3F800001, 3: 0x3F7FFFFE, 2: 0xBF800000}, 0xB3800000)
        # Manual example: FMAC FR0,FR5,FR0 with 2 and 5 returns 12 in FR0.
        self.instruction(0xF05E, {0: bits(2), 5: bits(5)}, bits(12), 0)

    def test_underflow_overflow_and_subnormal_sources(self):
        self.instruction(0xF232, {2: 0x7F7FFFFF, 3: bits(2)}, 0x7F7FFFFF)
        self.instruction(0xF232, {2: 0xFF7FFFFF, 3: bits(2)}, 0xFF7FFFFF)
        self.instruction(0xF232, {2: 0x80800000, 3: bits(.5)}, 0x80000000)
        self.instruction(0xF232, {2: 1, 3: bits(2**126)}, 0)
        self.instruction(0xF23C, {3: 1}, 1)  # FMOV copies subnormal bits unchanged.
        cpu = self.instruction(0xF234, {2: 0, 3: 1}, 0)
        self.assertTrue(cpu.t)

    def test_special_values_with_exceptions_disabled(self):
        for opcode, left, right, result in (
            (0xF233, bits(1), 0x80000000, 0xFF800000),
            (0xF233, 0, 0, fpu.QNAN),
            (0xF232, 0, 0x7F800000, fpu.QNAN),
            (0xF230, 0x7F800000, 0xFF800000, fpu.QNAN),
            (0xF230, 0x80000000, 0x80000000, 0x80000000),
            (0xF231, bits(1), bits(1), 0),
            (0xF232, 0x7FC00001, bits(1), fpu.QNAN),
            (0xF232, 0x7F800001, bits(1), fpu.QNAN),
        ):
            self.instruction(opcode, {2: left, 3: right}, result)
        self.assertEqual(fpu.QNAN & 0x00400000, 0)
        self.assertFalse(fpu.compare("eq", fpu.QNAN, fpu.QNAN))

    def test_exact_arithmetic_is_adjacent_toward_zero(self):
        rng = random.Random(0x7055)
        for _ in range(600):
            words = [rng.randrange(0x00800000, 0x7F800000) | (rng.randrange(2) << 31) for _ in range(2)]
            a, b = map(lambda w: Fraction(number(w)), words)
            for op, exact in (("add", a + b), ("sub", a - b), ("mul", a * b), ("div", a / b)):
                result = fpu.binary(op, *words)
                magnitude = result & 0x7FFFFFFF
                rounded = abs(Fraction(number(result)))
                self.assertLessEqual(rounded, abs(exact))
                if magnitude == 0:
                    self.assertLess(abs(exact), Fraction(2)**-126)
                elif magnitude < 0x7F7FFFFF:
                    self.assertLess(abs(exact), Fraction(number(magnitude + 1)))
                self.assertEqual(bool(result & fpu.SIGN), exact < 0)


def verify_execution():
    report = StringIO()
    result = unittest.TextTestRunner(stream=report).run(unittest.defaultTestLoader.loadTestsFromTestCase(FpuTests))
    if not result.wasSuccessful():
        raise SystemExit(report.getvalue())
    print(f"  SH-2E FPU: {result.testsRun} execution/value test groups passed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
