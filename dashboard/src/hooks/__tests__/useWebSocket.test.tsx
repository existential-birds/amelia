import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWebSocket } from '../useWebSocket';
import { useWorkflowStore } from '../../store/workflowStore';
import { createMockEvent } from '../../__tests__/fixtures';
import { suppressConsoleLogs } from '@/test/helpers';
import type { WebSocketMessage } from '../../types';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Store instance for test access
    MockWebSocket.instances.push(this);
  }

  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  // Test helpers
  static instances: MockWebSocket[] = [];
  static clearInstances() {
    MockWebSocket.instances = [];
  }
  static getLatestInstance(): MockWebSocket | undefined {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }

  triggerOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  triggerMessage(data: WebSocketMessage) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }

  triggerClose(code = 1000, reason = 'Normal closure') {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }
}

// Install mock
global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

describe('useWebSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.clearInstances();
    vi.useFakeTimers();
    useWorkflowStore.setState({
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
    });
    suppressConsoleLogs();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('should connect to WebSocket on mount', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance();
    expect(ws).toBeDefined();
    expect(ws?.url).toContain('ws://localhost:8420/ws/events');
  });

  it('should set isConnected when connection opens', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    expect(useWorkflowStore.getState().isConnected).toBe(true);
  });

  it('should subscribe to all workflows on connect', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'subscribe_all' })
    );
  });

  it('should handle incoming event messages', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    const event = createMockEvent({
      id: 'evt-1',
      workflow_id: 'wf-123',
      message: 'Workflow started',
    });

    ws.triggerMessage({ type: 'event', payload: event });

    // Events are batched - flush the batch to apply to state
    vi.advanceTimersByTime(100);

    const state = useWorkflowStore.getState();
    expect(state.eventsByWorkflow['wf-123']).toHaveLength(1);
    expect(state.eventsByWorkflow['wf-123']![0]).toEqual(event);
    expect(state.lastEventId).toBe('evt-1');
  });

  it('should respond to ping with pong', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    ws.send.mockClear();
    ws.triggerMessage({ type: 'ping' });

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'pong' }));
  });

  it('should reconnect with exponential backoff on disconnect', () => {
    renderHook(() => useWebSocket());

    const ws1 = MockWebSocket.getLatestInstance()!;
    ws1.triggerOpen();
    ws1.triggerClose(1006, 'Abnormal closure');

    expect(useWorkflowStore.getState().isConnected).toBe(false);

    // First reconnect after 1s
    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances.length).toBe(2);

    const ws2 = MockWebSocket.getLatestInstance()!;
    ws2.triggerClose(1006, 'Abnormal closure');

    // Second reconnect after 2s
    vi.advanceTimersByTime(2000);
    expect(MockWebSocket.instances.length).toBe(3);

    const ws3 = MockWebSocket.getLatestInstance()!;
    ws3.triggerClose(1006, 'Abnormal closure');

    // Third reconnect after 4s
    vi.advanceTimersByTime(4000);
    expect(MockWebSocket.instances.length).toBe(4);
  });

  it('should include since parameter when reconnecting with lastEventId', () => {
    useWorkflowStore.setState({ lastEventId: 'evt-42' });

    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    expect(ws.url).toContain('?since=evt-42');
  });


  it('should handle backfill_expired by clearing lastEventId', () => {
    useWorkflowStore.setState({ lastEventId: 'evt-old' });

    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    ws.triggerMessage({
      type: 'backfill_expired',
      message: 'Events expired',
    });

    expect(useWorkflowStore.getState().lastEventId).toBeNull();
  });

  it('should cap reconnect delay at 30 seconds', () => {
    renderHook(() => useWebSocket());

    // Simulate enough failures to reach the 30s cap (2^5 = 32s would exceed it)
    for (let i = 0; i < 6; i++) {
      const ws = MockWebSocket.getLatestInstance()!;
      if (ws.readyState === MockWebSocket.CONNECTING) {
        ws.triggerOpen();
      }
      ws.triggerClose(1006, 'Abnormal closure');

      const expectedDelay = Math.min(1000 * Math.pow(2, i), 30000);
      vi.advanceTimersByTime(expectedDelay);
    }

    // Verify the final delay is capped at 30s
    const lastWs = MockWebSocket.getLatestInstance()!;
    lastWs.triggerClose(1006, 'Abnormal closure');

    vi.advanceTimersByTime(30000);
    expect(MockWebSocket.instances.length).toBe(8); // 1 initial + 6 reconnects + 1 final
  });

  it('should disconnect WebSocket on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    unmount();

    expect(ws.close).toHaveBeenCalled();
  });

  it('should dispatch custom workflow-event for revalidation hints', () => {
    const eventListener = vi.fn();
    window.addEventListener('workflow-event', eventListener);

    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    const event = createMockEvent({
      id: 'evt-1',
      workflow_id: 'wf-123',
      message: 'Workflow started',
    });

    ws.triggerMessage({ type: 'event', payload: event });

    expect(eventListener).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: event,
      })
    );

    window.removeEventListener('workflow-event', eventListener);
  });

  it('should reset reconnect counter on successful connection', () => {
    renderHook(() => useWebSocket());

    // First connection fails
    const ws1 = MockWebSocket.getLatestInstance()!;
    ws1.triggerOpen();
    ws1.triggerClose(1006, 'Abnormal closure');

    // Reconnect after 1s
    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances.length).toBe(2);

    // Second connection succeeds
    const ws2 = MockWebSocket.getLatestInstance()!;
    ws2.triggerOpen();

    expect(useWorkflowStore.getState().isConnected).toBe(true);

    // Now if it fails again, should restart from 1s (not continue from 2s)
    ws2.triggerClose(1006, 'Abnormal closure');

    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances.length).toBe(3);
  });

  it('should handle backfill_complete message', () => {
    renderHook(() => useWebSocket());

    const ws = MockWebSocket.getLatestInstance()!;
    ws.triggerOpen();

    // Just verify it doesn't crash - logging is implementation detail
    ws.triggerMessage({ type: 'backfill_complete', count: 42 });

    expect(useWorkflowStore.getState().isConnected).toBe(true);
  });
});
