#!/usr/bin/env node
/**
 * This script serves as the main entry point for the SOL26 interpreter.
 *
 * IPP: You should not need to modify this file.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 */

import { readFileSync, statSync } from "node:fs";
import { Readable } from "node:stream";

import { ErrorCode } from "./interpreter/error_codes.js";
import { InterpreterError } from "./interpreter/exceptions.js";
import { Interpreter } from "./interpreter/interpreter.js";
import { getLogger, LogLevel, setLogLevel, type Logger } from "./interpreter/logging.js";

interface CliArguments {
  source: string;
  input: string | null;
  verbose: number;
}

class CliArgumentParsingError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "CliArgumentParsingError";
  }
}

function readRequiredOptionValue(
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

function parseArguments(argv: string[]): CliArguments {
  /**
   * Parses interpreter CLI arguments.
   */

  let source: string | null = null;
  let input: string | null = null;
  let verbose = 0;

  let index = 0;
  while (index < argv.length) {
    const current = argv[index];
    if (current === undefined) {
      break;
    }

    if (current === "-s" || current === "--source") {
      [source, index] = readRequiredOptionValue(argv, index, "--source");
      continue;
    }

    if (current === "-i" || current === "--input") {
      [input, index] = readRequiredOptionValue(argv, index, "--input");
      continue;
    }

    if (current === "-v" || current === "--verbose") {
      verbose += 1;
      index += 1;
      continue;
    }

    throw new CliArgumentParsingError(`Unknown argument: ${current}`);
  }

  if (source === null) {
    throw new CliArgumentParsingError("Missing required argument --source");
  }

  return { source, input, verbose };
}

function parseArgumentsOrFire(argv: string[]): CliArguments {
  try {
    return parseArguments(argv);
  } catch {
    ErrorCode.GENERAL_OPTIONS.fire();
  }

  throw new Error("Unreachable");
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function validateInputPaths(args: CliArguments): void {
  // Check that the provided paths are valid files (exist and are not directories)
  if (!isFile(args.source)) {
    ErrorCode.GENERAL_INPUT.fire("Source file does not exist or is not a file.");
  }

  if (args.input !== null && !isFile(args.input)) {
    ErrorCode.GENERAL_INPUT.fire("Input file does not exist or is not a file.");
  }
}

function configureVerboseLogging(verboseCount: number): void {
  // Enable debug or info logging if the verbose flag was set twice or once
  if (verboseCount >= 2) {
    setLogLevel(LogLevel.DEBUG);
    return;
  }

  if (verboseCount === 1) {
    setLogLevel(LogLevel.INFO);
    return;
  }

  setLogLevel(LogLevel.WARNING);
}

function createInputStream(inputPath: string | null): Readable {
  if (inputPath !== null) {
    // Execute the program using the provided input file as standard input
    const inputText = readFileSync(inputPath, "utf8");
    return Readable.from(inputText);
  }

  // Execute the program with an empty input stream if no input file was provided
  return Readable.from("");
}

function handleUnhandledError(error: unknown, logger: Logger): void {
  if (error instanceof InterpreterError) {
    logger.debug("InterpreterError", error);
    error.errorCode.fire(error.message);
  }

  logger.error("Unhandled exception during interpretation", error);
  ErrorCode.GENERAL_OTHER.fire(error instanceof Error ? error.message : String(error));
}

function main(): void {
  /**
   * The main entry point for the SOL26 interpreter. It parses command-line arguments, and uses
   * the Interpreter class to load and execute the specified program in the SOL-XML format.
   *
   * IPP: Do not modify this function, except for adding additional CLI arguments if you wish.
   */

  // Set up logging
  // IPP: You do not have to use logging - but it is the recommended practice.
  const logger = getLogger("main");

  const args = parseArgumentsOrFire(process.argv.slice(2));
  validateInputPaths(args);
  configureVerboseLogging(args.verbose);

  // Create an instance of the interpreter
  const interpreter = new Interpreter();

  try {
    // Load the program from the source file
    interpreter.loadProgram(args.source);
    interpreter.execute(createInputStream(args.input));
  } catch (error) {
    handleUnhandledError(error, logger);
  }
}

main();
