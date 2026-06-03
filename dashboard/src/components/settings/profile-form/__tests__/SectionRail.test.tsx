import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SectionRail } from '../SectionRail';
import type { SectionId } from '../types';

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'identity', label: 'Identity' },
  { id: 'agents', label: 'Agents' },
  { id: 'sandbox', label: 'Sandbox' },
  { id: 'autofix', label: 'Auto-Fix' },
];

describe('SectionRail', () => {
  it('calls onSelect when a section is chosen', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <SectionRail sections={SECTIONS} active="identity" onSelect={onSelect} errorSections={{}} />
    );
    await user.click(screen.getByRole('button', { name: /sandbox/i }));
    expect(onSelect).toHaveBeenCalledWith('sandbox');
  });

  it('marks a section that has errors', () => {
    render(
      <SectionRail
        sections={SECTIONS}
        active="identity"
        onSelect={vi.fn()}
        errorSections={{ agents: true }}
      />
    );
    expect(screen.getByRole('button', { name: /agents/i })).toHaveAttribute(
      'data-has-error',
      'true'
    );
  });
});
