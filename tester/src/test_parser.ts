// discovers and parses .test files into TestCaseDefinition objects

import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join, basename, dirname } from "node:path";

import {
  TestCaseDefinition,
  TestCaseType,
  UnexecutedReason,
  UnexecutedReasonCode,
} from "./models.js";

export function discoverTests(dir: string, recursive: boolean): string[] {
  const results: string[] = [];

  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory() && recursive) {
      results.push(...discoverTests(join(dir, entry.name), true));
    }
    if (entry.isFile() && entry.name.endsWith(".test")) {
      results.push(join(dir, entry.name));
    }
  }
  return results;
}

interface ParsedHeader {
  desc: string | null;
  category: string | null;
  points: number | null;
  parserCodes: number[];
  interpreterCodes: number[];
}

function parseHeaderLines(headerLines: string[]): ParsedHeader {
  let desc: string | null = null;
  let category: string | null = null;
  let points: number | null = null;
  const parserCodes: number[] = [];
  const interpreterCodes: number[] = [];

  for (const line of headerLines) {
    if (line.startsWith("***")) {
      desc = line.slice(3).trim();
    }
    if (line.startsWith("+++")) {
      category = line.slice(3).trim();
    }
    if (line.startsWith("!C!")) {
      parserCodes.push(parseInt(line.slice(3).trim()));
    }
    if (line.startsWith("!I!")) {
      interpreterCodes.push(parseInt(line.slice(3).trim()));
    }
    if (line.startsWith(">>>")) {
      points = parseFloat(line.slice(3).trim());
    }
  }

  return { desc, category, points, parserCodes, interpreterCodes };
}

function determineTestType(
  parserCodes: number[],
  interpreterCodes: number[]
): TestCaseType | UnexecutedReason {
  const hasCodes = parserCodes.length > 0;
  const hasICodes = interpreterCodes.length > 0;

  if (hasCodes && !hasICodes) {
    return TestCaseType.PARSE_ONLY;
  }
  if (!hasCodes && hasICodes) {
    return TestCaseType.EXECUTE_ONLY;
  }
  if (hasCodes && hasICodes) {
    // combined requires parser to exit 0 — anything else is ambiguous
    if (parserCodes.length !== 1 || parserCodes[0] !== 0) {
      return new UnexecutedReason(UnexecutedReasonCode.CANNOT_DETERMINE_TYPE);
    }
    return TestCaseType.COMBINED;
  }
  return new UnexecutedReason(UnexecutedReasonCode.CANNOT_DETERMINE_TYPE);
}

interface TestCasePaths {
  testSourcePath: string;
  stdinFile: string | null;
  stdoutFile: string | null;
}

function resolveTestCasePaths(
  path: string,
  name: string,
  dir: string,
  testType: TestCaseType
): TestCasePaths {
  const testSourcePath = testType === TestCaseType.EXECUTE_ONLY ? join(dir, name + ".xml") : path;
  const stdinFile = existsSync(join(dir, name + ".in")) ? join(dir, name + ".in") : null;
  const stdoutFile = existsSync(join(dir, name + ".out")) ? join(dir, name + ".out") : null;
  return { testSourcePath, stdinFile, stdoutFile };
}

export function parseTestFile(path: string): TestCaseDefinition | UnexecutedReason {
  const lines = readFileSync(path, "utf-8").split("\n");

  // look up for empty line separating header from source code
  const emptyLineIndex = lines.findIndex((line: string) => line.trim() === "");
  if (emptyLineIndex === -1) {
    return new UnexecutedReason(UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE);
  }

  const header = parseHeaderLines(lines.slice(0, emptyLineIndex));

  if (header.category === null || header.points === null) {
    return new UnexecutedReason(UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE);
  }

  const testTypeResult = determineTestType(header.parserCodes, header.interpreterCodes);
  if (testTypeResult instanceof UnexecutedReason) {
    return testTypeResult;
  }

  const name = basename(path, ".test");
  const dir = dirname(path);
  const { testSourcePath, stdinFile, stdoutFile } = resolveTestCasePaths(
    path,
    name,
    dir,
    testTypeResult
  );

  const hasCodes = header.parserCodes.length > 0;
  const hasICodes = header.interpreterCodes.length > 0;

  try {
    return new TestCaseDefinition({
      name,
      test_type: testTypeResult,
      description: header.desc,
      category: header.category,
      points: header.points,
      test_source_path: testSourcePath,
      stdin_file: stdinFile,
      expected_stdout_file: stdoutFile,
      expected_parser_exit_codes: hasCodes ? header.parserCodes : null,
      expected_interpreter_exit_codes: hasICodes ? header.interpreterCodes : null,
    });
  } catch {
    return new UnexecutedReason(UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE);
  }
}
