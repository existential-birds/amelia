/**
 * Shared mock configuration for workflowStore.
 * Used by DashboardSidebar tests and other components that depend on workflow state.
 *
 * Note: Due to vi.mock hoisting, these mocks must be used inline in vi.mock calls
 * rather than imported. However, this file documents the canonical mock shape
 * and can be used as a reference for consistency.
 */

/**
 * Default mock state for the workflow store.
 */
export const defaultWorkflowState = {
  isConnected: true,
};

/**
 * Mock factory for useWorkflowStore.
 * Usage in test files:
 *
 * ```ts
 * vi.mock('@/store/workflowStore', () => ({
 *   useWorkflowStore: vi.fn((selector) => {
 *     const state = { isConnected: true };
 *     return selector(state);
 *   }),
 * }));
 * ```
 */
export const workflowStoreMockShape = {
  useWorkflowStore: '(selector) => selector({ isConnected: true })',
};

/**
 * Mock factory for useDemoMode.
 * Usage in test files:
 *
 * ```ts
 * vi.mock('@/hooks/useDemoMode', () => ({
 *   useDemoMode: vi.fn(() => ({ isDemo: false, demoType: null })),
 * }));
 * ```
 */
export const demoModeMockShape = {
  useDemoMode: '() => ({ isDemo: false, demoType: null })',
};
