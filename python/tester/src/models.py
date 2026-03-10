"""
This module defines the data models used for representing test cases and their results.
It serves as the reference for the testing tool's expected output data structure.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
"""

from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

# ---- Test cases ----


class TestCaseType(IntEnum):
    """Represents the type of a test case: SOL2XML, interpretation only, combined."""

    PARSE_ONLY = 0
    EXECUTE_ONLY = 1
    COMBINED = 2


class TestCaseDefinition(BaseModel):
    """
    Represents a single discovered test case.

    IPP: Do not modify this model directly, as it is also used in the output report.
         You may create your own internal models derived from this one.
    """

    name: str = Field(
        description="The test case name, derived from the test case file name without "
        "the '.test' extension.",
    )
    test_type: TestCaseType = Field(
        description="The type of the test case, which determines how it should be executed "
        "and what exit codes are expected."
    )
    description: str | None = Field(
        default=None, description="An optional human-readable description of the test case."
    )
    category: str = Field(
        description="A string identifier of a category to which this test case belongs."
        "Used for grouping test cases in the final report and for filtering which "
        "test cases to execute."
    )
    points: int = Field(
        default=1, description="The number of points awarded for passing this test case."
    )
    test_source_path: Path = Field(description="Path to the test case definition file ('.test').")
    stdin_file: Path | None = Field(
        default=None,
        description="Path to a file with the standard input contents for the interpreter."
        "Present if the '.in' file was discovered.",
    )
    expected_stdout_file: Path | None = Field(
        default=None,
        description="Path to a file with the expected standard output of the interpreter. "
        "Present if the '.out' file was discovered.",
    )
    expected_parser_exit_codes: list[int] | None = Field(
        default=None,
        description="A list of expected parser exit codes. "
        "Must be present for parser-only test cases. "
        "Must be null for interpreter-only test cases. "
        "Must be null or [0] for combined test cases.",
    )
    expected_interpreter_exit_codes: list[int] | None = Field(
        default=None,
        description="A list of expected interpreter exit code. "
        "Must be present for interpreter-only and combined test cases. "
        "Must be null for parser-only test cases.",
    )

    @model_validator(mode="after")
    def validate_exit_codes(self) -> Self:
        """
        Validates that the expected exit codes are provided correctly based on the test case type.
        """

        if self.test_type == TestCaseType.PARSE_ONLY:
            if not self.expected_parser_exit_codes:
                raise ValueError(
                    "Expected parser exit codes must be provided for parse-only test cases."
                )
            if self.expected_interpreter_exit_codes is not None:
                raise ValueError(
                    "Expected interpreter exit codes should not be provided "
                    "for parse-only test cases."
                )
        elif self.test_type == TestCaseType.EXECUTE_ONLY:
            if not self.expected_interpreter_exit_codes:
                raise ValueError(
                    "Expected interpreter exit codes must be provided for execute-only test cases."
                )
            if self.expected_parser_exit_codes is not None:
                raise ValueError(
                    "Expected parser exit codes should not be provided "
                    "for execute-only test cases."
                )
        elif self.test_type == TestCaseType.COMBINED:
            if self.expected_parser_exit_codes and self.expected_parser_exit_codes != [0]:
                raise ValueError("In combined test cases, the parser exit code must be zero.")
            if not self.expected_interpreter_exit_codes:
                raise ValueError(
                    "Expected interpreter exit codes must be provided for combined test cases."
                )
        else:
            raise ValueError("Invalid test case type.")

        return self


# ---- Output ----


class UnexecutedReasonCode(IntEnum):
    """Represents the reason why a test case was not executed."""

    FILTERED_OUT = 0
    """The test case was filtered out based on the provided include/exclude criteria."""
    MALFORMED_TEST_CASE_FILE = 1
    """The test case file could not be parsed as a valid SOLtest."""
    CANNOT_DETERMINE_TYPE = 2
    """The type of the test case could not be (unambiguously) determined from the
     provided specification."""
    CANNOT_EXECUTE = 3
    """It was not possible to run the external executable that was required for the test."""
    OTHER = 4
    """Unexpected error."""


class UnexecutedReason(BaseModel):
    """
    Represents the reason why a test case was not executed, including an optional
    human-readable message.

    IPP: Choose a suitable message, it won't be evaluated automatically.
    """

    code: UnexecutedReasonCode
    message: str | None = None


class TestResult(StrEnum):
    """Represents the result of an executed test case."""

    PASSED = "passed"
    UNEXPECTED_PARSER_EXIT_CODE = "parse_fail"
    UNEXPECTED_INTERPRETER_EXIT_CODE = "int_fail"
    INTERPRETER_RESULT_DIFFERS = "diff_fail"


class TestCaseReport(BaseModel):
    """Represents the report for a single test case after processing."""

    result: TestResult
    parser_exit_code: int | None = None
    interpreter_exit_code: int | None = None
    parser_stdout: str | None = None
    parser_stderr: str | None = None
    interpreter_stdout: str | None = None
    interpreter_stderr: str | None = None
    diff_output: str | None = None


class CategoryReport(BaseModel):
    """Represents the report for a category of test cases."""

    total_points: int = Field(
        description="The sum of points for all executed test cases in this category."
    )
    passed_points: int = Field(
        description="The sum of points for all passed test cases in this category."
    )
    test_results: dict[str, TestCaseReport] = Field(
        description="A mapping from test case names to their individual reports."
    )


class TestReport(BaseModel):
    """Represents the report generated after processing the test cases."""

    discovered_test_cases: list[TestCaseDefinition]
    unexecuted: dict[str, UnexecutedReason] = Field(
        default_factory=dict,
        description="A mapping from a test case name to the reason why it was not executed.",
    )
    results: dict[str, CategoryReport] | None = Field(
        default=None,
        # The 'results' field is only included in the report if at least one test case was executed
        exclude_if=lambda x: x is None or len(x) == 0,
    )
