#!/usr/bin/env python3
"""
This script serves as the main entry point for the SOL26 interpreter.

IPP: You should not need to modify this file.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
"""

import argparse
import logging
import sys
from io import StringIO
from pathlib import Path

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.interpreter import Interpreter


def main() -> None:
    """
    The main entry point for the SOL26 interpreter. It parses command-line arguments, and uses
    the Interpreter class to load and execute the specified program in the SOL-XML format.

    IPP: Do not modify this function, except for adding additional CLI arguments if you wish.
    """

    # Set up logging
    # IPP: You do not have to use logging – but it is the recommended practice.
    # See this for more information: https://docs.python.org/3/howto/logging.html
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s [%(name)s][%(filename)s:%(lineno)d] %(message)s",
    )
    logger = logging.getLogger("main")

    # Define the CLI arguments
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "-s",
        "--source",
        type=Path,
        required=True,
        help="Path to the SOL-XML source file to be interpreted.",
    )
    arg_parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=False,
        help="Path to a file that will be used as the standard input "
        "for the interpreted program (optional).",
    )
    arg_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Enable verbose logging output (using once = INFO level, using twice = DEBUG level).",
    )

    # Parse the provided arguments
    # Note: argparse will automatically print an error message and try to exit if parsing fails,
    # but we want to exit with our custom error code so we catch the SystemExit exception that
    # argparse raises and fire our error code instead.
    try:
        args = arg_parser.parse_args()
    except SystemExit:
        ErrorCode.GENERAL_OPTIONS.fire()

    source_file: Path = args.source
    input_file: Path = args.input

    # Check that the provided paths are valid files (exist and are not directories)
    if not source_file.is_file():
        ErrorCode.GENERAL_INPUT.fire("Source file does not exist or is not a file.")
    if input_file is not None and not input_file.is_file():
        ErrorCode.GENERAL_INPUT.fire("Input file does not exist or is not a file.")

    # Enable debug or info logging if the verbose flag was set twice or once
    if args.verbose >= 2:
        logging.root.setLevel(logging.DEBUG)
    elif args.verbose == 1:
        logging.root.setLevel(logging.INFO)

    # Create an instance of the interpreter
    interpreter = Interpreter()

    try:
        # Load the program from the source file
        interpreter.load_program(source_file)

        if input_file is not None:
            # Execute the program using the provided input file as standard input
            with input_file.open() as input_io:
                interpreter.execute(input_io)
        else:
            # Execute the program with an empty input stream if no input file was provided
            interpreter.execute(StringIO())
    except InterpreterError as e:
        logger.debug("InterpreterError", exc_info=e)
        e.error_code.fire(str(e))
    except SystemExit as e:
        # You are NOT allowed to use exit(), sys.exit(), etc. anywhere in your code.
        # Handle interpretation errors by raising an appropriate InterpreterError
        # with the correct error code.
        logger.error("Caught disallowed SystemExit with code %s", e.code)
        exit(120)
    except Exception as e:
        logger.error("Unhandled exception during interpretation", exc_info=e)
        ErrorCode.GENERAL_OTHER.fire(str(e))


if __name__ == "__main__":
    main()
