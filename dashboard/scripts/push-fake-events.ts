/**
 * Script to push fake workflow events to the activity log for testing.
 * Run with: npx tsx scripts/push-fake-events.ts
 */

// Fake events covering all agent types and stages
const fakeEvents = [
  // Workflow start
  {
    id: 'evt-001',
    workflow_id: 'test-workflow-1',
    sequence: 1,
    timestamp: new Date(Date.now() - 300000).toISOString(),
    agent: 'system',
    event_type: 'workflow_started',
    level: 'info',
    message: 'Workflow execution started',
  },
  // Architect stage
  {
    id: 'evt-002',
    workflow_id: 'test-workflow-1',
    sequence: 2,
    timestamp: new Date(Date.now() - 290000).toISOString(),
    agent: 'system',
    event_type: 'stage_started',
    level: 'info',
    message: 'Starting architect_node',
  },
  {
    id: 'evt-003',
    workflow_id: 'test-workflow-1',
    sequence: 3,
    timestamp: new Date(Date.now() - 280000).toISOString(),
    agent: 'architect',
    event_type: 'agent_message',
    level: 'info',
    message: 'Analyzing issue requirements and codebase structure',
  },
  {
    id: 'evt-004',
    workflow_id: 'test-workflow-1',
    sequence: 4,
    timestamp: new Date(Date.now() - 270000).toISOString(),
    agent: 'architect',
    event_type: 'agent_message',
    level: 'debug',
    message: 'Created implementation plan with 5 tasks covering authentication flow, API endpoints, and UI components',
  },
  {
    id: 'evt-005',
    workflow_id: 'test-workflow-1',
    sequence: 5,
    timestamp: new Date(Date.now() - 260000).toISOString(),
    agent: 'system',
    event_type: 'stage_completed',
    level: 'info',
    message: 'Completed architect_node',
  },
  // Plan validator
  {
    id: 'evt-006',
    workflow_id: 'test-workflow-1',
    sequence: 6,
    timestamp: new Date(Date.now() - 250000).toISOString(),
    agent: 'system',
    event_type: 'stage_started',
    level: 'info',
    message: 'Starting plan_validator_node',
  },
  {
    id: 'evt-007',
    workflow_id: 'test-workflow-1',
    sequence: 7,
    timestamp: new Date(Date.now() - 240000).toISOString(),
    agent: 'validator',
    event_type: 'agent_message',
    level: 'info',
    message: 'Plan validated: Migrate the portfolio website from Gatsby v5.3.3 to Hugo while preserving all content, metadata, and S3 deployment capabilities, reducing build times and eliminating complex Node.js dependencies.',
  },
  {
    id: 'evt-008',
    workflow_id: 'test-workflow-1',
    sequence: 8,
    timestamp: new Date(Date.now() - 230000).toISOString(),
    agent: 'system',
    event_type: 'stage_completed',
    level: 'info',
    message: 'Completed plan_validator_node',
  },
  // Human approval
  {
    id: 'evt-009',
    workflow_id: 'test-workflow-1',
    sequence: 9,
    timestamp: new Date(Date.now() - 220000).toISOString(),
    agent: 'system',
    event_type: 'stage_started',
    level: 'info',
    message: 'Starting human_approval_node',
  },
  {
    id: 'evt-010',
    workflow_id: 'test-workflow-1',
    sequence: 10,
    timestamp: new Date(Date.now() - 210000).toISOString(),
    agent: 'human_approval',
    event_type: 'approval_required',
    level: 'info',
    message: 'Plan ready for review - awaiting human approval',
  },
  {
    id: 'evt-011',
    workflow_id: 'test-workflow-1',
    sequence: 11,
    timestamp: new Date(Date.now() - 200000).toISOString(),
    agent: 'human_approval',
    event_type: 'approval_granted',
    level: 'info',
    message: 'Plan approved',
  },
  {
    id: 'evt-012',
    workflow_id: 'test-workflow-1',
    sequence: 12,
    timestamp: new Date(Date.now() - 190000).toISOString(),
    agent: 'system',
    event_type: 'stage_completed',
    level: 'info',
    message: 'Completed human_approval_node',
  },
  // Developer stage
  {
    id: 'evt-013',
    workflow_id: 'test-workflow-1',
    sequence: 13,
    timestamp: new Date(Date.now() - 180000).toISOString(),
    agent: 'system',
    event_type: 'stage_started',
    level: 'info',
    message: 'Starting developer_node',
  },
  {
    id: 'evt-014',
    workflow_id: 'test-workflow-1',
    sequence: 14,
    timestamp: new Date(Date.now() - 170000).toISOString(),
    agent: 'developer',
    event_type: 'task_started',
    level: 'info',
    message: 'Starting task: Set up Hugo project structure',
  },
  {
    id: 'evt-015',
    workflow_id: 'test-workflow-1',
    sequence: 15,
    timestamp: new Date(Date.now() - 160000).toISOString(),
    agent: 'developer',
    event_type: 'file_created',
    level: 'debug',
    message: 'Created config.toml with site configuration',
  },
  {
    id: 'evt-016',
    workflow_id: 'test-workflow-1',
    sequence: 16,
    timestamp: new Date(Date.now() - 150000).toISOString(),
    agent: 'developer',
    event_type: 'task_completed',
    level: 'info',
    message: 'Completed task: Set up Hugo project structure',
  },
  {
    id: 'evt-017',
    workflow_id: 'test-workflow-1',
    sequence: 17,
    timestamp: new Date(Date.now() - 140000).toISOString(),
    agent: 'developer',
    event_type: 'agent_message',
    level: 'debug',
    message: 'Migrating content from Gatsby GraphQL queries to Hugo front matter format. This involves converting all .mdx files to standard .md with YAML front matter.',
  },
  {
    id: 'evt-018',
    workflow_id: 'test-workflow-1',
    sequence: 18,
    timestamp: new Date(Date.now() - 130000).toISOString(),
    agent: 'system',
    event_type: 'stage_completed',
    level: 'info',
    message: 'Completed developer_node',
  },
  // Reviewer stage
  {
    id: 'evt-019',
    workflow_id: 'test-workflow-1',
    sequence: 19,
    timestamp: new Date(Date.now() - 120000).toISOString(),
    agent: 'system',
    event_type: 'stage_started',
    level: 'info',
    message: 'Starting reviewer_node',
  },
  {
    id: 'evt-020',
    workflow_id: 'test-workflow-1',
    sequence: 20,
    timestamp: new Date(Date.now() - 110000).toISOString(),
    agent: 'reviewer',
    event_type: 'review_requested',
    level: 'info',
    message: 'Reviewing implementation changes',
  },
  {
    id: 'evt-021',
    workflow_id: 'test-workflow-1',
    sequence: 21,
    timestamp: new Date(Date.now() - 100000).toISOString(),
    agent: 'reviewer',
    event_type: 'agent_message',
    level: 'debug',
    message: 'Found 2 issues: missing alt text on images, unused CSS import. Requesting revision.',
  },
  {
    id: 'evt-022',
    workflow_id: 'test-workflow-1',
    sequence: 22,
    timestamp: new Date(Date.now() - 90000).toISOString(),
    agent: 'reviewer',
    event_type: 'revision_requested',
    level: 'info',
    message: 'Changes need revision - see feedback',
  },
  {
    id: 'evt-023',
    workflow_id: 'test-workflow-1',
    sequence: 23,
    timestamp: new Date(Date.now() - 80000).toISOString(),
    agent: 'system',
    event_type: 'stage_completed',
    level: 'info',
    message: 'Completed reviewer_node',
  },
  // Workflow complete
  {
    id: 'evt-024',
    workflow_id: 'test-workflow-1',
    sequence: 24,
    timestamp: new Date(Date.now() - 70000).toISOString(),
    agent: 'system',
    event_type: 'workflow_completed',
    level: 'info',
    message: 'Workflow completed successfully',
  },
];

// WebSocket connection to send events
async function pushEvents() {
  const ws = new WebSocket('ws://localhost:8420/api/ws');

  ws.onopen = () => {
    console.log('Connected to WebSocket');

    // Subscribe to all workflows
    ws.send(JSON.stringify({ type: 'subscribe_all' }));

    // Push events with delay between each
    let index = 0;
    const interval = setInterval(() => {
      if (index >= fakeEvents.length) {
        clearInterval(interval);
        console.log('All events pushed');
        ws.close();
        return;
      }

      const event = fakeEvents[index];
      console.log(`Pushing event ${index + 1}/${fakeEvents.length}: ${event.agent} - ${event.message}`);

      // Send as event message
      ws.send(JSON.stringify({
        type: 'event',
        payload: event,
      }));

      index++;
    }, 500);
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
  };
}

// For browser console injection (simpler approach)
console.log('=== Fake Events for Activity Log Testing ===');
console.log('Copy this to inject into the workflow store:');
console.log('');
console.log(`
// Paste in browser console while on the dashboard
const fakeEvents = ${JSON.stringify(fakeEvents, null, 2)};

// Access the workflow store and add events
const store = window.__ZUSTAND_STORE__;
if (store) {
  fakeEvents.forEach(event => {
    store.getState().addEvent(event);
  });
  console.log('Events injected!');
} else {
  console.log('Store not found. Try: localStorage.setItem("debug-events", JSON.stringify(fakeEvents))');
}
`);

export { fakeEvents };
