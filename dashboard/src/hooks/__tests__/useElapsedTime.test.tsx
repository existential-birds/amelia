import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useElapsedTime } from '../useElapsedTime';
import { createMockWorkflowDetail } from '../../__tests__/fixtures';
import type { WorkflowDetail } from '../../types';
import * as workflowUtils from '../../utils/workflow';

// Mock formatElapsedTime to track calls and provide controlled output
vi.mock('../../utils/workflow', () => ({
  formatElapsedTime: vi.fn(),
}));

describe('useElapsedTime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('should return formatted time for a workflow', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'completed',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('2h 30m');

    const { result } = renderHook(() => useElapsedTime(workflow));

    expect(result.current).toBe('2h 30m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledWith(workflow);
  });

  it('should return "--:--" for null workflow', () => {
    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('--:--');

    const { result } = renderHook(() => useElapsedTime(null));

    expect(result.current).toBe('--:--');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledWith(null);
  });

  it('should set up interval for in_progress workflows', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'in_progress',
    });

    vi.mocked(workflowUtils.formatElapsedTime)
      .mockReturnValueOnce('2h 30m')  // Initial state
      .mockReturnValueOnce('2h 30m')  // useEffect call
      .mockReturnValueOnce('2h 31m')  // After 60s
      .mockReturnValueOnce('2h 32m'); // After 120s

    const { result } = renderHook(() => useElapsedTime(workflow));

    // Initial render (calls formatElapsedTime twice: useState + useEffect)
    expect(result.current).toBe('2h 30m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Advance time by 60 seconds
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current).toBe('2h 31m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(3);

    // Advance another 60 seconds
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current).toBe('2h 32m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(4);
  });

  it('should NOT set up interval for completed workflows', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      completed_at: '2025-12-06T12:30:00Z',
      status: 'completed',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('2h 30m');

    const { result } = renderHook(() => useElapsedTime(workflow));

    // Initial render (calls formatElapsedTime twice: useState + useEffect)
    expect(result.current).toBe('2h 30m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Advance time by 60 seconds
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    // Should still be the same value - no interval updates
    expect(result.current).toBe('2h 30m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);
  });

  it('should NOT set up interval for blocked workflows', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'blocked',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('1h 15m');

    const { result } = renderHook(() => useElapsedTime(workflow));

    // Initial render (calls formatElapsedTime twice: useState + useEffect)
    expect(result.current).toBe('1h 15m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Advance time by 60 seconds
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    // Should still be the same value - no interval updates
    expect(result.current).toBe('1h 15m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);
  });

  it('should NOT set up interval for failed workflows', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'failed',
      failure_reason: 'Test error',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('0h 45m');

    const { result } = renderHook(() => useElapsedTime(workflow));

    // Initial render (calls formatElapsedTime twice: useState + useEffect)
    expect(result.current).toBe('0h 45m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Advance time by 60 seconds
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    // Should still be the same value - no interval updates
    expect(result.current).toBe('0h 45m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);
  });

  it('should clean up interval on unmount', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'in_progress',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('1h 00m');

    const { unmount } = renderHook(() => useElapsedTime(workflow));

    // Initial render sets up interval (calls formatElapsedTime twice: useState + useEffect)
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Unmount should clear the interval
    unmount();

    // Advance time - should not trigger any more calls
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);
  });

  it('should re-compute immediately when workflow changes', () => {
    const workflow1 = createMockWorkflowDetail({
      id: 'wf-1',
      started_at: '2025-12-06T10:00:00Z',
      status: 'in_progress',
    });

    const workflow2 = createMockWorkflowDetail({
      id: 'wf-2',
      started_at: '2025-12-06T09:00:00Z',
      status: 'completed',
      completed_at: '2025-12-06T11:30:00Z',
    });

    vi.mocked(workflowUtils.formatElapsedTime)
      .mockReturnValueOnce('1h 00m')  // workflow1 initial state
      .mockReturnValueOnce('1h 00m')  // workflow1 useEffect
      .mockReturnValueOnce('2h 30m')  // workflow2 useEffect
      .mockReturnValueOnce('2h 30m'); // workflow2 (if needed)

    const { result, rerender } = renderHook(
      ({ workflow }) => useElapsedTime(workflow),
      { initialProps: { workflow: workflow1 } }
    );

    // Initial render with workflow1
    expect(result.current).toBe('1h 00m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledWith(workflow1);

    // Re-render with workflow2
    act(() => {
      rerender({ workflow: workflow2 });
    });

    // Should immediately update to workflow2's elapsed time
    expect(result.current).toBe('2h 30m');
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledWith(workflow2);
  });

  it('should clear interval when workflow changes from in_progress to completed', () => {
    const inProgressWorkflow = createMockWorkflowDetail({
      id: 'wf-1',
      started_at: '2025-12-06T10:00:00Z',
      status: 'in_progress',
    });

    const completedWorkflow = createMockWorkflowDetail({
      id: 'wf-1',
      started_at: '2025-12-06T10:00:00Z',
      completed_at: '2025-12-06T12:30:00Z',
      status: 'completed',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('1h 00m');

    const { rerender } = renderHook(
      ({ workflow }) => useElapsedTime(workflow),
      { initialProps: { workflow: inProgressWorkflow } }
    );

    // Initial render - interval should be set up
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Change to completed
    rerender({ workflow: completedWorkflow });

    // After rerender, useEffect should have run
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(3);

    // Advance time - should not trigger any more calls (interval cleared)
    vi.clearAllMocks();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(workflowUtils.formatElapsedTime).not.toHaveBeenCalled();
  });

  it('should handle workflow changing to null', () => {
    const workflow = createMockWorkflowDetail({
      started_at: '2025-12-06T10:00:00Z',
      status: 'in_progress',
    });

    vi.mocked(workflowUtils.formatElapsedTime).mockReturnValue('1h 00m');

    const { rerender } = renderHook<
      string,
      { workflow: WorkflowDetail | null }
    >(({ workflow }) => useElapsedTime(workflow), {
      initialProps: { workflow },
    });

    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(2);

    // Change to null
    rerender({ workflow: null });

    // After rerender, useEffect should have run
    expect(workflowUtils.formatElapsedTime).toHaveBeenCalledTimes(3);

    // Advance time - should not trigger any more calls
    vi.clearAllMocks();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(workflowUtils.formatElapsedTime).not.toHaveBeenCalled();
  });
});
