/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Component barrel exports for the Amelia dashboard.
 *
 * Re-exports domain components, AI elements, shadcn UI primitives,
 * and custom React Flow node/edge types.
 */

// =============================================================================
// Domain Components
// =============================================================================

// Status and queue components
export { StatusBadge } from './StatusBadge';
export { JobQueueItem } from './JobQueueItem';
export { JobQueue } from './JobQueue';

// Activity log components
export { ActivityLogItem } from './ActivityLogItem';
export { ActivityLog } from './ActivityLog';

// Workflow components
export { ApprovalControls } from './ApprovalControls';
export { WorkflowCanvas } from './WorkflowCanvas';
// export { WorkflowHeader } from './WorkflowHeader';
export { WorkflowProgress } from './WorkflowProgress';
export { WorkflowEmptyState } from './WorkflowEmptyState';

// Skeleton loading states
export { JobQueueSkeleton } from './JobQueueSkeleton';
export { ActivityLogSkeleton } from './ActivityLogSkeleton';

// Layout components
export { DashboardSidebar } from './DashboardSidebar';

// Custom flow node/edge types
export * from './flow';

// =============================================================================
// ai-elements (re-exported for direct use when needed)
// =============================================================================
export * from './ai-elements/queue';
export * from './ai-elements/confirmation';
export * from './ai-elements/loader';
export * from './ai-elements/shimmer';

// =============================================================================
// shadcn UI components
// =============================================================================
export * from './ui/button';
export * from './ui/badge';
export * from './ui/card';
export * from './ui/collapsible';
export * from './ui/scroll-area';
export * from './ui/tooltip';
export * from './ui/progress';
export * from './ui/skeleton';
export * from './ui/alert';
export * from './ui/empty';
export * from './ui/sidebar';
export * from './ui/sheet';
export * from './ui/separator';
export * from './ui/input';

// =============================================================================
// Other components
// =============================================================================
export * as toast from './Toast';
