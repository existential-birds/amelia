import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApprovalControls } from '../ApprovalControls';

function renderWithRouter(workflowId: string, status: 'pending' | 'approved' | 'rejected' = 'pending') {
  const routes = [
    {
      path: '/',
      element: (
        <ApprovalControls
          workflowId={workflowId}
          planSummary="Test plan"
          planMarkdown="# Plan"
          status={status}
        />
      ),
    },
    { path: '/workflows/:id/approve', action: async () => ({ success: true }) },
    { path: '/workflows/:id/reject', action: async () => ({ success: true }) },
    { path: '/workflows/:id/replan', action: async () => ({ success: true }) },
  ];

  const router = createMemoryRouter(routes, { initialEntries: ['/'] });
  return render(<RouterProvider router={router} />);
}

describe('ApprovalControls', () => {
  it('should render Replan button when status is pending', () => {
    renderWithRouter('wf-123', 'pending');
    expect(screen.getByRole('button', { name: /replan/i })).toBeInTheDocument();
  });

  it('should not render Replan button when status is approved', () => {
    renderWithRouter('wf-123', 'approved');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });

  it('should not render Replan button when status is rejected', () => {
    renderWithRouter('wf-123', 'rejected');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });
});
