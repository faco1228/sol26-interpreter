"""
This module defines the ErrorCode enum, which contains all the error codes specified by
the project assignment.

IPP: You should not need to modify this file. However, you may add additional helper methods
     to the ErrorCode class.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
"""

import sys
from enum import IntEnum
from typing import NoReturn


class ErrorCode(IntEnum):
    """Error codes for the interpreter, used as program exit codes."""

    # General errors (10–19 + 99)
    GENERAL_OPTIONS = 10  # missing required CLI parameter or forbidden parameter combination
    GENERAL_INPUT = 11  # error opening input files (nonexistent, insufficient permissions, etc.)
    GENERAL_OTHER = 99  # unexpected internal error (uncategorized)

    # Interpreter / XML errors
    INT_XML = 20  # invalid XML input (not well-formed / cannot be parsed)
    INT_STRUCTURE = 42  # unexpected XML structure (nesting, missing required attrs, etc.)

    # Static semantic errors
    SEM_MAIN = 31  # missing Main class or its instance method run
    SEM_UNDEF = 32  # use of undefined/uninitialized variable/parameter/class/method
    SEM_ARITY = 33  # arity error for block assigned to selector in method definition
    SEM_COLLISION = 34  # assignment to a block's formal parameter (on LHS of assignment)
    SEM_ERROR = 35  # other static semantic error (e.g., class redefinition, name collisions)

    # Runtime interpreter errors
    INT_DNU = 51  # receiver does not understand the message (excluding instance-attr creation)
    INT_OTHER = 52  # other runtime errors (e.g., wrong operand types)
    INT_INVALID_ARG = 53  # invalid argument value (e.g., division by zero)
    INT_INST_ATTR = 54  # attempt to create instance attribute colliding with a method

    def fire(self, message: str | None = None) -> NoReturn:
        """Prints the error message (if specified) and exits with the appropriate code."""
        if message:
            print(f"Error {self.value}: {message}", file=sys.stderr)
        else:
            print(f"Error {self.value} ({self.name})", file=sys.stderr)
        exit(self.value)
