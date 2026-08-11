class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if self.is_empty():
            raise IndexError("Stack empty")
        return self._items.pop()

    def peek(self):
        if self.is_empty():
            raise IndexError("Stack empty")
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0


def main():
    stack = Stack()
    for line in __import__("sys").stdin:
        parts = line.strip().split()
        if not parts:
            continue
        cmd = parts[0].upper()
        if cmd == "PUSH":
            stack.push(int(parts[1]))
        elif cmd == "POP":
            try:
                print(stack.pop())
            except IndexError:
                print("Stack empty")
        elif cmd == "PEEK":
            try:
                print(stack.peek())
            except IndexError:
                print("Stack empty")
        elif cmd == "EMPTY":
            print(str(stack.is_empty()))


if __name__ == "__main__":
    main()
