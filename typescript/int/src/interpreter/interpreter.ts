/**
 * This module contains the main logic of the interpreter.
 *
 * IPP: You must definitely modify this file. Bend it to your will.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 * Author:
 */

import { readFileSync } from "node:fs";
import type { Readable } from "node:stream";

import { ErrorCode } from "./error_codes.js";
import { InterpreterError } from "./exceptions.js";
import {
  InvalidXmlError,
  ModelValidationError,
  parseProgramXml,
  type Program,
} from "./input_model.js";
import { getLogger } from "./logging.js";

const logger = getLogger("interpreter");

export class Interpreter {
  /**
   * The main interpreter class, responsible for loading the source file and executing the program.
   */

  public currentProgram: Program | null = null;

  public loadProgram(sourceFilePath: string): void {
    /**
     * Reads the source SOL-XML file and stores it as the target program for this interpreter.
     * If any program was previously loaded, it is replaced by the new one.
     *
     * IPP: If you wish to run static checks on the program before execution, this is a good place
     *      to call them from.
     */
    logger.info("Opening source file:", sourceFilePath);

    try {
      const sourceText = readFileSync(sourceFilePath, "utf8");
      this.currentProgram = parseProgramXml(sourceText);
    } catch (error) {
      if (error instanceof InvalidXmlError) {
        throw new InterpreterError(ErrorCode.INT_XML, "Error parsing input XML");
      }
      if (error instanceof ModelValidationError) {
        throw new InterpreterError(ErrorCode.INT_STRUCTURE, "Invalid SOL-XML structure");
      }
      throw error;
    }
  }

  public execute(inputIo: Readable): void {
    /**
     * Executes the currently loaded program, using the provided input stream as standard input.
     */
    logger.info("Executing program");
    void inputIo;

    // TODO: Your logic goes here.
  }
}
