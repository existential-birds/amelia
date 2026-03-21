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

describe('PRAutoFixSection', () => {
  it('renders enable toggle Switch', () => {
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={false} config={null} onChange={onChange} />
    );
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByText('Enable PR Auto-Fix')).toBeInTheDocument();
  });

  it('hides aggressiveness and poll_label when disabled', () => {
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={false} config={null} onChange={onChange} />
    );
    expect(screen.queryByText('Aggressiveness')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/poll label/i)).not.toBeInTheDocument();
  });

  it('shows aggressiveness and poll_label when enabled', () => {
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={true} config={DEFAULT_CONFIG} onChange={onChange} />
    );
    expect(screen.getByText('Aggressiveness')).toBeInTheDocument();
    expect(screen.getByLabelText(/poll label/i)).toBeInTheDocument();
  });

  it('calls onChange(null) when toggling off', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={true} config={DEFAULT_CONFIG} onChange={onChange} />
    );
    await user.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('calls onChange with default config when toggling on', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={false} config={null} onChange={onChange} />
    );
    await user.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ aggressiveness: 'standard' })
    );
  });

  it('calls onChange with updated aggressiveness when changed', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={true} config={DEFAULT_CONFIG} onChange={onChange} />
    );
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
    const onChange = vi.fn();
    render(
      <PRAutoFixSection enabled={true} config={DEFAULT_CONFIG} onChange={onChange} />
    );
    await user.click(screen.getByRole('combobox'));
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(4);
    expect(screen.getByRole('option', { name: /critical/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /standard/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /thorough/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /exemplary/i })).toBeInTheDocument();
  });
});
