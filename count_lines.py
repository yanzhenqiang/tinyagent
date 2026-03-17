#!/usr/bin/env python3
from pathlib import Path

py_lines = other_lines = 0
for p in Path(".").rglob("*"):
    if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
        lines = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        if p.suffix == ".py":
            py_lines += lines
        else:
            other_lines += lines
print(f"Python: {py_lines}")
print(f"Other:  {other_lines}")
print(f"Total:  {py_lines + other_lines}")
