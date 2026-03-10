#!/usr/bin/env python3
"""
An integration testing script for the SOL26 interpreter.

IPP: You can implement the entire tool in this file if you wish, but it is recommended to split
     the code into multiple files and modules as you see fit.

     Below, you have some code to get you started with the CLI argument parsing and logging setup,
     but you are **free to modify it** in whatever way you like.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
"""

import argparse
import logging
import sys
from pathlib import Path

from models import TestReport

logger = logging.getLogger("main")


class CliArguments(argparse.Namespace):
    """
    Represents the parsed command-line arguments.
    """

    tests_dir: Path
    recursive: bool
    output: Path | None
    dry_run: bool
    include: list[str] | None
    include_category: list[str] | None
    include_test: list[str] | None
    exclude: list[str] | None
    exclude_category: list[str] | None
    exclude_test: list[str] | None
    verbose: int
    regex_filters: bool


def write_result(result_report: TestReport, output_file: Path | None) -> None:
    """
    Writes the final report to the specified output file or standard output if no file is provided.
    """
    result_json = result_report.model_dump_json(indent=2)
    if output_file:
        with output_file.open("w") as f:
            f.write(result_json)
    else:
        print(result_json)


def parse_arguments() -> CliArguments:
    """
    Parses the command-line arguments and performs basic validation a sanitization.
    """

    # Define the CLI arguments
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "tests_dir",
        type=Path,
        help="Path to a directory with the test cases in the SOLtest format.",
    )
    arg_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively search for test cases in subdirectories of the provided directory.",
    )
    arg_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="The output file to write the test results to. "
        "If not provided, results will be printed to standard output.",
    )
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run: discover the test cases but don't actually execute them.",
    )
    arg_parser.add_argument(
        "-i",
        "--include",
        action="append",
        nargs="*",
        help="Include only test cases with the specified name or category. "
        "Can be used multiple times to specify multiple criteria."
        "Can be combined with -ic and -it.",
    )
    arg_parser.add_argument(
        "-ic",
        "--include-category",
        action="append",
        nargs="*",
        help="Include only test cases with the specified category. "
        "Can be used multiple times to specify multiple accepted categories. "
        "Can be combined with -it and -i.",
    )
    arg_parser.add_argument(
        "-it",
        "--include-test",
        action="append",
        nargs="*",
        help="Include only test cases with the specified name. "
        "Can be used multiple times to specify multiple accepted names. "
        "Can be combined with -ic and -i.",
    )
    arg_parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        nargs="*",
        help="Exclude test cases with the specified name or category. "
        "Can be used multiple times to specify multiple criteria."
        "Can be combined with -ic and -it.",
    )
    arg_parser.add_argument(
        "-ec",
        "--exclude-category",
        action="append",
        nargs="*",
        help="Exclude test cases with the specified category. "
        "Can be used multiple times to specify multiple accepted categories. "
        "Can be combined with -it and -i.",
    )
    arg_parser.add_argument(
        "-et",
        "--exclude-test",
        action="append",
        help="Exclude test cases with the specified name. "
        "Can be used multiple times to specify multiple accepted names. "
        "Can be combined with -ic and -i.",
    )
    arg_parser.add_argument(
        "-g",
        dest="regex_filters",
        action="store_true",
        help="When used, the filters specified with -i[ct]/-e[ct] will be interpreted as "
        "regular expressions instead of literal strings.",
    )  # TODO: This is optional. If you don't want to implement it, remove this argument.
    arg_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Enable verbose logging output (using once = INFO level, using twice = DEBUG level).",
    )

    # Parse the provided arguments
    # argparse will automatically print an error message and exit with the return code 2
    # in case of invalid arguments
    args = arg_parser.parse_args(namespace=CliArguments())

    # Check source directory
    source_directory: Path = args.tests_dir
    if not source_directory.is_dir():
        print("The provided path is not a directory.", file=sys.stderr)
        exit(1)

    # Warn if the output file already exists
    output_file: Path | None = args.output
    if output_file:
        if not output_file.parent.exists():
            print("The parent directory of the output file does not exist.", file=sys.stderr)
            exit(1)
        if output_file.exists():
            logger.warning("The output file will be overwritten: %s", output_file)

    return args


def main() -> None:
    """
    The main entry point for the SOL26 integration testing script.
    It parses command-line arguments and executes the testing process.
    """

    # Set up logging
    # IPP: You do not have to use logging – but it is the recommended practice.
    # See this for more information: https://docs.python.org/3/howto/logging.html
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s [%(name)s][%(filename)s:%(lineno)d] %(message)s",
    )

    # Parse the CLI arguments
    args = parse_arguments()

    # Enable debug or info logging if the verbose flag was set twice or once
    if args.verbose >= 2:
        logging.root.setLevel(logging.DEBUG)
    elif args.verbose == 1:
        logging.root.setLevel(logging.INFO)

    # TODO: Your code for discovering and executing the test cases goes here.

    # Example of how to write the final report:
    report = TestReport(discovered_test_cases=[], unexecuted={}, results={})
    write_result(report, args.output)


if __name__ == "__main__":
    main()
