import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkflowStore } from '../workflowStore';
import { createMockEvent } from '../../__tests__/fixtures';

// Mock sessionStorage
const sessionStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'sessionStorage', { value: sessionStorageMock });

describe('workflowStore', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],
    });
    sessionStorageMock.clear();
  });


  describe('addEvent', () => {
    it('should add event to workflow event list', () => {
      const event = createMockEvent({
        id: 'evt-1',
        workflow_id: 'wf-1',
        message: 'Workflow started',
      });

      useWorkflowStore.getState().addEvent(event);

      const state = useWorkflowStore.getState();
      expect(state.eventsByWorkflow['wf-1']).toHaveLength(1);
      expect(state.eventsByWorkflow['wf-1']![0]).toEqual(event);
      expect(state.lastEventId).toBe('evt-1');
    });

    it('should append to existing events', () => {
      const event1 = createMockEvent({
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        message: 'Started',
      });

      const event2 = createMockEvent({
        id: 'evt-2',
        workflow_id: 'wf-1',
        sequence: 2,
        event_type: 'stage_started',
        message: 'Planning',
        data: { stage: 'architect' },
      });

      useWorkflowStore.getState().addEvent(event1);
      useWorkflowStore.getState().addEvent(event2);

      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(2);
      expect(events![0]!.id).toBe('evt-1');
      expect(events![1]!.id).toBe('evt-2');
    });

    it('should trim events when exceeding MAX_EVENTS_PER_WORKFLOW', () => {
      const MAX_EVENTS = 500;

      // Add 501 events
      for (let i = 1; i <= MAX_EVENTS + 1; i++) {
        const event = createMockEvent({
          id: `evt-${i}`,
          workflow_id: 'wf-1',
          sequence: i,
          event_type: 'stage_started',
          message: `Event ${i}`,
        });
        useWorkflowStore.getState().addEvent(event);
      }

      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(MAX_EVENTS);
      // Should keep most recent (evt-2 to evt-501, dropping evt-1)
      expect(events![0]!.id).toBe('evt-2');
      expect(events![MAX_EVENTS - 1]!.id).toBe(`evt-${MAX_EVENTS + 1}`);
    });
  });

  describe('connection state', () => {
    it('should update connection status', () => {
      useWorkflowStore.getState().setConnected(true);

      expect(useWorkflowStore.getState().isConnected).toBe(true);
      expect(useWorkflowStore.getState().connectionError).toBeNull();
    });

    it('should set error when disconnected', () => {
      useWorkflowStore.getState().setConnected(false, 'Connection lost');

      expect(useWorkflowStore.getState().isConnected).toBe(false);
      expect(useWorkflowStore.getState().connectionError).toBe('Connection lost');
    });
  });

  describe('pending actions', () => {
    it('should add pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.includes('approve-wf-1')).toBe(true);
    });

    it('should not duplicate pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().addPendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.length).toBe(1);
    });

    it('should remove pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().removePendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.length).toBe(0);
    });
  });

  describe('persistence', () => {
    it('should persist selectedWorkflowId and lastEventId but NOT events', () => {
      // Update both selectedWorkflowId and add an event
      useWorkflowStore.getState().selectWorkflow('wf-123');
      useWorkflowStore.getState().addEvent(
        createMockEvent({
          id: 'evt-999',
          workflow_id: 'wf-1',
          message: 'Started',
        })
      );

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored!);

      // Should persist selectedWorkflowId
      expect(parsed.state.selectedWorkflowId).toBe('wf-123');

      // Should persist lastEventId
      expect(parsed.state.lastEventId).toBe('evt-999');

      // Should NOT persist events
      expect(parsed.state.eventsByWorkflow).toBeUndefined();
    });
  });
});
