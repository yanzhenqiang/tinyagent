"""
Unit tests for the Calculator module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from calculator import Calculator


class TestCalculator(unittest.TestCase):
    """Test cases for the Calculator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.calc = Calculator()

    # ==================== Addition Tests ====================
    def test_add_positive_numbers(self):
        """Test adding two positive numbers."""
        result = self.calc.add(2, 3)
        self.assertEqual(result, 5)

    def test_add_negative_numbers(self):
        """Test adding two negative numbers."""
        result = self.calc.add(-2, -3)
        self.assertEqual(result, -5)

    def test_add_mixed_numbers(self):
        """Test adding positive and negative numbers."""
        result = self.calc.add(5, -3)
        self.assertEqual(result, 2)

    def test_add_floats(self):
        """Test adding floating point numbers."""
        result = self.calc.add(1.5, 2.5)
        self.assertEqual(result, 4.0)

    # ==================== Subtraction Tests ====================
    def test_subtract_positive_numbers(self):
        """Test subtracting two positive numbers."""
        result = self.calc.subtract(5, 3)
        self.assertEqual(result, 2)

    def test_subtract_negative_numbers(self):
        """Test subtracting with negative numbers."""
        result = self.calc.subtract(-2, -3)
        self.assertEqual(result, 1)

    def test_subtract_mixed_numbers(self):
        """Test subtracting positive and negative numbers."""
        result = self.calc.subtract(5, -3)
        self.assertEqual(result, 8)

    # ==================== Multiplication Tests ====================
    def test_multiply_positive_numbers(self):
        """Test multiplying two positive numbers."""
        result = self.calc.multiply(4, 3)
        self.assertEqual(result, 12)

    def test_multiply_negative_numbers(self):
        """Test multiplying two negative numbers."""
        result = self.calc.multiply(-4, -3)
        self.assertEqual(result, 12)

    def test_multiply_mixed_numbers(self):
        """Test multiplying positive and negative numbers."""
        result = self.calc.multiply(4, -3)
        self.assertEqual(result, -12)

    def test_multiply_by_zero(self):
        """Test multiplying by zero."""
        result = self.calc.multiply(5, 0)
        self.assertEqual(result, 0)

    # ==================== Division Tests ====================
    def test_divide_positive_numbers(self):
        """Test dividing two positive numbers."""
        result = self.calc.divide(12, 4)
        self.assertEqual(result, 3)

    def test_divide_negative_numbers(self):
        """Test dividing two negative numbers."""
        result = self.calc.divide(-12, -4)
        self.assertEqual(result, 3)

    def test_divide_mixed_numbers(self):
        """Test dividing positive and negative numbers."""
        result = self.calc.divide(12, -4)
        self.assertEqual(result, -3)

    def test_divide_by_zero(self):
        """Test dividing by zero raises ZeroDivisionError."""
        with self.assertRaises(ZeroDivisionError) as context:
            self.calc.divide(5, 0)
        self.assertEqual(str(context.exception), "Cannot divide by zero")

    def test_divide_floats(self):
        """Test dividing floating point numbers."""
        result = self.calc.divide(5.0, 2.0)
        self.assertEqual(result, 2.5)

    # ==================== Power Tests ====================
    def test_power_positive_integers(self):
        """Test power with positive integers."""
        result = self.calc.power(2, 3)
        self.assertEqual(result, 8)

    def test_power_zero_exponent(self):
        """Test power with zero exponent."""
        result = self.calc.power(5, 0)
        self.assertEqual(result, 1)

    def test_power_negative_exponent(self):
        """Test power with negative exponent."""
        result = self.calc.power(2, -2)
        self.assertEqual(result, 0.25)

    def test_power_fractional_exponent(self):
        """Test power with fractional exponent."""
        result = self.calc.power(4, 0.5)
        self.assertEqual(result, 2.0)

    def test_power_negative_base_even_exponent(self):
        """Test power with negative base and even exponent."""
        result = self.calc.power(-2, 4)
        self.assertEqual(result, 16)

    def test_power_negative_base_odd_exponent(self):
        """Test power with negative base and odd exponent."""
        result = self.calc.power(-2, 3)
        self.assertEqual(result, -8)

    # ==================== Square Root Tests ====================
    def test_sqrt_perfect_square(self):
        """Test square root of perfect square."""
        result = self.calc.sqrt(9)
        self.assertEqual(result, 3.0)

    def test_sqrt_zero(self):
        """Test square root of zero."""
        result = self.calc.sqrt(0)
        self.assertEqual(result, 0.0)

    def test_sqrt_non_perfect_square(self):
        """Test square root of non-perfect square."""
        result = self.calc.sqrt(2)
        self.assertAlmostEqual(result, 1.4142135623730951, places=10)

    def test_sqrt_decimal(self):
        """Test square root of decimal number."""
        result = self.calc.sqrt(0.25)
        self.assertEqual(result, 0.5)

    def test_sqrt_negative_number(self):
        """Test square root of negative number raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.calc.sqrt(-4)
        self.assertEqual(str(context.exception), "Cannot calculate square root of negative number")


if __name__ == '__main__':
    unittest.main()
