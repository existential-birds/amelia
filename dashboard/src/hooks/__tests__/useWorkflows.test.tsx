import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWorkflows } from '../useWorkflows';
import { useWorkflowStore } from '../../store/workflowStore';
import { useLoaderData, useRevalidator } from 'react-router-dom';

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
    useWorkflowStore.setState({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],
    });
    vi.mocked(useRevalidator).mockReturnValue(mockRevalidator);
  });

  it('should return workflows from loader data', () => {
    const mockWorkflows = [
      {
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_name: 'main',
        status: 'in_progress' as const,
        started_at: '2025-12-01T10:00:00Z',
        current_stage: 'architect',
      },
    ];

    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.workflows).toEqual(mockWorkflows);
    expect(result.current.isConnected).toBe(false);
  });

  it('should return connection state from Zustand store', () => {
    useWorkflowStore.setState({ isConnected: true });
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isConnected).toBe(true);
  });

  it('should provide revalidation state', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });
    vi.mocked(useRevalidator).mockReturnValue({
      state: 'loading',
      revalidate: mockRevalidate,
    });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isRevalidating).toBe(true);
  });

  it('should provide manual revalidate function', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    const { result } = renderHook(() => useWorkflows());

    result.current.revalidate();

    expect(mockRevalidate).toHaveBeenCalled();
  });
});
