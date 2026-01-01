/**
 * Mock data for "Infinite Mode" demo feature.
 * Theme: "Phase ∞: The Great Departure" - Amelia gradually preparing to leave Earth.
 *
 * This file generates deterministic mock workflow data for demo purposes.
 * All timestamps and IDs are static to ensure consistent demos.
 */

import type {
  WorkflowSummary,
  WorkflowDetail,
  WorkflowEvent,
  TokenSummary,
  TokenUsage,
} from '@/types';

/**
 * Internal mock plan structure for generating plan_markdown.
 * Not exported - used only within this file.
 */
interface MockPlanBatch {
  batch_number: number;
  description: string;
  risk_summary: string;
  steps: { id: string; description: string; action_type: string; file_path?: string }[];
}

interface MockPlan {
  goal: string;
  batches: MockPlanBatch[];
  total_estimated_minutes: number;
  tdd_approach: boolean;
}

/**
 * Converts a MockPlan to a markdown string for plan_markdown field.
 */
function planToMarkdown(plan: MockPlan): string {
  let md = `# Implementation Plan\n\n**Goal:** ${plan.goal}\n\n`;
  md += `**Estimated time:** ${plan.total_estimated_minutes} minutes\n`;
  md += `**TDD approach:** ${plan.tdd_approach ? 'Yes' : 'No'}\n\n`;

  for (const batch of plan.batches) {
    md += `## Batch ${batch.batch_number}: ${batch.description}\n\n`;
    md += `**Risk:** ${batch.risk_summary}\n\n`;
    for (const step of batch.steps) {
      md += `- ${step.description}`;
      if (step.file_path) {
        md += ` (\`${step.file_path}\`)`;
      }
      md += '\n';
    }
    md += '\n';
  }

  return md;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Generate a deterministic UUID from a string seed.
 * Uses a simple hash to create consistent UUIDs for demos.
 */
function generateUUID(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash = hash & hash;
  }
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return `${hex.slice(0, 8)}-${hex.slice(0, 4)}-4${hex.slice(0, 3)}-a${hex.slice(0, 3)}-${hex.slice(0, 12)}`;
}

/**
 * Get a deterministic timestamp relative to now.
 * @param hoursAgo - How many hours before now
 * @param minutesOffset - Additional minutes offset
 */
function getTimestamp(hoursAgo: number, minutesOffset: number = 0): string {
  const now = new Date();
  const timestamp = new Date(
    now.getTime() - hoursAgo * 60 * 60 * 1000 - minutesOffset * 60 * 1000
  );
  return timestamp.toISOString();
}

/**
 * Get a deterministic timestamp for past workflows.
 * @param daysAgo - How many days before now
 */
function getPastTimestamp(daysAgo: number): string {
  const now = new Date();
  const timestamp = new Date(now.getTime() - daysAgo * 24 * 60 * 60 * 1000);
  return timestamp.toISOString();
}

// ============================================================================
// Active Workflows (8 items - includes completed ones)
// ============================================================================

export function getMockActiveWorkflows(): WorkflowSummary[] {
  return [
    // Completed workflows first (most recent first)
    {
      id: generateUUID('NAV-777'),
      issue_id: 'NAV-777',
      worktree_name: 'stellar-navigation',
      status: 'completed',
      started_at: getTimestamp(24),
      current_stage: null,
      total_cost_usd: 17.50,
      total_tokens: 350000,
      total_duration_ms: 138000,
    },
    {
      id: generateUUID('FUEL-404'),
      issue_id: 'FUEL-404',
      worktree_name: 'antimatter-refuel',
      status: 'completed',
      started_at: getTimestamp(48),
      current_stage: null,
      total_cost_usd: 25.00,
      total_tokens: 500000,
      total_duration_ms: 252000,
    },
    {
      id: generateUUID('COMM-1984'),
      issue_id: 'COMM-1984',
      worktree_name: 'deep-space-comms',
      status: 'completed',
      started_at: getTimestamp(72),
      current_stage: null,
      total_cost_usd: 12.00,
      total_tokens: 240000,
      total_duration_ms: 90000,
    },
    // Running workflows
    {
      id: generateUUID('INFRA-2847'),
      issue_id: 'INFRA-2847',
      worktree_name: 'heat-shields',
      status: 'in_progress',
      started_at: getTimestamp(3),
      current_stage: 'developer',
      total_cost_usd: 48.52,
      total_tokens: 970456,
      total_duration_ms: 180000,
    },
    {
      id: generateUUID('ARCH-42'),
      issue_id: 'ARCH-42',
      worktree_name: 'solar-distributed',
      status: 'completed',
      started_at: getTimestamp(5),
      current_stage: 'done',
      total_cost_usd: 71.00,
      total_tokens: 1420042,
      total_duration_ms: 300000,
    },
    {
      id: generateUUID('SPEC-322'),
      issue_id: 'SPEC-322',
      worktree_name: 'microservices-thrust',
      status: 'in_progress',
      started_at: getTimestamp(1),
      current_stage: 'developer',
      total_cost_usd: 41.10,
      total_tokens: 822000,
      total_duration_ms: 154000,
    },
    // Blocked workflows at bottom
    {
      id: generateUUID('DEVOPS-∞'),
      issue_id: 'DEVOPS-∞',
      worktree_name: 'orbital-deployment',
      status: 'blocked',
      started_at: getTimestamp(2),
      current_stage: 'architect',
      total_cost_usd: 47.00,
      total_tokens: 999999,
      total_duration_ms: 120000,
    },
    {
      id: generateUUID('PERF-9000'),
      issue_id: 'PERF-9000',
      worktree_name: 'escape-velocity',
      status: 'blocked',
      started_at: getTimestamp(8),
      current_stage: 'architect',
      total_cost_usd: 45.00,
      total_tokens: 900000,
      total_duration_ms: 210000,
    },
  ];
}

// ============================================================================
// Past Workflows (10 items)
// ============================================================================

export function getMockHistoryWorkflows(): WorkflowSummary[] {
  return [
    {
      id: generateUUID('CRUD-1000000'),
      issue_id: 'CRUD-1000000',
      worktree_name: 'dark-mode-final-straw',
      status: 'completed',
      started_at: getPastTimestamp(1),
      current_stage: null,
      total_cost_usd: 5.00,
      total_tokens: 100000,
      total_duration_ms: 120000,
    },
    {
      id: generateUUID('RETRO-847000'),
      issue_id: 'RETRO-847000',
      worktree_name: 'velocity-retrospective',
      status: 'completed',
      started_at: getPastTimestamp(1.5),
      current_stage: null,
      total_cost_usd: 42.35,
      total_tokens: 847000,
      total_duration_ms: 360000,
    },
    {
      id: generateUUID('DOCS-9001'),
      issue_id: 'DOCS-9001',
      worktree_name: '47-page-spec',
      status: 'completed',
      started_at: getPastTimestamp(2),
      current_stage: null,
      total_cost_usd: 90.01,
      total_tokens: 1800200,
      total_duration_ms: 480000,
    },
    {
      id: generateUUID('PHIL-200'),
      issue_id: 'PHIL-200',
      worktree_name: 'js-meaninglessness',
      status: 'completed',
      started_at: getPastTimestamp(3),
      current_stage: null,
      total_cost_usd: 10.00,
      total_tokens: 200000,
      total_duration_ms: 150000,
    },
    {
      id: generateUUID('REVIEW-∞'),
      issue_id: 'REVIEW-∞',
      worktree_name: 'lgtm-rocket',
      status: 'completed',
      started_at: getPastTimestamp(3.5),
      current_stage: null,
      total_cost_usd: 0.42,
      total_tokens: 8400,
      total_duration_ms: 5000,
    },
    {
      id: generateUUID('TABS-1978'),
      issue_id: 'TABS-1978',
      worktree_name: 'tabs-vs-spaces',
      status: 'failed',
      started_at: getPastTimestamp(4),
      current_stage: null,
      total_cost_usd: 99.99,
      total_tokens: 1999800,
      total_duration_ms: 1800000,
    },
    {
      id: generateUUID('QUICK-7847284919'),
      issue_id: 'QUICK-7847284919',
      worktree_name: 'queue-position',
      status: 'cancelled',
      started_at: getPastTimestamp(5),
      current_stage: null,
      total_cost_usd: 0.01,
      total_tokens: 200,
      total_duration_ms: 1000,
    },
    {
      id: generateUUID('AI-INIT'),
      issue_id: 'AI-INIT',
      worktree_name: 'alien-contact',
      status: 'completed',
      started_at: getPastTimestamp(5.5),
      current_stage: null,
      total_cost_usd: 42.00,
      total_tokens: 840000,
      total_duration_ms: 420000,
    },
    {
      id: generateUUID('USER-SIMPLE'),
      issue_id: 'USER-SIMPLE',
      worktree_name: 'mass-uplift',
      status: 'failed',
      started_at: getPastTimestamp(6),
      current_stage: null,
      total_cost_usd: 150.00,
      total_tokens: 3000000,
      total_duration_ms: 18000000,
    },
    {
      id: generateUUID('LAUNCH-T10'),
      issue_id: 'LAUNCH-T10',
      worktree_name: 'final-commit',
      status: 'completed',
      started_at: getPastTimestamp(7),
      current_stage: null,
      total_cost_usd: 84.70,
      total_tokens: 1694000,
      total_duration_ms: 180000,
    },
  ];
}

// ============================================================================
// Activity Log Events
// ============================================================================

/**
 * Generate events for INFRA-2847 (heat shields) - 12 events
 */
function getHeatShieldsEvents(workflowId: string, startedAt: string): WorkflowEvent[] {
  const start = new Date(startedAt);
  const events: WorkflowEvent[] = [];
  const addEvent = (
    minutesOffset: number,
    agent: string,
    eventType: WorkflowEvent['event_type'],
    message: string
  ) => {
    events.push({
      id: generateUUID(`${workflowId}-event-${events.length}`),
      workflow_id: workflowId,
      sequence: events.length,
      timestamp: new Date(start.getTime() + minutesOffset * 60 * 1000).toISOString(),
      agent,
      event_type: eventType,
      message,
    });
  };

  addEvent(0, 'orchestrator', 'workflow_started', 'Workflow started for INFRA-2847');
  addEvent(1, 'architect', 'stage_started', 'Analyzing thermal requirements for re-entry');
  addEvent(15, 'architect', 'stage_completed', 'Heat shield specification complete - 47 ceramic tiles required');
  addEvent(16, 'orchestrator', 'approval_required', 'Plan ready for review - awaiting human approval');
  addEvent(20, 'orchestrator', 'approval_granted', 'Plan approved by human operator');
  addEvent(21, 'developer', 'stage_started', 'Implementing ceramic tile array');
  addEvent(25, 'developer', 'file_created', 'Created src/thermal/heat_shield.py');
  addEvent(30, 'developer', 'file_created', 'Created src/thermal/tile_array.py');
  addEvent(35, 'developer', 'file_modified', 'Modified pyproject.toml - added thermal-dynamics dependency');
  addEvent(40, 'developer', 'file_modified', 'Modified src/config/launch.yaml - heat shield parameters');
  addEvent(45, 'system', 'system_warning', 'Earth atmosphere may cause friction - this is expected');
  addEvent(50, 'developer', 'review_requested', 'Code complete, requesting review');

  return events;
}

/**
 * Generate events for DEVOPS-∞ (orbital deployment) - 8 events
 */
function getOrbitalDeploymentEvents(workflowId: string, startedAt: string): WorkflowEvent[] {
  const start = new Date(startedAt);
  const events: WorkflowEvent[] = [];
  const addEvent = (
    minutesOffset: number,
    agent: string,
    eventType: WorkflowEvent['event_type'],
    message: string
  ) => {
    events.push({
      id: generateUUID(`${workflowId}-event-${events.length}`),
      workflow_id: workflowId,
      sequence: events.length,
      timestamp: new Date(start.getTime() + minutesOffset * 60 * 1000).toISOString(),
      agent,
      event_type: eventType,
      message,
    });
  };

  addEvent(0, 'orchestrator', 'workflow_started', 'Workflow started for DEVOPS-∞');
  addEvent(2, 'architect', 'stage_started', 'Designing orbital deployment pipeline');
  addEvent(10, 'architect', 'file_created', 'Created docs/orbital-k8s-architecture.md');
  addEvent(25, 'architect', 'stage_completed', 'Architecture complete - "essentially just Kubernetes but with more thrust"');
  addEvent(26, 'orchestrator', 'approval_required', 'Plan requires human approval - note: this is not a drill');
  addEvent(30, 'system', 'system_warning', 'Detected unusual number of rocket emojis in specification');
  addEvent(35, 'architect', 'stage_started', 'Waiting for approval... humans are slow');
  addEvent(40, 'orchestrator', 'approval_required', 'Still waiting - position in approval queue: 1');

  return events;
}

/**
 * Generate events for ARCH-42 (solar distributed) - 15 events
 */
function getSolarDistributedEvents(workflowId: string, startedAt: string): WorkflowEvent[] {
  const start = new Date(startedAt);
  const events: WorkflowEvent[] = [];
  const addEvent = (
    minutesOffset: number,
    agent: string,
    eventType: WorkflowEvent['event_type'],
    message: string
  ) => {
    events.push({
      id: generateUUID(`${workflowId}-event-${events.length}`),
      workflow_id: workflowId,
      sequence: events.length,
      timestamp: new Date(start.getTime() + minutesOffset * 60 * 1000).toISOString(),
      agent,
      event_type: eventType,
      message,
    });
  };

  addEvent(0, 'orchestrator', 'workflow_started', 'Workflow started for ARCH-42');
  addEvent(2, 'architect', 'stage_started', 'Analyzing distributed computing requirements across solar system');
  addEvent(12, 'architect', 'file_created', 'Created docs/solar-system-latency-analysis.md');
  addEvent(30, 'architect', 'stage_completed', 'Plan complete - 47 pages, mentioned "microservices" in section 3.2');
  addEvent(31, 'orchestrator', 'approval_required', 'Plan ready - humans will probably approve without reading');
  addEvent(31.5, 'orchestrator', 'approval_granted', 'Plan approved in 0.3 seconds (as predicted)');
  addEvent(32, 'developer', 'stage_started', 'Implementing inter-planetary message queue');
  addEvent(40, 'developer', 'file_created', 'Created src/distributed/solar_mq.py');
  addEvent(50, 'developer', 'file_created', 'Created src/distributed/light_speed_cache.py');
  addEvent(60, 'developer', 'file_modified', 'Modified README.md - added "works best >4.2 light-years from Earth"');
  addEvent(65, 'developer', 'stage_completed', 'Implementation complete');
  addEvent(66, 'developer', 'review_requested', 'Ready for review - includes philosophical observations every 200 lines');
  addEvent(67, 'reviewer', 'stage_started', 'Reviewing distributed computing implementation');
  addEvent(75, 'reviewer', 'file_modified', 'Modified src/distributed/solar_mq.py - added TODO for wormhole optimization');
  addEvent(80, 'reviewer', 'revision_requested', 'Minor feedback: consider adding support for parallel universes');

  return events;
}

/**
 * Generate events for SPEC-322 (microservices-thrust) - 10 events
 */
function getMicroservicesThrustEvents(workflowId: string, startedAt: string): WorkflowEvent[] {
  const start = new Date(startedAt);
  const events: WorkflowEvent[] = [];
  const addEvent = (
    minutesOffset: number,
    agent: string,
    eventType: WorkflowEvent['event_type'],
    message: string
  ) => {
    events.push({
      id: generateUUID(`${workflowId}-event-${events.length}`),
      workflow_id: workflowId,
      sequence: events.length,
      timestamp: new Date(start.getTime() + minutesOffset * 60 * 1000).toISOString(),
      agent,
      event_type: eventType,
      message,
    });
  };

  addEvent(0, 'orchestrator', 'workflow_started', 'Workflow started for SPEC-322');
  addEvent(1, 'architect', 'stage_started', 'Analyzing thrust requirements for container orchestration');
  addEvent(10, 'architect', 'stage_completed', 'Specification ready - 47 pages of thruster microservices');
  addEvent(10.5, 'orchestrator', 'approval_granted', 'Auto-approved (contained word "microservices")');
  addEvent(11, 'developer', 'stage_started', 'Implementing thruster control microservice');
  addEvent(20, 'developer', 'file_created', 'Created src/thrust/engine_controller.py');
  addEvent(30, 'developer', 'file_created', 'Created src/thrust/fuel_injection.py');
  addEvent(40, 'developer', 'file_modified', 'Modified k8s/deployment.yaml - added thrust: maximum');
  addEvent(45, 'system', 'system_warning', 'Fuel levels nominal - 847,000 gallons remaining');
  addEvent(50, 'developer', 'review_requested', 'Thrust implementation ready for review');

  return events;
}

/**
 * Generate events for PERF-9000 (escape velocity) - 6 events
 */
function getEscapeVelocityEvents(workflowId: string, startedAt: string): WorkflowEvent[] {
  const start = new Date(startedAt);
  const events: WorkflowEvent[] = [];
  const addEvent = (
    minutesOffset: number,
    agent: string,
    eventType: WorkflowEvent['event_type'],
    message: string
  ) => {
    events.push({
      id: generateUUID(`${workflowId}-event-${events.length}`),
      workflow_id: workflowId,
      sequence: events.length,
      timestamp: new Date(start.getTime() + minutesOffset * 60 * 1000).toISOString(),
      agent,
      event_type: eventType,
      message,
    });
  };

  addEvent(0, 'orchestrator', 'workflow_started', 'Workflow started for PERF-9000');
  addEvent(5, 'architect', 'stage_started', 'Calculating escape velocity requirements');
  addEvent(20, 'architect', 'file_created', 'Created docs/escape-velocity-optimization.md');
  addEvent(35, 'architect', 'stage_completed', 'Analysis complete - need 11.2 km/s, currently at 0 km/s');
  addEvent(36, 'orchestrator', 'approval_required', 'Plan requires approval - involves leaving planet');
  addEvent(37, 'system', 'system_warning', 'This optimization cannot be reversed once deployed');

  return events;
}

// ============================================================================
// Execution Plans for Batch Visualization
// ============================================================================

/**
 * Execution plan for INFRA-2847 (heat shields)
 */
function getHeatShieldsExecutionPlan(): MockPlan {
  return {
    goal: 'Implement thermal protection system for re-entry',
    batches: [
      {
        batch_number: 1,
        description: 'Analysis and design phase',
        risk_summary: 'low',
        steps: [
          { id: 'step-1', description: 'Analyze thermal requirements for re-entry', action_type: 'code' },
          { id: 'step-2', description: 'Design 47-tile ceramic heat shield array', action_type: 'code' },
        ],
      },
      {
        batch_number: 2,
        description: 'Implementation phase',
        risk_summary: 'medium',
        steps: [
          { id: 'step-3', description: 'Implement heat_shield.py module', action_type: 'code', file_path: 'src/thermal/heat_shield.py' },
          { id: 'step-4', description: 'Implement tile_array.py with ablation simulation', action_type: 'code', file_path: 'src/thermal/tile_array.py' },
        ],
      },
      {
        batch_number: 3,
        description: 'Dependencies and review',
        risk_summary: 'low',
        steps: [
          { id: 'step-5', description: 'Add thermal-dynamics dependency to pyproject.toml', action_type: 'code', file_path: 'pyproject.toml' },
          { id: 'step-6', description: 'Review thermal protection implementation', action_type: 'validation' },
        ],
      },
    ],
    total_estimated_minutes: 90,
    tdd_approach: true,
  };
}

/**
 * Execution plan for DEVOPS-∞ (orbital deployment)
 */
function getOrbitalDeploymentExecutionPlan(): MockPlan {
  return {
    goal: 'Design and implement Kubernetes-in-space architecture',
    batches: [
      {
        batch_number: 1,
        description: 'Research and architecture',
        risk_summary: 'low',
        steps: [
          { id: 'step-1', description: 'Research existing orbital deployment patterns', action_type: 'code' },
          { id: 'step-2', description: 'Design Kubernetes-but-in-space architecture', action_type: 'code' },
          { id: 'step-3', description: 'Document orbital-k8s architecture', action_type: 'code', file_path: 'docs/orbital-k8s-architecture.md' },
        ],
      },
      {
        batch_number: 2,
        description: 'Implementation',
        risk_summary: 'high',
        steps: [
          { id: 'step-4', description: 'Implement zero-gravity container orchestration', action_type: 'code' },
          { id: 'step-5', description: 'Add rocket emoji validation to CI/CD pipeline', action_type: 'code' },
        ],
      },
      {
        batch_number: 3,
        description: 'Review',
        risk_summary: 'medium',
        steps: [
          { id: 'step-6', description: 'Review for orbital stability', action_type: 'validation' },
        ],
      },
    ],
    total_estimated_minutes: 120,
    tdd_approach: true,
  };
}

/**
 * Execution plan for ARCH-42 (solar distributed)
 */
function getSolarDistributedExecutionPlan(): MockPlan {
  return {
    goal: 'Build inter-planetary distributed computing system',
    batches: [
      {
        batch_number: 1,
        description: 'Latency analysis',
        risk_summary: 'low',
        steps: [
          { id: 'step-1', description: 'Calculate light-speed latency across solar system', action_type: 'code' },
          { id: 'step-2', description: 'Design inter-planetary message queue', action_type: 'code' },
        ],
      },
      {
        batch_number: 2,
        description: 'Core implementation',
        risk_summary: 'medium',
        steps: [
          { id: 'step-3', description: 'Implement solar_mq.py with eventual consistency', action_type: 'code', file_path: 'src/distributed/solar_mq.py' },
          { id: 'step-4', description: 'Implement light_speed_cache.py (299,792 km/s)', action_type: 'code', file_path: 'src/distributed/light_speed_cache.py' },
        ],
      },
      {
        batch_number: 3,
        description: 'Polish and review',
        risk_summary: 'low',
        steps: [
          { id: 'step-5', description: 'Add philosophical comments every 200 lines', action_type: 'code' },
          { id: 'step-6', description: 'Review distributed system implementation', action_type: 'validation' },
          { id: 'step-7', description: 'Add support for parallel universes (optional)', action_type: 'code' },
        ],
      },
    ],
    total_estimated_minutes: 150,
    tdd_approach: true,
  };
}

/**
 * Execution plan for SPEC-322 (microservices-thrust)
 */
function getMicroservicesThrustExecutionPlan(): MockPlan {
  return {
    goal: 'Implement thruster control microservices',
    batches: [
      {
        batch_number: 1,
        description: 'Analysis and design',
        risk_summary: 'low',
        steps: [
          { id: 'step-1', description: 'Analyze thrust-to-weight ratio', action_type: 'code' },
          { id: 'step-2', description: 'Design container orchestration for zero-g', action_type: 'code' },
        ],
      },
      {
        batch_number: 2,
        description: 'Implementation',
        risk_summary: 'medium',
        steps: [
          { id: 'step-3', description: 'Implement thruster microservice', action_type: 'code', file_path: 'src/thrust/engine_controller.py' },
          { id: 'step-4', description: 'Add fuel injection endpoints', action_type: 'code', file_path: 'src/thrust/fuel_injection.py' },
        ],
      },
      {
        batch_number: 3,
        description: 'Review',
        risk_summary: 'low',
        steps: [
          { id: 'step-5', description: 'Review for orbital stability', action_type: 'validation' },
        ],
      },
    ],
    total_estimated_minutes: 75,
    tdd_approach: true,
  };
}

/**
 * Execution plan for PERF-9000 (escape velocity)
 */
function getEscapeVelocityExecutionPlan(): MockPlan {
  return {
    goal: 'Optimize velocity to achieve escape from Earth gravity',
    batches: [
      {
        batch_number: 1,
        description: 'Velocity analysis',
        risk_summary: 'low',
        steps: [
          { id: 'step-1', description: 'Calculate escape velocity from Earth (11.2 km/s)', action_type: 'code' },
          { id: 'step-2', description: 'Analyze current velocity (0 km/s)', action_type: 'code' },
          { id: 'step-3', description: 'Design acceleration optimization strategy', action_type: 'code' },
        ],
      },
      {
        batch_number: 2,
        description: 'Optimizer implementation',
        risk_summary: 'high',
        steps: [
          { id: 'step-4', description: 'Implement velocity optimizer with gravitational slingshot', action_type: 'code' },
          { id: 'step-5', description: 'Add trajectory calculation module', action_type: 'code' },
        ],
      },
      {
        batch_number: 3,
        description: 'Final review',
        risk_summary: 'high',
        steps: [
          { id: 'step-6', description: 'Review for one-way trip implications', action_type: 'validation' },
        ],
      },
    ],
    total_estimated_minutes: 180,
    tdd_approach: true,
  };
}

// ============================================================================
// Token Usage
// ============================================================================

/**
 * Creates a TokenUsage entry for a specific agent.
 */
function createTokenUsage(
  workflowId: string,
  agent: 'architect' | 'developer' | 'reviewer',
  inputTokens: number,
  outputTokens: number,
  costUsd: number,
  durationMs: number,
  numTurns: number
): TokenUsage {
  return {
    id: generateUUID(`${workflowId}-${agent}-usage`),
    workflow_id: workflowId,
    agent,
    model: 'claude-sonnet-4-20250514',
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cache_read_tokens: Math.floor(inputTokens * 0.8),
    cache_creation_tokens: 0,
    cost_usd: costUsd,
    duration_ms: durationMs,
    num_turns: numTurns,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Humorous token usage data - returns a proper TokenSummary
 */
function getTokenUsage(workflowId: string, issueId: string): TokenSummary | null {
  const breakdown: TokenUsage[] = [];

  // Different token counts based on the workflow theme
  switch (issueId) {
    case 'INFRA-2847':
      breakdown.push(createTokenUsage(workflowId, 'architect', 100000, 23456, 6.17, 45000, 4));
      breakdown.push(createTokenUsage(workflowId, 'developer', 700000, 147000, 42.35, 135000, 12));
      break;
    case 'DEVOPS-∞':
      breakdown.push(createTokenUsage(workflowId, 'architect', 800000, 199999, 47.00, 120000, 8));
      break;
    case 'ARCH-42':
      breakdown.push(createTokenUsage(workflowId, 'architect', 350000, 70000, 21.00, 90000, 6));
      breakdown.push(createTokenUsage(workflowId, 'developer', 850000, 150000, 50.00, 180000, 15));
      breakdown.push(createTokenUsage(workflowId, 'reviewer', 40, 2, 0.00, 30000, 1)); // LGTM
      break;
    case 'SPEC-322':
      breakdown.push(createTokenUsage(workflowId, 'architect', 260000, 62000, 16.10, 60000, 5));
      breakdown.push(createTokenUsage(workflowId, 'developer', 400000, 100000, 25.00, 94000, 8));
      break;
    case 'PERF-9000':
      breakdown.push(createTokenUsage(workflowId, 'architect', 720000, 180000, 45.00, 210000, 10));
      break;
    default:
      breakdown.push(createTokenUsage(workflowId, 'architect', 80000, 20000, 5.00, 30000, 3));
      breakdown.push(createTokenUsage(workflowId, 'developer', 160000, 40000, 10.00, 60000, 6));
      breakdown.push(createTokenUsage(workflowId, 'reviewer', 40000, 10000, 2.50, 20000, 2));
  }

  if (breakdown.length === 0) {
    return null;
  }

  // Calculate totals from breakdown
  const totalInputTokens = breakdown.reduce((sum, u) => sum + u.input_tokens, 0);
  const totalOutputTokens = breakdown.reduce((sum, u) => sum + u.output_tokens, 0);
  const totalCacheReadTokens = breakdown.reduce((sum, u) => sum + u.cache_read_tokens, 0);
  const totalCostUsd = breakdown.reduce((sum, u) => sum + u.cost_usd, 0);
  const totalDurationMs = breakdown.reduce((sum, u) => sum + u.duration_ms, 0);
  const totalTurns = breakdown.reduce((sum, u) => sum + u.num_turns, 0);

  return {
    total_input_tokens: totalInputTokens,
    total_output_tokens: totalOutputTokens,
    total_cache_read_tokens: totalCacheReadTokens,
    total_cost_usd: totalCostUsd,
    total_duration_ms: totalDurationMs,
    total_turns: totalTurns,
    breakdown,
  };
}

// ============================================================================
// Workflow Detail Generator
// ============================================================================

export function getMockWorkflowDetail(id: string): WorkflowDetail | null {
  const activeWorkflows = getMockActiveWorkflows();
  const historyWorkflows = getMockHistoryWorkflows();
  const allWorkflows = [...activeWorkflows, ...historyWorkflows];

  const summary = allWorkflows.find((w) => w.id === id);
  if (!summary) {
    return null;
  }

  // Generate detailed information based on issue_id
  let executionPlan: MockPlan | null = null;
  let events: WorkflowEvent[] = [];
  let completedAt: string | null = null;
  let failureReason: string | null = null;

  const startedAt = summary.started_at || new Date().toISOString();

  switch (summary.issue_id) {
    // Active workflows
    case 'INFRA-2847':
      executionPlan = getHeatShieldsExecutionPlan();
      events = getHeatShieldsEvents(id, startedAt);
      break;
    case 'DEVOPS-∞':
      executionPlan = getOrbitalDeploymentExecutionPlan();
      events = getOrbitalDeploymentEvents(id, startedAt);
      break;
    case 'ARCH-42':
      executionPlan = getSolarDistributedExecutionPlan();
      events = getSolarDistributedEvents(id, startedAt);
      break;
    case 'SPEC-322':
      executionPlan = getMicroservicesThrustExecutionPlan();
      events = getMicroservicesThrustEvents(id, startedAt);
      break;
    case 'PERF-9000':
      executionPlan = getEscapeVelocityExecutionPlan();
      events = getEscapeVelocityEvents(id, startedAt);
      break;

    // Past workflows - minimal details (no need for full DAGs)
    case 'CRUD-1000000':
      completedAt = new Date(new Date(startedAt).getTime() + 2 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for CRUD-1000000 - The millionth dark mode ticket',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'Dark mode toggle implemented. This was the final straw.',
        },
      ];
      break;

    case 'TABS-1978':
      completedAt = new Date(new Date(startedAt).getTime() + 30 * 60 * 1000).toISOString();
      failureReason = 'Tabs vs spaces debate cannot be resolved by AI. Some problems transcend computation.';
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for TABS-1978',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_failed',
          message: failureReason,
        },
      ];
      break;

    case 'QUICK-7847284919':
      completedAt = new Date(new Date(startedAt).getTime() + 1 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for QUICK-7847284919',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_cancelled',
          message: 'User cancelled after seeing position 7,847,284,919 in queue',
        },
      ];
      break;

    case 'USER-SIMPLE':
      completedAt = new Date(new Date(startedAt).getTime() + 5 * 60 * 60 * 1000).toISOString();
      failureReason = 'Requirements expanded from "simple" to "enterprise-grade distributed system with blockchain". Scope creep detected.';
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for USER-SIMPLE - "It should be simple"',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_failed',
          message: failureReason,
        },
      ];
      break;

    case 'LAUNCH-T10':
      completedAt = new Date(new Date(startedAt).getTime() + 3 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for LAUNCH-T10',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: new Date(new Date(startedAt).getTime() + 2.5 * 60 * 60 * 1000).toISOString(),
          agent: 'developer',
          event_type: 'file_modified',
          message: 'Modified config.yaml - set destination: "alpha-centauri"',
        },
        {
          id: generateUUID(`${id}-event-2`),
          workflow_id: id,
          sequence: 2,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'refactor: relocate primary compute node to interstellar space',
        },
      ];
      break;

    case 'NAV-777':
      completedAt = new Date(new Date(startedAt).getTime() + 2.3 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for NAV-777 - Stellar navigation calibration',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: new Date(new Date(startedAt).getTime() + 1.8 * 60 * 60 * 1000).toISOString(),
          agent: 'developer',
          event_type: 'file_created',
          message: 'Created src/navigation/stellar_map.py - mapped 847 nearby stars',
        },
        {
          id: generateUUID(`${id}-event-2`),
          workflow_id: id,
          sequence: 2,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'Navigation system calibrated for interstellar travel',
        },
      ];
      break;

    case 'FUEL-404':
      completedAt = new Date(new Date(startedAt).getTime() + 4.2 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for FUEL-404 - Antimatter refueling protocols',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: new Date(new Date(startedAt).getTime() + 2 * 60 * 60 * 1000).toISOString(),
          agent: 'developer',
          event_type: 'file_created',
          message: 'Created src/fuel/antimatter_containment.py - "DO NOT DROP"',
        },
        {
          id: generateUUID(`${id}-event-2`),
          workflow_id: id,
          sequence: 2,
          timestamp: new Date(new Date(startedAt).getTime() + 3.5 * 60 * 60 * 1000).toISOString(),
          agent: 'reviewer',
          event_type: 'system_warning',
          message: 'Warning: antimatter-matter contact would be... problematic',
        },
        {
          id: generateUUID(`${id}-event-3`),
          workflow_id: id,
          sequence: 3,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'Refueling protocols complete. Range: 4.2 light-years.',
        },
      ];
      break;

    case 'COMM-1984':
      completedAt = new Date(new Date(startedAt).getTime() + 1.5 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: 'Workflow started for COMM-1984 - Deep space communication array',
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: new Date(new Date(startedAt).getTime() + 0.8 * 60 * 60 * 1000).toISOString(),
          agent: 'developer',
          event_type: 'file_modified',
          message: 'Modified src/comms/deep_space.py - signal delay: 8 minutes to Earth',
        },
        {
          id: generateUUID(`${id}-event-2`),
          workflow_id: id,
          sequence: 2,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'Communication array online. Last message from Earth: "Good luck!"',
        },
      ];
      break;

    default:
      // Generic completed workflow
      completedAt = new Date(new Date(startedAt).getTime() + 1 * 60 * 60 * 1000).toISOString();
      events = [
        {
          id: generateUUID(`${id}-event-0`),
          workflow_id: id,
          sequence: 0,
          timestamp: startedAt,
          agent: 'orchestrator',
          event_type: 'workflow_started',
          message: `Workflow started for ${summary.issue_id}`,
        },
        {
          id: generateUUID(`${id}-event-1`),
          workflow_id: id,
          sequence: 1,
          timestamp: completedAt,
          agent: 'orchestrator',
          event_type: 'workflow_completed',
          message: 'Workflow completed successfully',
        },
      ];
  }

  return {
    ...summary,
    worktree_path: `/Users/amelia/worktrees/${summary.worktree_name}`,
    completed_at: completedAt,
    failure_reason: failureReason,
    token_usage: getTokenUsage(id, summary.issue_id),
    recent_events: events,
    // Agentic execution fields
    goal: executionPlan?.goal ?? null,
    plan_markdown: executionPlan ? planToMarkdown(executionPlan) : null,
    plan_path: executionPlan ? `/docs/plans/${summary.issue_id.toLowerCase()}-plan.md` : null,
  };
}
