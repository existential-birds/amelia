import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PRAutoFixSection } from '../PRAutoFixSection';
import type { PRAutoFixConfig } from '@/api/settings';

const DEFAULT_CONFIG: PRAutoFixConfig = {
  aggressiveness: 'standard',
  poll_interval: 60,
  auto_resolve: true,
  resolve_no_changes: true,
  max_iterations: 3,
  commit_prefix: 'fix(review):',
  post_push_cooldown_seconds: 30,
  max_cooldown_seconds: 120,
  poll_label: null,
  ignore_authors: [],
  confidence_threshold: 0.7,
};

function renderSection(props?: Partial<{ enabled: boolean; config: PRAutoFixConfig | null }>) {
  const onChange = vi.fn();
  render(
    <PRAutoFixSection
      enabled={props?.enabled ?? false}
      config={props?.config ?? null}
      onChange={onChange}
    />
  );
  return { onChange };
}

describe('PRAutoFixSection', () => {
  it('renders enable toggle Switch', () => {
    renderSection();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByText('Enable PR Auto-Fix')).toBeInTheDocument();
  });

  it('hides aggressiveness and poll_label when disabled', () => {
    renderSection();
    expect(screen.queryByText('Aggressiveness')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/poll label/i)).not.toBeInTheDocument();
  });

  it('shows aggressiveness and poll_label when enabled', () => {
    renderSection({ enabled: true, config: DEFAULT_CONFIG });
    expect(screen.getByText('Aggressiveness')).toBeInTheDocument();
    expect(screen.getByLabelText(/poll label/i)).toBeInTheDocument();
  });

  it('calls onChange(null) when toggling off', async () => {
    const user = userEvent.setup();
    const { onChange } = renderSection({ enabled: true, config: DEFAULT_CONFIG });
    await user.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('calls onChange with default config when toggling on', async () => {
    const user = userEvent.setup();
    const { onChange } = renderSection();
    await user.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ aggressiveness: 'standard' })
    );
  });

  it('calls onChange with updated aggressiveness when changed', async () => {
    const user = userEvent.setup();
    const { onChange } = renderSection({ enabled: true, config: DEFAULT_CONFIG });
    // Open the aggressiveness select
    await user.click(screen.getByRole('combobox'));
    // Select "Thorough"
    await user.click(screen.getByRole('option', { name: /thorough/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ aggressiveness: 'thorough' })
    );
  });

  it('shows 4 aggressiveness options', async () => {
    const user = userEvent.setup();
    renderSection({ enabled: true, config: DEFAULT_CONFIG });
    await user.click(screen.getByRole('combobox'));
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(4);
    expect(screen.getByRole('option', { name: /critical/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /standard/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /thorough/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /exemplary/i })).toBeInTheDocument();
  });
});
