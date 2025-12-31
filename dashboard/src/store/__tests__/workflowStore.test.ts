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
      eventsByWorkflow: {},
      eventIdsByWorkflow: {},
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

    it('should deduplicate events by ID (handles StrictMode double-effect)', () => {
      const event = createMockEvent({
        id: 'evt-duplicate',
        workflow_id: 'wf-1',
        sequence: 1,
        message: 'Starting architect_node',
      });

      // Simulate StrictMode causing duplicate event additions
      useWorkflowStore.getState().addEvent(event);
      useWorkflowStore.getState().addEvent(event); // Same event added again

      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(1);
      expect(events![0]!.id).toBe('evt-duplicate');
    });

    // Verify that adding a duplicate of an EARLIER event doesn't
    // revert lastEventId to the older event's ID
    it('should not update lastEventId when duplicate is skipped', () => {
      const event1 = createMockEvent({
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        message: 'First event',
      });

      const event2 = createMockEvent({
        id: 'evt-2',
        workflow_id: 'wf-1',
        sequence: 2,
        message: 'Second event',
      });

      useWorkflowStore.getState().addEvent(event1);
      useWorkflowStore.getState().addEvent(event2);

      // Try to add duplicate of first event
      useWorkflowStore.getState().addEvent(event1);

      // lastEventId should remain evt-2, not revert to evt-1
      expect(useWorkflowStore.getState().lastEventId).toBe('evt-2');

      // Verify no duplicate was added
      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(2);
    });

    it('should dedupe events with same id from different objects', () => {
      const event1 = createMockEvent({
        id: 'evt-dedupe',
        workflow_id: 'wf-1',
        sequence: 1,
        message: 'Original event',
      });

      // Create distinct object with same id (simulates JSON deserialization)
      const event2 = { ...event1, message: 'Cloned event' };

      // Verify they are different object references
      expect(event1).not.toBe(event2);
      expect(event1.id).toBe(event2.id);

      useWorkflowStore.getState().addEvent(event1);
      useWorkflowStore.getState().addEvent(event2);

      // Should deduplicate by id, not object reference
      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(1);
      expect(events![0]!.message).toBe('Original event');
    });

    it('should allow same event ID across different workflows', () => {
      const event1 = createMockEvent({
        id: 'evt-shared',
        workflow_id: 'wf-1',
        sequence: 1,
        message: 'Event in workflow 1',
      });
      const event2 = createMockEvent({
        id: 'evt-shared',
        workflow_id: 'wf-2',
        sequence: 1,
        message: 'Event in workflow 2',
      });

      useWorkflowStore.getState().addEvent(event1);
      useWorkflowStore.getState().addEvent(event2);

      expect(useWorkflowStore.getState().eventsByWorkflow['wf-1']).toHaveLength(1);
      expect(useWorkflowStore.getState().eventsByWorkflow['wf-2']).toHaveLength(1);
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
    it('should persist lastEventId but NOT events', () => {
      // Add an event to update lastEventId
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

      // Should persist lastEventId
      expect(parsed.state.lastEventId).toBe('evt-999');

      // Should NOT persist events
      expect(parsed.state.eventsByWorkflow).toBeUndefined();
    });
  });
});
