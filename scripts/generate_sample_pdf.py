"""Generate a sample Python assignment PDF for testing."""

from pathlib import Path

import fitz

CONTENT = """
Python Assignment: Stack Implementation

Page 1 - Overview
================
Implement a Stack data structure in Python with the following methods:
- push(item): add item to top
- pop(): remove and return top item
- peek(): return top without removing
- is_empty(): return True if stack is empty

Page 2 - Requirements
=====================
Input Format:
- Commands come from stdin, one per line
- Commands: PUSH <value>, POP, PEEK, EMPTY

Output Format:
- POP prints the popped value or "Stack empty"
- PEEK prints the top value or "Stack empty"
- EMPTY prints "True" or "False"

Constraints:
- Use a list internally (do NOT use collections.deque for pop)
- Handle empty stack gracefully
- Maximum 10,000 operations

Page 3 - Starter Structure
==========================
Create a file main.py with:

class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        pass  # TODO

    def pop(self):
        pass  # TODO

Page 4 - Example
================
Input:
PUSH 5
PUSH 3
PEEK
POP
EMPTY

Expected Output:
3
3
False

Page 5 - Testing
================
Run tests with: pytest test_main.py
All tests must pass before submission.
"""

def main() -> None:
    out = Path(__file__).resolve().parent.parent / "sample_assignment.pdf"
    doc = fitz.open()
    sections = CONTENT.strip().split("\n\n")
    for section in sections:
        page = doc.new_page()
        page.insert_text((50, 50), section, fontsize=11)

    doc.save(out)
    doc.close()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
