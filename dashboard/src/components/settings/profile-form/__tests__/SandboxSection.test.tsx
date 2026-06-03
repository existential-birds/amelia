import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SandboxSection } from '../SandboxSection';
import type { SandboxFormData } from '../types';

const sb = (mode: SandboxFormData['mode'], overrides: Partial<SandboxFormData> = {}): SandboxFormData => ({
  mode,
  image: 'amelia-sandbox:latest',
  network_allowlist_enabled: false,
  network_allowed_hosts: [],
  repo_url: '',
  daytona_api_url: '',
  daytona_target: 'us',
  daytona_cpu: 2,
  daytona_memory: 4,
  daytona_disk: 10,
  daytona_image: '',
  ...overrides,
});

describe('SandboxSection', () => {
  it('shows the sandbox mode select with the none-mode description by default', () => {
    render(<SandboxSection sandbox={sb('none')} errors={{}} onField={vi.fn()} onHosts={vi.fn()} />);
    expect(screen.getByText('Sandbox Mode')).toBeInTheDocument();
    expect(screen.getByText('Code runs directly on the host machine.')).toBeInTheDocument();
  });

  it('shows the Docker Image field only in container mode', () => {
    const { rerender } = render(
      <SandboxSection sandbox={sb('none')} errors={{}} onField={vi.fn()} onHosts={vi.fn()} />
    );
    expect(screen.queryByText('Docker Image')).not.toBeInTheDocument();
    rerender(<SandboxSection sandbox={sb('container')} errors={{}} onField={vi.fn()} onHosts={vi.fn()} />);
    expect(screen.getByText('Docker Image')).toBeInTheDocument();
  });

  it('does not show container fields when mode is None', () => {
    render(<SandboxSection sandbox={sb('none')} errors={{}} onField={vi.fn()} onHosts={vi.fn()} />);
    expect(screen.queryByText('Docker Image')).not.toBeInTheDocument();
    expect(screen.queryByText('Network Allowlist')).not.toBeInTheDocument();
  });

  it('shows the container image value in container mode', () => {
    render(
      <SandboxSection
        sandbox={sb('container', { image: 'amelia-sandbox:latest' })}
        errors={{}}
        onField={vi.fn()}
        onHosts={vi.fn()}
      />
    );
    expect(screen.getByDisplayValue('amelia-sandbox:latest')).toBeInTheDocument();
  });

  it('shows allowed hosts when network allowlist is enabled', () => {
    render(
      <SandboxSection
        sandbox={sb('container', {
          network_allowlist_enabled: true,
          network_allowed_hosts: ['api.anthropic.com', 'github.com'],
        })}
        errors={{}}
        onField={vi.fn()}
        onHosts={vi.fn()}
      />
    );
    expect(screen.getByText('api.anthropic.com')).toBeInTheDocument();
    expect(screen.getByText('github.com')).toBeInTheDocument();
  });

  it('does not show allowed hosts when the allowlist is disabled', () => {
    render(
      <SandboxSection
        sandbox={sb('container', { network_allowlist_enabled: false })}
        errors={{}}
        onField={vi.fn()}
        onHosts={vi.fn()}
      />
    );
    expect(screen.queryByText('Allowed Hosts')).not.toBeInTheDocument();
  });

  it('shows Daytona resource inputs in daytona mode', () => {
    render(<SandboxSection sandbox={sb('daytona')} errors={{}} onField={vi.fn()} onHosts={vi.fn()} />);
    expect(screen.getByText('CPU Cores')).toBeInTheDocument();
    expect(screen.getByText('Memory (GB)')).toBeInTheDocument();
    expect(screen.getByText('Disk (GB)')).toBeInTheDocument();
  });

  it('renders the inline repo_url error in daytona mode', () => {
    render(
      <SandboxSection
        sandbox={sb('daytona')}
        errors={{ sandbox_repo_url: 'Repository URL is required' }}
        onField={vi.fn()}
        onHosts={vi.fn()}
      />
    );
    expect(screen.getByText('Repository URL is required')).toBeInTheDocument();
  });
});
