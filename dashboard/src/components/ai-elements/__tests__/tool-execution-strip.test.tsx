import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ToolExecutionStrip } from '../tool-execution-strip';
import type { ToolCall } from '@/types/api';

function createToolCall(overrides?: Partial<ToolCall> & { index?: number }): ToolCall {
  const index = overrides?.index ?? 0;
  return {
    tool_call_id: `tool-${index}`,
    tool_name: `test_tool_${index}`,
    input: {},
    state: 'output-available',
    ...overrides,
  };
}

describe('ToolExecutionStrip', () => {
  describe('pip visibility', () => {
    it('renders pips only for non-completed tool calls', () => {
      const toolCalls = [
        createToolCall({ index: 0, state: 'output-available' }),
        createToolCall({ index: 1, state: 'input-available' }),
        createToolCall({ index: 2, state: 'output-available' }),
        createToolCall({ index: 3, state: 'output-error' }),
      ];

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      const list = screen.getByRole('list', { name: 'Tool execution status' });
      const pips = list.querySelectorAll('span.rounded-full');
      expect(pips).toHaveLength(2);
    });

    it('renders pips for failed tool calls', () => {
      const toolCalls = [
        createToolCall({ index: 0, state: 'output-available' }),
        createToolCall({ index: 1, state: 'output-error' }),
        createToolCall({ index: 2, state: 'output-available' }),
      ];

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      const list = screen.getByRole('list', { name: 'Tool execution status' });
      const pips = list.querySelectorAll('span.rounded-full');
      expect(pips).toHaveLength(1);
    });

    it('renders no pips when all tool calls are completed', () => {
      const toolCalls = [
        createToolCall({ index: 0, state: 'output-available' }),
        createToolCall({ index: 1, state: 'output-available' }),
        createToolCall({ index: 2, state: 'output-available' }),
      ];

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      const list = screen.getByRole('list', { name: 'Tool execution status' });
      const pips = list.querySelectorAll('span.rounded-full');
      expect(pips).toHaveLength(0);
    });

    it('renders pips for all tool calls when none are completed', () => {
      const toolCalls = [
        createToolCall({ index: 0, state: 'input-available' }),
        createToolCall({ index: 1, state: 'input-available' }),
        createToolCall({ index: 2, state: 'output-error' }),
      ];

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      const list = screen.getByRole('list', { name: 'Tool execution status' });
      const pips = list.querySelectorAll('span.rounded-full');
      expect(pips).toHaveLength(3);
    });
  });

  describe('pip cap', () => {
    it('caps visible pips at 10 even with more active tool calls', () => {
      const toolCalls = Array.from({ length: 15 }, (_, i) =>
        createToolCall({ index: i, state: 'input-available' }),
      );

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      const list = screen.getByRole('list', { name: 'Tool execution status' });
      const pips = list.querySelectorAll('span.rounded-full');
      expect(pips).toHaveLength(10);
    });
  });

  describe('summary stats', () => {
    it('shows total count reflecting all tools including completed', () => {
      const toolCalls = [
        createToolCall({ index: 0, state: 'output-available' }),
        createToolCall({ index: 1, state: 'output-available' }),
        createToolCall({ index: 2, state: 'input-available' }),
      ];

      render(<ToolExecutionStrip toolCalls={toolCalls} />);

      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('tools')).toBeInTheDocument();
    });
  });
});
