import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TypeBadge } from '../TypeBadge';

describe('TypeBadge', () => {
  it('renders "Implementation" with blue styling for pipeline_type="full"', () => {
    render(<TypeBadge type="full" />);
    expect(screen.getByText('Implementation')).toBeInTheDocument();
    const badge = screen.getByText('Implementation');
    expect(badge.className).toMatch(/blue/);
  });

  it('renders "Review" with purple styling for pipeline_type="review"', () => {
    render(<TypeBadge type="review" />);
    expect(screen.getByText('Review')).toBeInTheDocument();
    const badge = screen.getByText('Review');
    expect(badge.className).toMatch(/purple/);
  });

  it('renders "PR Fix" with orange styling for pipeline_type="pr_auto_fix"', () => {
    render(<TypeBadge type="pr_auto_fix" />);
    expect(screen.getByText('PR Fix')).toBeInTheDocument();
    const badge = screen.getByText('PR Fix');
    expect(badge.className).toMatch(/orange/);
  });

  it('defaults to "Implementation" when pipeline_type is null', () => {
    render(<TypeBadge type={null} />);
    expect(screen.getByText('Implementation')).toBeInTheDocument();
  });

  it('defaults to "Implementation" when pipeline_type is undefined', () => {
    render(<TypeBadge type={undefined as unknown as string | null} />);
    expect(screen.getByText('Implementation')).toBeInTheDocument();
  });
});
