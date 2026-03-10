#!/usr/bin/env node
/**
 * An integration testing script for the SOL26 interpreter.
 *
 * IPP: You can implement the entire tool in this file if you wish, but it is recommended to split
 *      the code into multiple files and modules as you see fit.
 *
 *      Below, you have some code to get you started with the CLI argument parsing and logging setup,
 *      but you are **free to modify it** in whatever way you like.
 *
 * Author: Ondrej Ondryas <iondryas@fit.vut.cz>
 */

import { existsSync, lstatSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { getLogger, LogLevel, setLogLevel } from "./logging.js";
import { TestReport } from "./models.js";

const logger = getLogger("main");

interface CliArguments {
  tests_dir: string;
  recursive: boolean;
  output: string | null;
  dry_run: boolean;
  include: string[] | null;
  include_category: string[] | null;
  include_test: string[] | null;
  exclude: string[] | null;
  exclude_category: string[] | null;
  exclude_test: string[] | null;
  verbose: number;
  regex_filters: boolean;
}

class CliArgumentParsingError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "CliArgumentParsingError";
  }
}

interface ParserState {
  positionalArguments: string[];
  include: string[];
  includeCategory: string[];
  includeTest: string[];
  exclude: string[];
  excludeCategory: string[];
  excludeTest: string[];
  recursive: boolean;
  output: string | null;
  dryRun: boolean;
  regexFilters: boolean;
  verbose: number;
}

function writeResult(resultReport: TestReport, outputFile: string | null): void {
  /**
   * Writes the final report to the specified output file or standard output if no file is provided.
   */
  const resultJson = JSON.stringify(resultReport, null, 2);
  if (outputFile !== null) {
    writeFileSync(outputFile, resultJson, "utf8");
    return;
  }

  console.log(resultJson);
}

function createParserState(): ParserState {
  return {
    positionalArguments: [],
    include: [],
    includeCategory: [],
    includeTest: [],
    exclude: [],
    excludeCategory: [],
    excludeTest: [],
    recursive: false,
    output: null,
    dryRun: false,
    regexFilters: false,
    verbose: 0,
  };
}

function readRequiredValue(
  argv: string[],
  currentIndex: number,
  optionName: string
): [string, number] {
  const value = argv[currentIndex + 1];
  if (value === undefined || value.startsWith("-")) {
    throw new CliArgumentParsingError(`Missing value for ${optionName}`);
  }

  return [value, currentIndex + 2];
}

function collectOptionalValues(argv: string[], startIndex: number): [string[], number] {
  const values: string[] = [];
  let index = startIndex;

  while (index < argv.length) {
    const value = argv[index];
    if (value === undefined || value.startsWith("-")) {
      break;
    }

    values.push(value);
    index += 1;
  }

  return [values, index];
}

function tryConsumeBooleanOption(current: string, state: ParserState): boolean {
  if (current === "-r" || current === "--recursive") {
    state.recursive = true;
    return true;
  }

  if (current === "--dry-run") {
    state.dryRun = true;
    return true;
  }

  if (current === "-g") {
    state.regexFilters = true;
    return true;
  }

  if (current === "-v" || current === "--verbose") {
    state.verbose += 1;
    return true;
  }

  return false;
}

function tryConsumeRequiredValueOption(
  argv: string[],
  current: string,
  index: number,
  state: ParserState
): number | null {
  if (current !== "-o" && current !== "--output") {
    return null;
  }

  const [value, nextIndex] = readRequiredValue(argv, index, "--output");
  state.output = value;
  return nextIndex;
}

function tryConsumeSingleListValueOption(
  argv: string[],
  current: string,
  index: number,
  state: ParserState
): number | null {
  if (current !== "-et" && current !== "--exclude-test") {
    return null;
  }

  const [value, nextIndex] = readRequiredValue(argv, index, "--exclude-test");
  state.excludeTest.push(value);
  return nextIndex;
}

const OPTIONAL_LIST_OPTION_NAMES = {
  "-i": "include",
  "--include": "include",
  "-ic": "includeCategory",
  "--include-category": "includeCategory",
  "-it": "includeTest",
  "--include-test": "includeTest",
  "-e": "exclude",
  "--exclude": "exclude",
  "-ec": "excludeCategory",
  "--exclude-category": "excludeCategory",
} as const;

type OptionalListOptionName = keyof typeof OPTIONAL_LIST_OPTION_NAMES;
type OptionalListStateKey = (typeof OPTIONAL_LIST_OPTION_NAMES)[OptionalListOptionName];

function getOptionalListTarget(current: string, state: ParserState): string[] | null {
  const key = OPTIONAL_LIST_OPTION_NAMES[current as OptionalListOptionName] as
    | OptionalListStateKey
    | undefined;
  return key === undefined ? null : state[key];
}

function tryConsumeOptionalListOption(
  argv: string[],
  current: string,
  index: number,
  state: ParserState
): number | null {
  const target = getOptionalListTarget(current, state);
  if (target === null) {
    return null;
  }

  const [values, nextIndex] = collectOptionalValues(argv, index + 1);
  target.push(...values);
  return nextIndex;
}

type OptionConsumer = (
  argv: string[],
  current: string,
  index: number,
  state: ParserState
) => number | null;

function consumeToken(argv: string[], index: number, state: ParserState): number {
  const current = argv[index];
  if (current === undefined) {
    return index + 1;
  }

  if (tryConsumeBooleanOption(current, state)) {
    return index + 1;
  }

  const consumers: OptionConsumer[] = [
    tryConsumeRequiredValueOption,
    tryConsumeOptionalListOption,
    tryConsumeSingleListValueOption,
  ];
  for (const consumeOption of consumers) {
    const nextIndex = consumeOption(argv, current, index, state);
    if (nextIndex !== null) {
      return nextIndex;
    }
  }

  if (current.startsWith("-")) {
    throw new CliArgumentParsingError(`Unknown argument: ${current}`);
  }

  state.positionalArguments.push(current);
  return index + 1;
}

function parseCliArguments(argv: string[]): CliArguments {
  const state = createParserState();

  let index = 0;
  while (index < argv.length) {
    index = consumeToken(argv, index, state);
  }

  if (state.positionalArguments.length !== 1) {
    throw new CliArgumentParsingError("Exactly one positional argument (tests_dir) is required.");
  }

  const testsDirectory = state.positionalArguments[0];
  if (testsDirectory === undefined) {
    throw new CliArgumentParsingError("Exactly one positional argument (tests_dir) is required.");
  }

  return {
    tests_dir: resolve(testsDirectory),
    recursive: state.recursive,
    output: state.output,
    dry_run: state.dryRun,
    include: state.include.length > 0 ? state.include : null,
    include_category: state.includeCategory.length > 0 ? state.includeCategory : null,
    include_test: state.includeTest.length > 0 ? state.includeTest : null,
    exclude: state.exclude.length > 0 ? state.exclude : null,
    exclude_category: state.excludeCategory.length > 0 ? state.excludeCategory : null,
    exclude_test: state.excludeTest.length > 0 ? state.excludeTest : null,
    verbose: state.verbose,
    regex_filters: state.regexFilters,
  };
}

function parseArguments(): CliArguments {
  /**
   * Parses the command-line arguments and performs basic validation a sanitization.
   */

  // Parse the provided arguments
  // argparse will automatically print an error message and exit with the return code 2
  // in case of invalid arguments
  let args: CliArguments;
  try {
    args = parseCliArguments(process.argv.slice(2));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(message);
    process.exit(2);
  }

  // Check source directory
  if (!existsSync(args.tests_dir) || !lstatSync(args.tests_dir).isDirectory()) {
    console.error("The provided path is not a directory.");
    process.exit(1);
  }

  // Warn if the output file already exists
  if (args.output !== null) {
    const parentDirectory = dirname(args.output);
    if (!existsSync(parentDirectory)) {
      console.error("The parent directory of the output file does not exist.");
      process.exit(1);
    }
    if (existsSync(args.output)) {
      logger.warning("The output file will be overwritten:", args.output);
    }
  }

  return args;
}

function main(): void {
  /**
   * The main entry point for the SOL26 integration testing script.
   * It parses command-line arguments and executes the testing process.
   */

  // Set up logging
  // IPP: You do not have to use logging - but it is the recommended practice.
  setLogLevel(LogLevel.WARNING);

  // Parse the CLI arguments
  const args = parseArguments();

  // Enable debug or info logging if the verbose flag was set twice or once
  if (args.verbose >= 2) {
    setLogLevel(LogLevel.DEBUG);
  } else if (args.verbose === 1) {
    setLogLevel(LogLevel.INFO);
  }

  // TODO: Your code for discovering and executing the test cases goes here.

  // Example of how to write the final report:
  const report = new TestReport({ discovered_test_cases: [], unexecuted: {}, results: {} });
  writeResult(report, args.output);
}

main();
