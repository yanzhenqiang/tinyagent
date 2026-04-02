"""
Calculator module with basic arithmetic operations.
"""

import math


class Calculator:
    """A simple calculator class with basic arithmetic operations."""

    def add(self, a: float, b: float) -> float:
        """Add two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of a and b
        """
        return a + b

    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Difference of a and b
        """
        return a - b

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Product of a and b
        """
        return a * b

    def divide(self, a: float, b: float) -> float:
        """Divide a by b.
        
        Args:
            a: First number (dividend)
            b: Second number (divisor)
            
        Returns:
            Quotient of a and b
            
        Raises:
            ZeroDivisionError: If b is zero
        """
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return a / b

    def power(self, base: float, exponent: float) -> float:
        """Calculate base raised to the power of exponent.
        
        Args:
            base: The base number
            exponent: The exponent
            
        Returns:
            base raised to the power of exponent
            
        Examples:
            >>> calc.power(2, 3)
            8.0
            >>> calc.power(4, 0.5)
            2.0
        """
        return base ** exponent

    def sqrt(self, a: float) -> float:
        """Calculate the square root of a number.
        
        Args:
            a: The number to calculate square root of
            
        Returns:
            Square root of a
            
        Raises:
            ValueError: If a is negative
            
        Examples:
            >>> calc.sqrt(9)
            3.0
            >>> calc.sqrt(2)
            1.4142135623730951
        """
        if a < 0:
            raise ValueError("Cannot calculate square root of negative number")
        return math.sqrt(a)
