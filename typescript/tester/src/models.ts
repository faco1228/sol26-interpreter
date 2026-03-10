/**
 * This module defines the data models used for representing test cases and their results.
 * It serves as the reference for the testing tool's expected output data structure.
 *
 * Author: Ondrej Ondryas <iondryas@fit.vut.cz>
 */

// ---- Test cases ----

export enum TestCaseType {
  /** Represents the type of a test case: SOL2XML, interpretation only, combined. */
  PARSE_ONLY = 0,
  EXECUTE_ONLY = 1,
  COMBINED = 2,
}

export interface TestCaseDefinitionInit {
  name: string;
  test_type: TestCaseType;
  description?: string | null;
  category: string;
  points?: number;
  test_source_path: string;
  stdin_file?: string | null;
  expected_stdout_file?: string | null;
  expected_parser_exit_codes?: number[] | null;
  expected_interpreter_exit_codes?: number[] | null;
}

export class TestCaseDefinition {
  /**
   * Represents a single discovered test case.
   *
   * IPP: Do not modify this model directly, as it is also used in the output report.
   *      You may create your own internal models derived from this one.
   */

  public readonly name: string;
  public readonly test_type: TestCaseType;
  public readonly description: string | null;
  public readonly category: string;
  public readonly points: number;
  public readonly test_source_path: string;
  public readonly stdin_file: string | null;
  public readonly expected_stdout_file: string | null;
  public readonly expected_parser_exit_codes: number[] | null;
  public readonly expected_interpreter_exit_codes: number[] | null;

  public constructor(init: TestCaseDefinitionInit) {
    this.name = init.name;
    this.test_type = init.test_type;
    this.description = init.description ?? null;
    this.category = init.category;
    this.points = init.points ?? 1;
    this.test_source_path = init.test_source_path;
    this.stdin_file = init.stdin_file ?? null;
    this.expected_stdout_file = init.expected_stdout_file ?? null;
    this.expected_parser_exit_codes = init.expected_parser_exit_codes ?? null;
    this.expected_interpreter_exit_codes = init.expected_interpreter_exit_codes ?? null;

    this.validateExitCodes();
  }

  private static hasNoExitCodes(exitCodes: number[] | null): boolean {
    return exitCodes === null || exitCodes.length === 0;
  }

  private validateParseOnlyExitCodes(): void {
    if (TestCaseDefinition.hasNoExitCodes(this.expected_parser_exit_codes)) {
      throw new Error("Expected parser exit codes must be provided for parse-only test cases.");
    }
    if (this.expected_interpreter_exit_codes !== null) {
      throw new Error(
        "Expected interpreter exit codes should not be provided for parse-only test cases."
      );
    }
  }

  private validateExecuteOnlyExitCodes(): void {
    if (TestCaseDefinition.hasNoExitCodes(this.expected_interpreter_exit_codes)) {
      throw new Error(
        "Expected interpreter exit codes must be provided for execute-only test cases."
      );
    }
    if (this.expected_parser_exit_codes !== null) {
      throw new Error(
        "Expected parser exit codes should not be provided for execute-only test cases."
      );
    }
  }

  private validateCombinedExitCodes(): void {
    if (
      this.expected_parser_exit_codes !== null &&
      (this.expected_parser_exit_codes.length !== 1 || this.expected_parser_exit_codes[0] !== 0)
    ) {
      throw new Error("In combined test cases, the parser exit code must be zero.");
    }
    if (TestCaseDefinition.hasNoExitCodes(this.expected_interpreter_exit_codes)) {
      throw new Error("Expected interpreter exit codes must be provided for combined test cases.");
    }
  }

  private validateExitCodes(): void {
    /**
     * Validates that the expected exit codes are provided correctly based on the test case type.
     */
    switch (this.test_type) {
      case TestCaseType.PARSE_ONLY:
        this.validateParseOnlyExitCodes();
        return;
      case TestCaseType.EXECUTE_ONLY:
        this.validateExecuteOnlyExitCodes();
        return;
      case TestCaseType.COMBINED:
        this.validateCombinedExitCodes();
        return;
    }
  }
}

// ---- Output ----

export enum UnexecutedReasonCode {
  /** The test case was filtered out based on the provided include/exclude criteria. */
  FILTERED_OUT = 0,
  /** The test case file could not be parsed as a valid SOLtest. */
  MALFORMED_TEST_CASE_FILE = 1,
  /** The type of the test case could not be (unambiguously) determined from the provided specification. */
  CANNOT_DETERMINE_TYPE = 2,
  /** It was not possible to run the external executable that was required for the test. */
  CANNOT_EXECUTE = 3,
  /** Unexpected error. */
  OTHER = 4,
}

export class UnexecutedReason {
  /**
   * Represents the reason why a test case was not executed, including an optional
   * human-readable message.
   *
   * IPP: Choose a suitable message, it won't be evaluated automatically.
   */

  public constructor(
    public readonly code: UnexecutedReasonCode,
    public readonly message: string | null = null
  ) {}
}

export enum TestResult {
  /** Represents the result of an executed test case. */
  PASSED = "passed",
  UNEXPECTED_PARSER_EXIT_CODE = "parse_fail",
  UNEXPECTED_INTERPRETER_EXIT_CODE = "int_fail",
  INTERPRETER_RESULT_DIFFERS = "diff_fail",
}

export class TestCaseReport {
  /** Represents the report for a single test case after processing. */

  public constructor(
    public readonly result: TestResult,
    public readonly parser_exit_code: number | null = null,
    public readonly interpreter_exit_code: number | null = null,
    public readonly parser_stdout: string | null = null,
    public readonly parser_stderr: string | null = null,
    public readonly interpreter_stdout: string | null = null,
    public readonly interpreter_stderr: string | null = null,
    public readonly diff_output: string | null = null
  ) {}
}

export class CategoryReport {
  /** Represents the report for a category of test cases. */

  public constructor(
    public readonly total_points: number,
    public readonly passed_points: number,
    public readonly test_results: Record<string, TestCaseReport>
  ) {}
}

export interface TestReportInit {
  discovered_test_cases: TestCaseDefinition[];
  unexecuted?: Record<string, UnexecutedReason>;
  results?: Record<string, CategoryReport> | null;
}

export class TestReport {
  /** Represents the report generated after processing the test cases. */

  public readonly discovered_test_cases: TestCaseDefinition[];
  public readonly unexecuted: Record<string, UnexecutedReason>;
  public readonly results: Record<string, CategoryReport> | null;

  public constructor(init: TestReportInit) {
    this.discovered_test_cases = init.discovered_test_cases;
    this.unexecuted = init.unexecuted ?? {};
    this.results = init.results ?? null;
  }

  public toJSON(): Record<string, unknown> {
    const result: Record<string, unknown> = {
      discovered_test_cases: this.discovered_test_cases,
      unexecuted: this.unexecuted,
    };

    // The 'results' field is only included in the report if at least one test case was executed.
    if (this.results !== null && Object.keys(this.results).length > 0) {
      result["results"] = this.results;
    }

    return result;
  }
}
