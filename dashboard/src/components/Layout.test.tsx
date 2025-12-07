import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './Layout';

// Mock the hooks
const mockUseWebSocket = vi.fn();
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

let mockIsConnected = true;
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: mockIsConnected };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

const renderLayout = (initialRoute = '/') => {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <Layout />,
        children: [
          { path: 'workflows', element: <div>Workflows</div> },
          { path: 'history', element: <div>History</div> },
          { path: 'logs', element: <div>Logs</div> },
        ],
      },
    ],
    { initialEntries: [initialRoute] }
  );
  return render(<RouterProvider router={router} />);
};

describe('Layout WebSocket Initialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsConnected = true;
  });

  it('should initialize WebSocket on mount', () => {
    renderLayout();
    expect(mockUseWebSocket).toHaveBeenCalledTimes(1);
  });

  it('should display "Connected" when WebSocket is connected', () => {
    mockIsConnected = true;
    renderLayout();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('should display "Disconnected" when WebSocket is disconnected', () => {
    mockIsConnected = false;
    renderLayout();
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });
});
