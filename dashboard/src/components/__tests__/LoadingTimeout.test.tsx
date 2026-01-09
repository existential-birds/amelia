import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { LoadingTimeout } from '../LoadingTimeout';

describe('LoadingTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it('should show loading spinner initially', async () => {
    render(<LoadingTimeout />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText(/taking longer/i)).not.toBeInTheDocument();

    // Flush any pending interval callbacks to avoid act() warning
    await act(async () => {
      vi.runOnlyPendingTimers();
    });
  });

  it('should show timeout message after 10 seconds', () => {
    render(<LoadingTimeout />);

    // Advance 11 intervals (11 seconds) to exceed 10s threshold
    act(() => {
      vi.advanceTimersByTime(11000);
    });

    expect(screen.getByText(/taking longer than expected/i)).toBeInTheDocument();
  });

  it('should show connection hint after 30 seconds', () => {
    render(<LoadingTimeout />);

    // Advance 31 intervals (31 seconds) to exceed 30s threshold
    act(() => {
      vi.advanceTimersByTime(31000);
    });

    expect(screen.getByText(/check your connection/i)).toBeInTheDocument();
  });
});
