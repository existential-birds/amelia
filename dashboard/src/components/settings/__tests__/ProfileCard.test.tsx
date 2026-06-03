import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileCard } from '../ProfileCard';
import { createMockProfile } from '@/__tests__/fixtures';

// motion/react sets an initial opacity:0 on the wrapper that jsdom never
// animates away, which would defeat toBeVisible(). Render as plain elements.
vi.mock('motion/react', () => ({
  motion: new Proxy(
    {},
    {
      get:
        (_target, tag: string) =>
        ({ children, layout, initial, animate, exit, transition, ...rest }: Record<string, unknown>) => {
          void layout;
          void initial;
          void animate;
          void exit;
          void transition;
          const Tag = tag as keyof JSX.IntrinsicElements;
          return <Tag {...rest}>{children as React.ReactNode}</Tag>;
        },
    }
  ),
}));

describe('ProfileCard sandbox indicator', () => {
  const defaultProps = {
    onConfigure: vi.fn(),
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

describe('ProfileCard interaction', () => {
  it('calls onConfigure when the card body is clicked', async () => {
    const user = userEvent.setup();
    const onConfigure = vi.fn();
    const p = createMockProfile({ id: 'dev' });
    render(<ProfileCard profile={p} onConfigure={onConfigure} onActivate={vi.fn()} onDelete={vi.fn()} />);
    await user.click(screen.getByText('dev'));
    expect(onConfigure).toHaveBeenCalledWith(p);
  });

  it('calls onActivate from the always-visible star without configuring', async () => {
    const user = userEvent.setup();
    const onActivate = vi.fn();
    const onConfigure = vi.fn();
    const p = createMockProfile({ id: 'dev', is_active: false });
    render(<ProfileCard profile={p} onConfigure={onConfigure} onActivate={onActivate} onDelete={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /set .*active/i }));
    expect(onActivate).toHaveBeenCalledWith(p);
    expect(onConfigure).not.toHaveBeenCalled();
  });

  it('exposes delete without hover', () => {
    const p = createMockProfile({ id: 'dev' });
    render(<ProfileCard profile={p} onConfigure={vi.fn()} onActivate={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole('button', { name: /delete profile dev/i })).toBeVisible();
  });
});
