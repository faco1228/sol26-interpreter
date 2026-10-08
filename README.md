# SOL26 interpreter

An interpreter for **SOL26** — a small Smalltalk-like, class-based object-oriented teaching
language — written in Python. It loads a program in the SOL-XML representation and executes it.
Built for the IPP course (Principles of Programming Languages) at BUT FIT.

**Stack:** Python 3.14 · Docker

## What it does

The interpreter takes a SOL program (as SOL-XML), builds an object model of its classes, methods
and blocks, and runs it with full OOP semantics: message passing, user-defined classes and
inheritance, built-in classes, blocks/closures, and the language's runtime error model (each
error maps to a defined exit code).

The `tester/sol2xml/` helper converts SOL source code into the SOL-XML the interpreter consumes,
so programs can be run end to end.

## Layout

```
int/
  src/
    solint.py                # entry point (course-provided skeleton)
    interpreter/             # the interpreter engine — my implementation
      interpreter.py         #   object model, message dispatch, execution
      input_model.py         #   SOL-XML parsing into the internal model
      error_codes.py         #   exit-code mapping
      exceptions.py          #   runtime error types
tester/
  sol2xml/                   # SOL source -> SOL-XML converter
Containerfile                # containerised build / check / test targets
Makefile                     # build, test and packaging targets
tests/                       # interpreter test cases (basic, errors, combined)
```

## Build & run

With Docker (recommended):

```bash
make build # build the interpreter image
```

Or run the interpreter directly on a SOL-XML file:

```bash
cd int/src
python3 solint.py --source program.xml --input program.in
```

See `int/pyproject.toml` for the Python dependencies.

## Note

`solint.py` and parts of the scaffolding are provided by the course; the interpreter engine under
`int/src/interpreter/` is my own work. 
Documentation is in `dokumentacia/dokumentace.pdf`.
