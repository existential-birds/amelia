import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HostChipInput } from '../HostChipInput';

describe('HostChipInput', () => {
  it('adds a valid host and removes it', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<HostChipInput hosts={[]} onChange={onChange} />);
    await user.type(screen.getByPlaceholderText('api.example.com'), 'api.example.com');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange).toHaveBeenCalledWith(['api.example.com']);
    rerender(<HostChipInput hosts={['api.example.com']} onChange={onChange} />);
    await user.click(screen.getByRole('button', { name: /remove api\.example\.com/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('rejects an invalid hostname with an error', async () => {
    const user = userEvent.setup();
    render(<HostChipInput hosts={[]} onChange={vi.fn()} />);
    await user.type(screen.getByPlaceholderText('api.example.com'), 'not a host');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Invalid hostname')).toBeInTheDocument();
  });
});
