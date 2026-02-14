import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProfileCard } from '../ProfileCard';
import { createMockProfile } from '@/__tests__/fixtures';

describe('ProfileCard sandbox indicator', () => {
  const defaultProps = {
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onActivate: vi.fn(),
  };

  it('should not show sandbox badge when sandbox mode is none', () => {
    const profile = createMockProfile({
      sandbox: { mode: 'none', image: 'amelia-sandbox:latest', network_allowlist_enabled: false, network_allowed_hosts: [] },
    });

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.queryByText('Sandbox')).not.toBeInTheDocument();
  });

  it('should not show sandbox badge when sandbox is undefined', () => {
    const profile = createMockProfile();

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.queryByText('Sandbox')).not.toBeInTheDocument();
  });

  it('should show sandbox badge when sandbox mode is container', () => {
    const profile = createMockProfile({
      sandbox: { mode: 'container', image: 'amelia-sandbox:latest', network_allowlist_enabled: true, network_allowed_hosts: ['api.anthropic.com'] },
    });

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.getByText('Sandbox')).toBeInTheDocument();
  });
});
