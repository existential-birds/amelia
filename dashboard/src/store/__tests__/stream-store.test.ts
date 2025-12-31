import { describe, it, expect, beforeEach } from 'vitest';
import { useStreamStore } from '../stream-store';
import { StreamEventType } from '../../types';
import { createMockStreamEvent } from '../../__tests__/fixtures';

describe('streamStore', () => {
  beforeEach(() => {
    useStreamStore.setState({
      events: [],
      liveMode: false,
      maxEvents: 1000,
    });
  });

  describe('initial state', () => {
    it('should have empty events array', () => {
      const state = useStreamStore.getState();
      expect(state.events).toEqual([]);
    });

    it('should have liveMode disabled by default', () => {
      const state = useStreamStore.getState();
      expect(state.liveMode).toBe(false);
    });

    it('should have maxEvents set to 1000', () => {
      const state = useStreamStore.getState();
      expect(state.maxEvents).toBe(1000);
    });
  });

  describe('addEvent', () => {
    it('should add event to events array', () => {
      const event = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_THINKING,
        content: 'Analyzing requirements...',
      });

      useStreamStore.getState().addEvent(event);

      const state = useStreamStore.getState();
      expect(state.events).toHaveLength(1);
      expect(state.events[0]).toEqual(event);
    });

    it('should append to existing events maintaining order', () => {
      const event1 = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_THINKING,
        content: 'First thought',
        timestamp: '2025-12-13T10:00:00Z',
      });

      const event2 = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_TOOL_CALL,
        content: null,
        tool_name: 'read_file',
        tool_input: { path: '/src/main.py' },
        timestamp: '2025-12-13T10:00:01Z',
      });

      const event3 = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_TOOL_RESULT,
        content: 'File contents...',
        timestamp: '2025-12-13T10:00:02Z',
      });

      useStreamStore.getState().addEvent(event1);
      useStreamStore.getState().addEvent(event2);
      useStreamStore.getState().addEvent(event3);

      const events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);
      expect(events[0]).toEqual(event1);
      expect(events[1]).toEqual(event2);
      expect(events[2]).toEqual(event3);
    });

    it('should handle different event types correctly', () => {
      const thinkingEvent = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_THINKING,
        content: 'Thinking...',
        tool_name: null,
        tool_input: null,
      });

      const toolCallEvent = createMockStreamEvent({
        subtype: StreamEventType.CLAUDE_TOOL_CALL,
        content: null,
        tool_name: 'execute_command',
        tool_input: { command: 'ls -la' },
      });

      const agentOutputEvent = createMockStreamEvent({
        subtype: StreamEventType.AGENT_OUTPUT,
        content: 'Task completed successfully',
        tool_name: null,
        tool_input: null,
      });

      useStreamStore.getState().addEvent(thinkingEvent);
      useStreamStore.getState().addEvent(toolCallEvent);
      useStreamStore.getState().addEvent(agentOutputEvent);

      const events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);
      expect(events[0]!.subtype).toBe(StreamEventType.CLAUDE_THINKING);
      expect(events[1]!.subtype).toBe(StreamEventType.CLAUDE_TOOL_CALL);
      expect(events[2]!.subtype).toBe(StreamEventType.AGENT_OUTPUT);
    });

    it('should respect maxEvents limit (buffer overflow)', () => {
      // Set maxEvents to 5 for easier testing
      useStreamStore.setState({ maxEvents: 5 });

      // Add 7 events (exceeds limit by 2)
      for (let i = 1; i <= 7; i++) {
        const event = createMockStreamEvent({
          content: `Event ${i}`,
          timestamp: `2025-12-13T10:00:${i.toString().padStart(2, '0')}Z`,
        });
        useStreamStore.getState().addEvent(event);
      }

      const events = useStreamStore.getState().events;
      expect(events).toHaveLength(5);

      // Should keep most recent (events 3-7, dropping 1-2)
      expect(events[0]!.content).toBe('Event 3');
      expect(events[1]!.content).toBe('Event 4');
      expect(events[2]!.content).toBe('Event 5');
      expect(events[3]!.content).toBe('Event 6');
      expect(events[4]!.content).toBe('Event 7');
    });

    it('should trim oldest events when buffer is full', () => {
      // Set maxEvents to 3
      useStreamStore.setState({ maxEvents: 3 });

      // Add 3 events (fills buffer)
      const event1 = createMockStreamEvent({ content: 'Event 1' });
      const event2 = createMockStreamEvent({ content: 'Event 2' });
      const event3 = createMockStreamEvent({ content: 'Event 3' });

      useStreamStore.getState().addEvent(event1);
      useStreamStore.getState().addEvent(event2);
      useStreamStore.getState().addEvent(event3);

      let events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);

      // Add one more event - should drop event1
      const event4 = createMockStreamEvent({ content: 'Event 4' });
      useStreamStore.getState().addEvent(event4);

      events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);
      expect(events[0]!.content).toBe('Event 2');
      expect(events[1]!.content).toBe('Event 3');
      expect(events[2]!.content).toBe('Event 4');
    });

    it('should handle events from different workflows', () => {
      const event1 = createMockStreamEvent({
        workflow_id: 'wf-1',
        content: 'Workflow 1 event',
      });

      const event2 = createMockStreamEvent({
        workflow_id: 'wf-2',
        content: 'Workflow 2 event',
      });

      const event3 = createMockStreamEvent({
        workflow_id: 'wf-1',
        content: 'Another workflow 1 event',
      });

      useStreamStore.getState().addEvent(event1);
      useStreamStore.getState().addEvent(event2);
      useStreamStore.getState().addEvent(event3);

      const events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);
      expect(events.filter(e => e.workflow_id === 'wf-1')).toHaveLength(2);
      expect(events.filter(e => e.workflow_id === 'wf-2')).toHaveLength(1);
    });

    it('should handle events from different agents', () => {
      const architectEvent = createMockStreamEvent({
        agent: 'architect',
        content: 'Planning...',
      });

      const developerEvent = createMockStreamEvent({
        agent: 'developer',
        content: 'Implementing...',
      });

      const reviewerEvent = createMockStreamEvent({
        agent: 'reviewer',
        content: 'Reviewing...',
      });

      useStreamStore.getState().addEvent(architectEvent);
      useStreamStore.getState().addEvent(developerEvent);
      useStreamStore.getState().addEvent(reviewerEvent);

      const events = useStreamStore.getState().events;
      expect(events).toHaveLength(3);
      expect(events[0]!.agent).toBe('architect');
      expect(events[1]!.agent).toBe('developer');
      expect(events[2]!.agent).toBe('reviewer');
    });
  });

  describe('setLiveMode', () => {
    it('should enable live mode', () => {
      useStreamStore.getState().setLiveMode(true);

      const state = useStreamStore.getState();
      expect(state.liveMode).toBe(true);
    });

    it('should disable live mode', () => {
      // First enable it
      useStreamStore.setState({ liveMode: true });

      // Then disable it
      useStreamStore.getState().setLiveMode(false);

      const state = useStreamStore.getState();
      expect(state.liveMode).toBe(false);
    });

    it('should toggle live mode multiple times', () => {
      let state = useStreamStore.getState();
      expect(state.liveMode).toBe(false);

      useStreamStore.getState().setLiveMode(true);
      state = useStreamStore.getState();
      expect(state.liveMode).toBe(true);

      useStreamStore.getState().setLiveMode(false);
      state = useStreamStore.getState();
      expect(state.liveMode).toBe(false);

      useStreamStore.getState().setLiveMode(true);
      state = useStreamStore.getState();
      expect(state.liveMode).toBe(true);
    });
  });

  describe('clearEvents', () => {
    it('should empty the events array', () => {
      // Add some events first
      const event1 = createMockStreamEvent({ content: 'Event 1' });
      const event2 = createMockStreamEvent({ content: 'Event 2' });
      const event3 = createMockStreamEvent({ content: 'Event 3' });

      useStreamStore.getState().addEvent(event1);
      useStreamStore.getState().addEvent(event2);
      useStreamStore.getState().addEvent(event3);

      expect(useStreamStore.getState().events).toHaveLength(3);

      // Clear all events
      useStreamStore.getState().clearEvents();

      const state = useStreamStore.getState();
      expect(state.events).toEqual([]);
      expect(state.events).toHaveLength(0);
    });

    it('should not affect other state properties', () => {
      // Set up some state
      useStreamStore.setState({
        events: [createMockStreamEvent()],
        liveMode: true,
        maxEvents: 500,
      });

      // Clear events
      useStreamStore.getState().clearEvents();

      const state = useStreamStore.getState();
      expect(state.events).toHaveLength(0);
      expect(state.liveMode).toBe(true);
      expect(state.maxEvents).toBe(500);
    });

    it('should work on already empty array', () => {
      expect(useStreamStore.getState().events).toHaveLength(0);

      useStreamStore.getState().clearEvents();

      expect(useStreamStore.getState().events).toHaveLength(0);
    });
  });
});
