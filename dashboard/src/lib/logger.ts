/**
 * @fileoverview Structured logging utility for the dashboard.
 *
 * Provides consistent log formatting with context and level-based filtering.
 * In production, logs can be suppressed or sent to a logging service.
 */

/**
 * Log severity levels supported by the logger.
 * Ordered from lowest to highest severity: debug < info < warn < error.
 */
type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/**
 * Context object for structured logging.
 * Allows arbitrary key-value pairs for contextual data that will be serialized to JSON.
 * @property [key: string] - Arbitrary context properties
 */
interface LogContext {
  [key: string]: unknown;
}

/**
 * Log level severities mapped to numeric values for filtering comparison.
 * Higher numbers represent higher severity levels.
 */
const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

/**
 * Minimum log level - in production, suppress debug/info logs.
 * Development: debug, Production: warn.
 */
const MIN_LOG_LEVEL: LogLevel = import.meta.env.PROD ? 'warn' : 'debug';

/**
 * Determines if a log message should be emitted based on level filtering.
 * Compares the provided level against MIN_LOG_LEVEL.
 * @param level - The log level to check
 * @returns True if the level meets or exceeds the minimum threshold
 */
function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[MIN_LOG_LEVEL];
}

/**
 * Formats a log message with timestamp, level, and optional context.
 * Format: [ISO timestamp] [LEVEL] message {contextJSON}
 * @param level - Log severity level
 * @param message - The log message
 * @param context - Optional structured context data to append as JSON
 * @returns Formatted log string
 */
function formatMessage(level: LogLevel, message: string, context?: LogContext): string {
  const timestamp = new Date().toISOString();
  const contextStr = context ? ` ${JSON.stringify(context)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}] ${message}${contextStr}`;
}

/**
 * Structured logger with level-based filtering.
 *
 * Provides debug, info, warn, and error methods with automatic filtering
 * based on environment (development logs all, production logs only warn/error).
 * All messages include timestamps and optional structured context.
 *
 * @example
 * ```typescript
 * logger.info('User logged in', { userId: '123' });
 * logger.error('Failed to save', new Error('Network timeout'));
 * ```
 */
export const logger = {
  /**
   * Logs a debug message. Only emitted in development mode.
   * @param message - The debug message to log
   * @param context - Optional structured context data
   */
  debug(message: string, context?: LogContext): void {
    if (shouldLog('debug')) {
      console.debug(formatMessage('debug', message, context));
    }
  },

  /**
   * Logs an info message. Only emitted in development mode.
   * @param message - The info message to log
   * @param context - Optional structured context data
   */
  info(message: string, context?: LogContext): void {
    if (shouldLog('info')) {
      console.info(formatMessage('info', message, context));
    }
  },

  /**
   * Logs a warning message. Emitted in both development and production.
   * @param message - The warning message to log
   * @param context - Optional structured context data
   */
  warn(message: string, context?: LogContext): void {
    if (shouldLog('warn')) {
      console.warn(formatMessage('warn', message, context));
    }
  },

  /**
   * Logs an error message with optional error object. Emitted in both development and production.
   * @param message - The error message to log
   * @param error - Optional error object or value to include in context
   * @param context - Optional additional structured context data
   */
  error(message: string, error?: unknown, context?: LogContext): void {
    if (shouldLog('error')) {
      const errorContext = error instanceof Error
        ? { ...context, error: error.message, stack: error.stack }
        : { ...context, error: String(error) };
      console.error(formatMessage('error', message, errorContext));
    }
  },
};
