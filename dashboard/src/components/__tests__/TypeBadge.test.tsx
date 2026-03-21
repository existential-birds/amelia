import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TypeBadge } from '../TypeBadge';

describe('TypeBadge', () => {
  it.each([
    ['full', 'Implementation', /blue/],
    ['review', 'Review', /purple/],
    ['pr_auto_fix', 'PR Fix', /orange/],
  ] as const)('renders "%s" as "%s" with %s styling', (type, label, colorPattern) => {
    render(<TypeBadge type={type} />);
    const badge = screen.getByText(label);
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(colorPattern);
  });

  it.each([null, undefined] as const)(
    'defaults to "Implementation" when pipeline_type is %s',
    (type) => {
      render(<TypeBadge type={type as unknown as string | null} />);
      expect(screen.getByText('Implementation')).toBeInTheDocument();
    },
  );
});
