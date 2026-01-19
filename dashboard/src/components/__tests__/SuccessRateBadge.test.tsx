import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SuccessRateBadge } from '../SuccessRateBadge';

describe('SuccessRateBadge', () => {
  it('should display percentage value', () => {
    render(<SuccessRateBadge rate={0.85} />);

    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('should round to nearest integer', () => {
    render(<SuccessRateBadge rate={0.856} />);

    expect(screen.getByText('86%')).toBeInTheDocument();
  });

  it('should apply green color for rate >= 90%', () => {
    render(<SuccessRateBadge rate={0.95} />);

    const badge = screen.getByText('95%');
    expect(badge).toHaveClass('text-green-400');
  });

  it('should apply yellow color for rate 70-89%', () => {
    render(<SuccessRateBadge rate={0.75} />);

    const badge = screen.getByText('75%');
    expect(badge).toHaveClass('text-yellow-400');
  });

  it('should apply red color for rate < 70%', () => {
    render(<SuccessRateBadge rate={0.5} />);

    const badge = screen.getByText('50%');
    expect(badge).toHaveClass('text-red-400');
  });

  it('should handle 0% rate', () => {
    render(<SuccessRateBadge rate={0} />);

    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('should handle 100% rate', () => {
    render(<SuccessRateBadge rate={1} />);

    expect(screen.getByText('100%')).toBeInTheDocument();
  });
});
