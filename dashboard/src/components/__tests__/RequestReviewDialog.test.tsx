import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RequestReviewDialog } from '../RequestReviewDialog';
import { api } from '@/api/client';
import { toast } from 'sonner';

vi.mock('@/api/client', () => ({
  api: {
    requestReview: vi.fn(),
  },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('RequestReviewDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.requestReview).mockResolvedValue(undefined);
  });

  it('renders the trigger button', () => {
    render(<RequestReviewDialog workflowId="test-id" />);
    expect(screen.getByText('Request Review')).toBeInTheDocument();
  });

  it('opens dialog when trigger button is clicked', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    expect(screen.getByText('Request Code Review')).toBeInTheDocument();
    expect(screen.getByText('General')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Review Only')).toBeInTheDocument();
    expect(screen.getByText('Review & Fix')).toBeInTheDocument();
  });

  it('has general review type selected by default', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    const generalBtn = screen.getByText('General');
    expect(generalBtn.className).toContain('border-primary');
  });

  it('toggles review type selection', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    const securityBtn = screen.getByText('Security');
    await user.click(securityBtn);
    expect(securityBtn.className).toContain('border-primary');

    await user.click(securityBtn);
    expect(securityBtn.className).not.toContain('bg-primary/10');
  });

  it('switches mode between review_only and review_fix', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    const reviewFixBtn = screen.getByText('Review & Fix');
    await user.click(reviewFixBtn);
    expect(reviewFixBtn.className).toContain('border-primary');

    const reviewOnlyBtn = screen.getByText('Review Only');
    expect(reviewOnlyBtn.className).not.toContain('bg-primary/10');
  });

  it('submits review request with selected options', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="wf-123" />);

    await user.click(screen.getByText('Request Review'));
    await user.click(screen.getByText('Security'));
    await user.click(screen.getByText('Review & Fix'));

    const submitButtons = screen.getAllByRole('button', { name: /Request Review/i });
    const submitBtn = submitButtons.at(-1)!;
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.requestReview).toHaveBeenCalledWith('wf-123', {
        mode: 'review_fix',
        review_types: ['general', 'security'],
      });
    });

    expect(toast.success).toHaveBeenCalledWith('Review requested successfully');
  });

  it('disables submit button when no review types are selected', async () => {
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    await user.click(screen.getByText('General'));

    const submitButtons = screen.getAllByRole('button', { name: /Request Review/i });
    const submitBtn = submitButtons.at(-1)!;
    expect(submitBtn).toBeDisabled();
  });

  it('displays error message and toast when request fails', async () => {
    vi.mocked(api.requestReview).mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    const submitButtons = screen.getAllByRole('button', { name: /Request Review/i });
    const submitBtn = submitButtons.at(-1)!;
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    expect(toast.error).toHaveBeenCalledWith('Network error');
  });

  it('shows fallback error message for non-Error exceptions', async () => {
    vi.mocked(api.requestReview).mockRejectedValue('unknown');
    const user = userEvent.setup();
    render(<RequestReviewDialog workflowId="test-id" />);

    await user.click(screen.getByText('Request Review'));

    const submitButtons = screen.getAllByRole('button', { name: /Request Review/i });
    const submitBtn = submitButtons.at(-1)!;
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to request review')).toBeInTheDocument();
    });
  });
});
