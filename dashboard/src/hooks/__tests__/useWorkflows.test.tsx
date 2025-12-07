import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWorkflows } from '../useWorkflows';
import { useWorkflowStore } from '../../store/workflowStore';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import type { WorkflowEvent } from '../../types/api';

vi.mock('react-router-dom', () => ({
  useLoaderData: vi.fn(),
  useRevalidator: vi.fn(),
}));

describe('useWorkflows', () => {
  const mockRevalidate = vi.fn();
  const mockRevalidator = {
    state: 'idle' as const,
    revalidate: mockRevalidate,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    useWorkflowStore.setState({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],
    });
    vi.mocked(useRevalidator).mockReturnValue(mockRevalidator);
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return isConnected from store', () => {
    useWorkflowStore.setState({ isConnected: true });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isConnected).toBe(true);
  });

  it('should expose isRevalidating based on revalidator state', () => {
    vi.mocked(useRevalidator).mockReturnValue({
      state: 'loading',
      revalidate: mockRevalidate,
    });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isRevalidating).toBe(true);
  });

  describe('auto-revalidation logic', () => {
    const createEvent = (
      event_type: WorkflowEvent['event_type'],
      timestamp: string
    ): WorkflowEvent => ({
      id: 'evt-1',
      workflow_id: 'wf-1',
      event_type,
      timestamp,
      data: {},
    });

    it.each([
      'workflow_started',
      'workflow_completed',
      'workflow_failed',
    ] as const)('should auto-revalidate on recent %s event', (event_type) => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      const { rerender } = renderHook(() => useWorkflows());

      // Add a recent status event
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent(event_type, now.toISOString())],
          },
        });
        rerender();
      });

      expect(mockRevalidate).toHaveBeenCalledTimes(1);
    });

    it('should NOT revalidate for old status events (>5 seconds)', () => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      const { rerender } = renderHook(() => useWorkflows());

      // Add an old status event (6 seconds ago)
      const oldTimestamp = new Date(now.getTime() - 6000).toISOString();
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent('workflow_completed', oldTimestamp)],
          },
        });
        rerender();
      });

      expect(mockRevalidate).not.toHaveBeenCalled();
    });

    it('should NOT revalidate for non-status events', () => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      const { rerender } = renderHook(() => useWorkflows());

      // Add a non-status event
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent('stage_started', now.toISOString())],
          },
        });
        rerender();
      });

      expect(mockRevalidate).not.toHaveBeenCalled();
    });

    it('should NOT revalidate when revalidator is already loading', () => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      // Mock revalidator as loading
      vi.mocked(useRevalidator).mockReturnValue({
        state: 'loading',
        revalidate: mockRevalidate,
      });

      const { rerender } = renderHook(() => useWorkflows());

      // Add a recent status event
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent('workflow_completed', now.toISOString())],
          },
        });
        rerender();
      });

      expect(mockRevalidate).not.toHaveBeenCalled();
    });

    it('should revalidate when multiple workflows have recent status events', () => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      const { rerender } = renderHook(() => useWorkflows());

      // Add recent status events for multiple workflows
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent('workflow_started', now.toISOString())],
            'wf-2': [createEvent('workflow_completed', now.toISOString())],
          },
        });
        rerender();
      });

      expect(mockRevalidate).toHaveBeenCalledTimes(1);
    });

    it('should revalidate when recent status event is exactly at 5 second boundary', () => {
      const now = new Date('2025-12-06T10:00:00Z');
      vi.setSystemTime(now);

      const { rerender } = renderHook(() => useWorkflows());

      // Add event exactly 4.999 seconds ago (still within 5 second window)
      const boundaryTimestamp = new Date(now.getTime() - 4999).toISOString();
      act(() => {
        useWorkflowStore.setState({
          eventsByWorkflow: {
            'wf-1': [createEvent('workflow_completed', boundaryTimestamp)],
          },
        });
        rerender();
      });

      expect(mockRevalidate).toHaveBeenCalledTimes(1);
    });
  });
});
