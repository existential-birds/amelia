/**
 * Shared mock configuration for workflowStore.
 * Used by DashboardSidebar tests and other components that depend on workflow state.
 *
 * Note: Due to vi.mock hoisting, these mocks must be used inline in vi.mock calls
 * rather than imported. See usage examples below.
 *
 * @example useWorkflowStore mock
 * ```ts
 * vi.mock('@/store/workflowStore', () => ({
 *   useWorkflowStore: vi.fn((selector) => {
 *     const state = { isConnected: true };
 *     return selector(state);
 *   }),
 * }));
 * ```
 *
 * @example useDemoMode mock
 * ```ts
 * vi.mock('@/hooks/useDemoMode', () => ({
 *   useDemoMode: vi.fn(() => ({ isDemo: false, demoType: null })),
 * }));
 * ```
 */

/**
 * Default mock state for the workflow store.
 */
export const defaultWorkflowState = {
  isConnected: true,
};
