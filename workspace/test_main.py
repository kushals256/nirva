import pytest
from main import Stack


def test_push_pop():
    s = Stack()
    s.push(1)
    s.push(2)
    assert s.pop() == 2
    assert s.pop() == 1


def test_peek():
    s = Stack()
    s.push(5)
    assert s.peek() == 5
    assert not s.is_empty()


def test_empty():
    s = Stack()
    assert s.is_empty()
    s.push(1)
    assert not s.is_empty()
