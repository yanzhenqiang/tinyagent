# Calculator Project

A simple Python calculator library with basic arithmetic operations and comprehensive unit tests.

## Features

- **Addition**: Add two numbers
- **Subtraction**: Subtract one number from another
- **Multiplication**: Multiply two numbers
- **Division**: Divide one number by another (with zero-division protection)

## Project Structure

```
.
├── src/
│   └── calculator.py       # Main calculator implementation
├── tests/
│   └── test_calculator.py  # Unit tests
└── README.md               # Project documentation
```

## Installation

No external dependencies required. This project uses only Python standard library.

## Usage

```python
from src.calculator import Calculator

calc = Calculator()

# Addition
result = calc.add(5, 3)        # Returns: 8

# Subtraction
result = calc.subtract(5, 3)   # Returns: 2

# Multiplication
result = calc.multiply(5, 3)   # Returns: 15

# Division
result = calc.divide(15, 3)    # Returns: 5.0
```

## Running Tests

Run all tests using Python's built-in unittest:

```bash
python -m unittest tests/test_calculator.py
```

Or run with verbose output:

```bash
python -m unittest tests/test_calculator.py -v
```

## API Reference

### Calculator Class

#### `add(a: float, b: float) -> float`
Add two numbers and return the sum.

#### `subtract(a: float, b: float) -> float`
Subtract `b` from `a` and return the difference.

#### `multiply(a: float, b: float) -> float`
Multiply two numbers and return the product.

#### `divide(a: float, b: float) -> float`
Divide `a` by `b` and return the quotient.

**Raises:**
- `ZeroDivisionError`: If `b` is zero

## License

MIT License
