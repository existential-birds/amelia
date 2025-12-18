import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApprovalControls } from './ApprovalControls';

const renderWithRouter = (workflowId: string, planSummary: string, status?: 'pending' | 'approved' | 'rejected') => {
  const router = createMemoryRouter([
    {
      path: '/',
      element: <ApprovalControls workflowId={workflowId} planSummary={planSummary} status={status} />,
    },
  ]);

  return render(<RouterProvider router={router} />);
};

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
    // Find the approval controls by its heading, then check parent has data-slot
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

  it('focuses textarea when reject is clicked', async () => {
    const user = userEvent.setup();
    renderWithRouter('wf-001', 'Test');

    await user.click(screen.getByRole('button', { name: /reject/i }));

    const textarea = screen.getByRole('textbox', { name: /rejection feedback/i });
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveFocus();
  });
});
