"""Value semantics for the independent instruction-test interpreter.

SH-2E always truncates toward zero, flushes denormals, and saturates finite
overflow. FMAC performs a rounded multiply followed by a rounded add.
Source: Renesas SH-2E Software Manual REJ09B0316-0200, sections 4.2--4.4,
7.3.3, and 7.3.9: https://www.renesas.com/en/document/mah/sh-2e-software-manual

This models values with invalid/divide-by-zero exceptions disabled. FPSCR
flags, exception delivery, and NaN payload propagation are not emulated.
Fixtures/ROM constants still use normal host binary32 encoding; only actual
instruction arithmetic uses these functions. Exact rational arithmetic avoids
host double-rounding errors, including cancellation with very small operands.
"""
from fractions import Fraction
import math
import struct

SIGN = 0x80000000
INF = 0x7F800000
MAX_FINITE = 0x7F7FFFFF
QNAN = 0x7FBFFFFF  # SH-2E quiet NaN has fraction bit 22 CLEAR.


def value(word):
    if word & 0x7F800000 == 0:
        word &= SIGN
    return struct.unpack(">f", struct.pack(">I", word))[0]


def rational_bits(exact, negative_zero=False):
    """Truncate an exact finite value into SH-2E's normal-or-zero format."""
    exact = Fraction(exact)
    if not exact:
        return SIGN if negative_zero else 0
    sign = SIGN if exact < 0 else 0
    n, d = abs(exact.numerator), exact.denominator
    exponent = n.bit_length() - d.bit_length()
    below_power = n < (d << exponent) if exponent >= 0 else (n << -exponent) < d
    if below_power:
        exponent -= 1
    if exponent < -126:
        return sign
    if exponent > 127:
        return sign | MAX_FINITE
    shift = 23 - exponent
    significand = (n << shift) // d if shift >= 0 else n // (d << -shift)
    return sign | ((exponent + 127) << 23) | (significand - (1 << 23))


def binary(op, left_word, right_word):
    """FADD/FSUB/FMUL/FDIV, with operands in mathematical left/right order."""
    left, right = value(left_word), value(right_word)
    if math.isnan(left) or math.isnan(right):
        return QNAN
    if op == "sub":
        return binary("add", left_word, right_word ^ SIGN)
    if op == "add":
        if math.isinf(left) or math.isinf(right):
            total = left + right
            if math.isnan(total):
                return QNAN
            return (SIGN if total < 0 else 0) | INF
        return rational_bits(Fraction(left) + Fraction(right),
                             bool(left_word & right_word & SIGN))
    sign = (left_word ^ right_word) & SIGN
    if op == "mul":
        if math.isinf(left) or math.isinf(right):
            return QNAN if left == 0 or right == 0 else sign | INF
        return rational_bits(Fraction(left) * Fraction(right), bool(sign))
    assert op == "div", op
    if (left == 0 and right == 0) or (math.isinf(left) and math.isinf(right)):
        return QNAN
    if right == 0 or math.isinf(left):
        return sign | INF
    if math.isinf(right):
        return sign
    return rational_bits(Fraction(left) / Fraction(right), bool(sign))


def multiply_accumulate(fr0, frm, frn):
    return binary("add", binary("mul", fr0, frm), frn)


def negate(word):
    if math.isnan(value(word)):
        return QNAN
    return (word & SIGN) ^ SIGN if word & 0x7F800000 == 0 else word ^ SIGN


def compare(op, left_word, right_word):
    left, right = value(left_word), value(right_word)
    return left == right if op == "eq" else left > right
