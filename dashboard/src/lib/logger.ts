/**
 * @fileoverview Structured logging utility for the dashboard.
 *
 * Provides consistent log formatting with context and level-based filtering.
 * In production, logs can be suppressed or sent to a logging service.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  [key: string]: unknown;
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

// In production, suppress debug/info logs
const MIN_LOG_LEVEL: LogLevel = import.meta.env.PROD ? 'warn' : 'debug';

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[MIN_LOG_LEVEL];
}

function formatMessage(level: LogLevel, message: string, context?: LogContext): string {
  const timestamp = new Date().toISOString();
  const contextStr = context ? ` ${JSON.stringify(context)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}] ${message}${contextStr}`;
}

/**
 * Structured logger with level-based filtering.
 *
 * In development: all levels are logged.
 * In production: only warn and error are logged.
 */
export const logger = {
  debug(message: string, context?: LogContext): void {
    if (shouldLog('debug')) {
      console.debug(formatMessage('debug', message, context));
    }
  },

  info(message: string, context?: LogContext): void {
    if (shouldLog('info')) {
      console.info(formatMessage('info', message, context));
    }
  },

  warn(message: string, context?: LogContext): void {
    if (shouldLog('warn')) {
      console.warn(formatMessage('warn', message, context));
    }
  },

  error(message: string, error?: unknown, context?: LogContext): void {
    if (shouldLog('error')) {
      const errorContext = error instanceof Error
        ? { ...context, error: error.message, stack: error.stack }
        : { ...context, error: String(error) };
      console.error(formatMessage('error', message, errorContext));
    }
  },
};
