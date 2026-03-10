/**
 * This module defines the custom exception classes used by the interpreter to represent various error
 * conditions that can occur during interpretation.
 *
 * IPP: You can freely modify this file and add any additional exception classes.
 *      However, the InterpreterError class must be used as a base for any exceptions that control
 *      the outcome of the interpretation (i.e., those that are caught in solint.ts and cause
 *      the interpreter to exit with a specific error code).
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 */

import { ErrorCode } from "./error_codes.js";

export class InterpreterError extends Error {
  /**
   * A general exception class for errors that occur during interpretation.
   * It includes an error code instance that can be used to determine the appropriate
   * exit code for the program.
   */
  public constructor(
    public readonly errorCode: ErrorCode,
    message?: string
  ) {
    super(message);
    this.name = "InterpreterError";
  }
}
