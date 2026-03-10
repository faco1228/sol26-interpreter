/**
 * A very small logging helper used by the template.
 */

export enum LogLevel {
  DEBUG = 10,
  INFO = 20,
  WARNING = 30,
  ERROR = 40,
}

let currentLevel: LogLevel = LogLevel.WARNING;

function levelToName(level: LogLevel): string {
  switch (level) {
    case LogLevel.DEBUG:
      return "DEBUG";
    case LogLevel.INFO:
      return "INFO";
    case LogLevel.WARNING:
      return "WARNING";
    case LogLevel.ERROR:
      return "ERROR";
  }
}

function writeLog(level: LogLevel, loggerName: string, message: string, error?: unknown): void {
  if (level < currentLevel) {
    return;
  }

  const timestamp = new Date().toISOString();
  const prefix = `${timestamp} ${levelToName(level)} [${loggerName}]`;
  if (error instanceof Error) {
    console.error(`${prefix} ${message}: ${error.message}`);
    if (error.stack) {
      console.error(error.stack);
    }
  } else if (error !== undefined) {
    console.error(`${prefix} ${message}`, error);
  } else {
    console.error(`${prefix} ${message}`);
  }
}

export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
}

export interface Logger {
  debug: (message: string, error?: unknown) => void;
  info: (message: string, ...args: unknown[]) => void;
  warning: (message: string, ...args: unknown[]) => void;
  error: (message: string, error?: unknown) => void;
}

function formatMessage(message: string, args: unknown[]): string {
  if (args.length === 0) {
    return message;
  }
  return `${message} ${args.map((arg) => String(arg)).join(" ")}`;
}

export function getLogger(loggerName: string): Logger {
  return {
    debug: (message: string, error?: unknown) => {
      writeLog(LogLevel.DEBUG, loggerName, message, error);
    },
    info: (message: string, ...args: unknown[]) => {
      writeLog(LogLevel.INFO, loggerName, formatMessage(message, args));
    },
    warning: (message: string, ...args: unknown[]) => {
      writeLog(LogLevel.WARNING, loggerName, formatMessage(message, args));
    },
    error: (message: string, error?: unknown) => {
      writeLog(LogLevel.ERROR, loggerName, message, error);
    },
  };
}
