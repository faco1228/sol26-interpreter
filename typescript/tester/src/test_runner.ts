// test-runner.ts
// filterTests(tests, args) → {toRun, filtered}
//   - include/exclude logic
//   - regex if args.regex_filters

// runTest(test, args) → TestCaseReport
//   - EXECUTE_ONLY: run interpreter on .xml file
//   - COMBINED: run sol2xml → then interpreter
//   - PARSE_ONLY: run only sol2xml
//   - compare exit code, diff stdout

// buildReport(tests, results, unexecuted) → TestReport

import { spawnSync } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { CliArguments } from "./tester.js";

import {
  TestCaseDefinition,
  TestCaseReport,
  TestCaseType,
  TestResult,
  UnexecutedReason,
  UnexecutedReasonCode,
  CategoryReport,
  TestReport,
} from "./models.js";

interface ProcessResult {
  status: number;
  stdout: string;
  stderr: string;
}

function runProcess(command: string, extraArgs: string[]): ProcessResult {
  const quotedArgs = extraArgs.map((a) => `'${a.replace(/'/g, "'\\''")}'`);
  const fullCommand = `${command.trim()} ${quotedArgs.join(" ")}`;
  const result = spawnSync("sh", ["-c", fullCommand], {
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });
  return { status: result.status ?? 1, stdout: result.stdout, stderr: result.stderr };
}

function runDiff(actualOutput: string, expectedFile: string): { status: number; output: string } {
  const tmpDir = mkdtempSync(join(tmpdir(), "sol26-"));
  const tmpActual = join(tmpDir, "actual.txt");
  try {
    writeFileSync(tmpActual, actualOutput, "utf8");
    const result = spawnSync("diff", [expectedFile, tmpActual], { encoding: "utf8" });
    return { status: result.status ?? 1, output: result.stdout };
  } finally {
    rmSync(tmpDir, { recursive: true });
  }
}

function runInterpreter(cmd: string, xmlPath: string, stdinFile: string | null): ProcessResult {
  const extraArgs = ["--source", xmlPath];
  if (stdinFile !== null) {
    extraArgs.push("--input", stdinFile);
  }
  return runProcess(cmd, extraArgs);
}

function matchesFilter(value: string, pattern: string, useRegex: boolean): boolean {
  if (useRegex) {
    return new RegExp(pattern).test(value);
  }
  return value === pattern;
}

export function filterTests(
  tests: TestCaseDefinition[],
  args: CliArguments
): { toRun: TestCaseDefinition[]; filtered: TestCaseDefinition[] } {
  let toRun = [...tests];
  const { include, include_category, include_test, exclude, exclude_category, exclude_test } =
    args;
  const useRegex = args.regex_filters;

  const match = (value: string, pattern: string) => matchesFilter(value, pattern, useRegex);

  if (include !== null) {
    toRun = toRun.filter((test) =>
      include.some((id) => match(test.name, id) || match(test.category, id))
    );
  }
  if (include_category !== null) {
    toRun = toRun.filter((test) => include_category.some((id) => match(test.category, id)));
  }
  if (include_test !== null) {
    toRun = toRun.filter((test) => include_test.some((id) => match(test.name, id)));
  }
  if (exclude !== null) {
    toRun = toRun.filter(
      (test) => !exclude.some((id) => match(test.name, id) || match(test.category, id))
    );
  }
  if (exclude_category !== null) {
    toRun = toRun.filter((test) => !exclude_category.some((id) => match(test.category, id)));
  }
  if (exclude_test !== null) {
    toRun = toRun.filter((test) => !exclude_test.some((id) => match(test.name, id)));
  }

  const filtered = tests.filter((test) => !toRun.includes(test));
  return { toRun, filtered };
}

function extractSourceFromTestFile(testPath: string): string {
  const lines = readFileSync(testPath, "utf-8").split("\n");
  const emptyLineIndex = lines.findIndex((line: string) => line.trim() === "");
  return lines.slice(emptyLineIndex + 1).join("\n");
}

function runExecuteOnly(test: TestCaseDefinition, args: CliArguments): TestCaseReport {
  const r = runInterpreter(args.interpreter ?? "", test.test_source_path, test.stdin_file);
  const expectedCodes = test.expected_interpreter_exit_codes ?? [];

  if (!expectedCodes.includes(r.status)) {
    return new TestCaseReport(
      TestResult.UNEXPECTED_INTERPRETER_EXIT_CODE,
      null,
      r.status,
      null,
      null,
      r.stdout,
      r.stderr
    );
  }
  if (r.status === 0 && test.expected_stdout_file !== null) {
    const diff = runDiff(r.stdout, test.expected_stdout_file);
    if (diff.status !== 0) {
      return new TestCaseReport(
        TestResult.INTERPRETER_RESULT_DIFFERS,
        null,
        r.status,
        null,
        null,
        r.stdout,
        r.stderr,
        diff.output
      );
    }
  }
  return new TestCaseReport(TestResult.PASSED, null, r.status, null, null, r.stdout, r.stderr);
}

function runParseOnly(
  test: TestCaseDefinition,
  args: CliArguments,
  sourcePath: string
): TestCaseReport {
  const r = runProcess(args.parser as string, [sourcePath]);
  const expectedCodes = test.expected_parser_exit_codes ?? [];

  if (!expectedCodes.includes(r.status)) {
    return new TestCaseReport(
      TestResult.UNEXPECTED_PARSER_EXIT_CODE,
      r.status,
      null,
      r.stdout,
      r.stderr
    );
  }
  return new TestCaseReport(TestResult.PASSED, r.status, null, r.stdout, r.stderr);
}

function runCombined(
  test: TestCaseDefinition,
  args: CliArguments,
  sourcePath: string
): TestCaseReport {
  const pr = runProcess(args.parser as string, [sourcePath]);

  if (pr.status !== 0) {
    return new TestCaseReport(
      TestResult.UNEXPECTED_PARSER_EXIT_CODE,
      pr.status,
      null,
      pr.stdout,
      pr.stderr
    );
  }

  const tmpDir = mkdtempSync(join(tmpdir(), "sol26-"));
  const tmpXml = join(tmpDir, "parsed.xml");

  try {
    writeFileSync(tmpXml, pr.stdout, "utf8");
    const ir = runInterpreter(args.interpreter ?? "", tmpXml, test.stdin_file);
    const expectedCodes = test.expected_interpreter_exit_codes ?? [];

    if (!expectedCodes.includes(ir.status)) {
      return new TestCaseReport(
        TestResult.UNEXPECTED_INTERPRETER_EXIT_CODE,
        pr.status,
        ir.status,
        pr.stdout,
        pr.stderr,
        ir.stdout,
        ir.stderr
      );
    }
    if (ir.status === 0 && test.expected_stdout_file !== null) {
      const diff = runDiff(ir.stdout, test.expected_stdout_file);
      if (diff.status !== 0) {
        return new TestCaseReport(
          TestResult.INTERPRETER_RESULT_DIFFERS,
          pr.status,
          ir.status,
          pr.stdout,
          pr.stderr,
          ir.stdout,
          ir.stderr,
          diff.output
        );
      }
    }
    return new TestCaseReport(
      TestResult.PASSED,
      pr.status,
      ir.status,
      pr.stdout,
      pr.stderr,
      ir.stdout,
      ir.stderr
    );
  } finally {
    rmSync(tmpDir, { recursive: true });
  }
}

export function runTest(
  test: TestCaseDefinition,
  args: CliArguments
): TestCaseReport | UnexecutedReason {
  if (args.interpreter === null) {
    return new UnexecutedReason(UnexecutedReasonCode.CANNOT_EXECUTE, "--interpreter not provided");
  }

  if (test.test_type === TestCaseType.EXECUTE_ONLY) {
    return runExecuteOnly(test, args);
  }

  if (args.parser === null) {
    return new UnexecutedReason(UnexecutedReasonCode.CANNOT_EXECUTE, "--parser not provided");
  }

  const sourceCode = extractSourceFromTestFile(test.test_source_path);
  const srcTmpDir = mkdtempSync(join(tmpdir(), "sol26-src-"));
  const srcTmpFile = join(srcTmpDir, "source.sol");
  writeFileSync(srcTmpFile, sourceCode, "utf8");

  try {
    if (test.test_type === TestCaseType.PARSE_ONLY) {
      return runParseOnly(test, args, srcTmpFile);
    }
    return runCombined(test, args, srcTmpFile);
  } finally {
    rmSync(srcTmpDir, { recursive: true });
  }
}

export function buildReport(
  allTests: TestCaseDefinition[],
  results: Map<string, { test: TestCaseDefinition; report: TestCaseReport }>,
  unexecuted: Map<string, UnexecutedReason>
): TestReport {
  const unexecutedObj: Record<string, UnexecutedReason> = {};
  for (const [name, reason] of unexecuted) {
    unexecutedObj[name] = reason;
  }

  const categoryMap = new Map<string, { test: TestCaseDefinition; report: TestCaseReport }[]>();
  for (const [, entry] of results) {
    const cat = entry.test.category;
    let catArr = categoryMap.get(cat);
    if (catArr === undefined) {
      catArr = [];
      categoryMap.set(cat, catArr);
    }
    catArr.push(entry);
  }

  const categoryReports: Record<string, CategoryReport> = {};
  for (const [cat, entries] of categoryMap) {
    let totalPoints = 0;
    let passedPoints = 0;
    const testResults: Record<string, TestCaseReport> = {};

    for (const entry of entries) {
      totalPoints += entry.test.points;
      if (entry.report.result === TestResult.PASSED) {
        passedPoints += entry.test.points;
      }
      testResults[entry.test.name] = entry.report;
    }
    categoryReports[cat] = new CategoryReport(totalPoints, passedPoints, testResults);
  }

  return new TestReport({
    discovered_test_cases: allTests,
    unexecuted: unexecutedObj,
    results: categoryReports,
  });
}
