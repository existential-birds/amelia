/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Custom React hooks for the Amelia dashboard.
 *
 * Provides hooks for WebSocket connectivity, workflow data management,
 * and workflow state transitions.
 *
 * @see {@link useWebSocket} - Real-time workflow event streaming
 * @see {@link useWorkflows} - Combined loader and WebSocket workflow data
 * @see {@link useWorkflowActions} - Workflow state transitions (approve/reject/cancel)
 */

export { useWebSocket } from './useWebSocket';
export { useWorkflows } from './useWorkflows';
export { useWorkflowActions } from './useWorkflowActions';
export { useElapsedTime } from './useElapsedTime';
export { useAutoRevalidation } from './useAutoRevalidation';
