"""Offline tests for Nova's local tools."""

import re
import unittest

from gemini_agent.tools import (
    TOOL_DECLARATIONS,
    TOOL_HANDLERS,
    calculator,
    current_datetime,
)


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


class DateTimeToolTests(unittest.TestCase):
    def test_current_datetime_is_registered(self):
        self.assertIs(TOOL_HANDLERS["current_datetime"], current_datetime)
        self.assertEqual(TOOL_DECLARATIONS[1]["name"], "current_datetime")

    def test_current_datetime_has_iso_format(self):
        value = current_datetime()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
