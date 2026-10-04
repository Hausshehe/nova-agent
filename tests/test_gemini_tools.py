"""Offline tests for Nova's local tools."""

import unittest

from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS, calculator


class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(calculator("12 * (3 + 4)"), "84")

    def test_decimal_arithmetic(self):
        self.assertEqual(calculator("10 / 4"), "2.5")

    def test_rejects_python(self):
        with self.assertRaises(ValueError):
            calculator("__import__('os').getcwd()")

    def test_calculator_is_registered(self):
        self.assertIs(TOOL_HANDLERS["calculator"], calculator)
        self.assertEqual(TOOL_DECLARATIONS[0]["name"], "calculator")


if __name__ == "__main__":
    unittest.main()
