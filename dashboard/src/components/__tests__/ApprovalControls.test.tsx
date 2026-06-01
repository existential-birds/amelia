import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApprovalControls } from '../ApprovalControls';

function renderWithRouter(
  workflowId: string,
  planSummary = 'Test plan',
  status: 'pending' | 'approved' | 'rejected' = 'pending'
) {
  const routes = [
    {
      path: '/',
      element: (
        <ApprovalControls
          workflowId={workflowId}
          planSummary={planSummary}
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
  it('renders Approve and Reject buttons', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('renders plan summary', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByText(/Add benchmark framework/)).toBeInTheDocument();
  });

  it('renders description text', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByText(/Review and approve/)).toBeInTheDocument();
  });

  it('has data-slot attribute', () => {
    renderWithRouter('wf-001', 'Test');
    const heading = screen.getByText('Test');
    const controls = heading.closest('[data-slot="approval-controls"]');
    expect(controls).toBeInTheDocument();
  });

  it.each([
    { status: 'approved' as const, expectedText: /Plan approved/ },
    { status: 'rejected' as const, expectedText: /Plan rejected/ },
  ])('shows $status state', ({ status, expectedText }) => {
    renderWithRouter('wf-001', 'Test', status);
    expect(screen.getByText(expectedText)).toBeInTheDocument();
  });

  it('hides buttons when not pending', () => {
    renderWithRouter('wf-001', 'Test', 'approved');
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });

  it('should render Replan button when status is pending', () => {
    renderWithRouter('wf-123', 'Test plan', 'pending');
    expect(screen.getByRole('button', { name: /replan/i })).toBeInTheDocument();
  });

  it('should not render Replan button when status is approved', () => {
    renderWithRouter('wf-123', 'Test plan', 'approved');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });

  it('should not render Replan button when status is rejected', () => {
    renderWithRouter('wf-123', 'Test plan', 'rejected');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });
});
