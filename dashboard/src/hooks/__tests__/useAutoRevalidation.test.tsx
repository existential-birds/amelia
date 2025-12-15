/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { renderHook } from '@testing-library/react';
import { useAutoRevalidation } from '../useAutoRevalidation';
import { useRevalidator } from 'react-router-dom';
import { useWorkflowStore } from '../../store/workflowStore';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('react-router-dom', () => ({
  useRevalidator: vi.fn(),
}));

vi.mock('../../store/workflowStore', () => ({
  useWorkflowStore: vi.fn(),
}));

describe('useAutoRevalidation', () => {
  const mockRevalidate = vi.fn();
  const mockRevalidator = {
    revalidate: mockRevalidate,
    state: 'idle' as const,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRevalidator).mockReturnValue(mockRevalidator);
    vi.mocked(useWorkflowStore).mockReturnValue({ eventsByWorkflow: {} });
  });

  it('should not revalidate when there are no events', () => {
    renderHook(() => useAutoRevalidation());
    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it('should not revalidate for non-status events', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'system_info',
            timestamp: new Date().toISOString(),
            message: 'Some info',
            sequence: 1,
          },
        ],
      },
    });

    renderHook(() => useAutoRevalidation());
    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it.each([
    'approval_required',
    'approval_granted',
    'approval_rejected',
    'workflow_completed',
    'workflow_failed',
    'workflow_started',
  ] as const)('should auto-revalidate on recent %s event', (event_type) => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type,
            timestamp: new Date().toISOString(),
            message: 'Status changed',
            sequence: 1,
          },
        ],
      },
    });

    const { rerender } = renderHook(() => useAutoRevalidation());
    rerender();
    expect(mockRevalidate).toHaveBeenCalled();
  });

  it('should NOT revalidate for old status events (>5 seconds)', () => {
    const oldTimestamp = new Date(Date.now() - 6000).toISOString();
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'approval_required',
            timestamp: oldTimestamp,
            message: 'Old event',
            sequence: 1,
          },
        ],
      },
    });

    renderHook(() => useAutoRevalidation());
    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it('should NOT revalidate when revalidator is already loading', () => {
    vi.mocked(useRevalidator).mockReturnValue({
      ...mockRevalidator,
      state: 'loading',
    });
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'approval_required',
            timestamp: new Date().toISOString(),
            message: 'Needs approval',
            sequence: 1,
          },
        ],
      },
    });

    const { rerender } = renderHook(() => useAutoRevalidation());
    rerender();
    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it('should filter events by workflowId when provided', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'approval_required',
            timestamp: new Date().toISOString(),
            message: 'Needs approval',
            sequence: 1,
          },
        ],
        'wf-2': [
          {
            id: 'evt-2',
            workflow_id: 'wf-2',
            event_type: 'system_info',
            timestamp: new Date().toISOString(),
            message: 'Info',
            sequence: 1,
          },
        ],
      },
    });

    // Should revalidate when filtering by wf-1 (has approval_required)
    const { rerender } = renderHook(() => useAutoRevalidation('wf-1'));
    rerender();
    expect(mockRevalidate).toHaveBeenCalled();
  });

  it('should NOT revalidate when filtering by workflow with no status events', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'approval_required',
            timestamp: new Date().toISOString(),
            message: 'Needs approval',
            sequence: 1,
          },
        ],
        'wf-2': [
          {
            id: 'evt-2',
            workflow_id: 'wf-2',
            event_type: 'system_info',
            timestamp: new Date().toISOString(),
            message: 'Info',
            sequence: 1,
          },
        ],
      },
    });

    // Should NOT revalidate when filtering by wf-2 (has only system_info)
    renderHook(() => useAutoRevalidation('wf-2'));
    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it('should handle undefined workflowId gracefully', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            event_type: 'approval_required',
            timestamp: new Date().toISOString(),
            message: 'Needs approval',
            sequence: 1,
          },
        ],
      },
    });

    // Should handle undefined by watching all workflows
    const { rerender } = renderHook(() => useAutoRevalidation(undefined));
    rerender();
    expect(mockRevalidate).toHaveBeenCalled();
  });
});
