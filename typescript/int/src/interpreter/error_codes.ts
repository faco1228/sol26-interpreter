/**
 * This module defines the ErrorCode class, which contains all the error codes specified by
 * the project assignment.
 *
 * IPP: You should not need to modify this file. However, you may add additional helper methods
 *      to the ErrorCode class.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 */

export class ErrorCode {
  // General errors (10-19 + 99)
  public static readonly GENERAL_OPTIONS = new ErrorCode(
    "GENERAL_OPTIONS",
    10,
    "missing required CLI parameter or forbidden parameter combination"
  );
  public static readonly GENERAL_INPUT = new ErrorCode(
    "GENERAL_INPUT",
    11,
    "error opening input files (nonexistent, insufficient permissions, etc.)"
  );
  public static readonly GENERAL_OTHER = new ErrorCode(
    "GENERAL_OTHER",
    99,
    "unexpected internal error (uncategorized)"
  );

  // Interpreter / XML errors
  public static readonly INT_XML = new ErrorCode(
    "INT_XML",
    20,
    "invalid XML input (not well-formed / cannot be parsed)"
  );
  public static readonly INT_STRUCTURE = new ErrorCode(
    "INT_STRUCTURE",
    42,
    "unexpected XML structure (nesting, missing required attrs, etc.)"
  );

  // Static semantic errors
  public static readonly SEM_MAIN = new ErrorCode(
    "SEM_MAIN",
    31,
    "missing Main class or its instance method run"
  );
  public static readonly SEM_UNDEF = new ErrorCode(
    "SEM_UNDEF",
    32,
    "use of undefined/uninitialized variable/parameter/class/method"
  );
  public static readonly SEM_ARITY = new ErrorCode(
    "SEM_ARITY",
    33,
    "arity error for block assigned to selector in method definition"
  );
  public static readonly SEM_COLLISION = new ErrorCode(
    "SEM_COLLISION",
    34,
    "assignment to a block's formal parameter (on LHS of assignment)"
  );
  public static readonly SEM_ERROR = new ErrorCode(
    "SEM_ERROR",
    35,
    "other static semantic error (e.g., class redefinition, name collisions)"
  );

  // Runtime interpreter errors
  public static readonly INT_DNU = new ErrorCode(
    "INT_DNU",
    51,
    "receiver does not understand the message (excluding instance-attr creation)"
  );
  public static readonly INT_OTHER = new ErrorCode(
    "INT_OTHER",
    52,
    "other runtime errors (e.g., wrong operand types)"
  );
  public static readonly INT_INVALID_ARG = new ErrorCode(
    "INT_INVALID_ARG",
    53,
    "invalid argument value (e.g., division by zero)"
  );
  public static readonly INT_INST_ATTR = new ErrorCode(
    "INT_INST_ATTR",
    54,
    "attempt to create instance attribute colliding with a method"
  );

  private constructor(
    public readonly name: string,
    public readonly value: number,
    public readonly description: string
  ) {}

  public fire(message?: string): never {
    if (message !== undefined && message.length > 0) {
      console.error(`Error ${String(this.value)}: ${message}`);
    } else {
      console.error(`Error ${String(this.value)} (${this.name})`);
    }
    process.exit(this.value);
  }
}
