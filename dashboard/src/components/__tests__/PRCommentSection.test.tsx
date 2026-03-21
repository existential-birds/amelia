import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PRCommentSection } from '../PRCommentSection';
import type { PRCommentData } from '@/types';

const mockComments: PRCommentData[] = [
  {
    comment_id: 1,
    file_path: 'src/auth.ts',
    line: 42,
    body: 'This function should validate the token before proceeding with the request handler.',
    author: 'reviewer1',
    status: 'fixed',
    status_reason: null,
    html_url: 'https://github.com/org/repo/pull/1/comment/1',
  },
  {
    comment_id: 2,
    file_path: 'src/db.ts',
    line: 10,
    body: 'Consider using a connection pool here instead of creating new connections.',
    author: 'reviewer2',
    status: 'fixed',
    status_reason: null,
    html_url: 'https://github.com/org/repo/pull/1/comment/2',
  },
  {
    comment_id: 3,
    file_path: 'src/utils.ts',
    line: 5,
    body: 'This helper is duplicated in three files, extract to shared module.',
    author: 'reviewer1',
    status: 'failed',
    status_reason: 'Circular dependency detected',
    html_url: 'https://github.com/org/repo/pull/1/comment/3',
  },
  {
    comment_id: 4,
    file_path: null,
    line: null,
    body: 'Overall looks good, just minor style nits.',
    author: 'reviewer3',
    status: 'skipped',
    status_reason: 'Below aggressiveness threshold',
    html_url: 'https://github.com/org/repo/pull/1/comment/4',
  },
];

describe('PRCommentSection', () => {
  it('renders summary bar with correct fixed/failed/skipped counts', () => {
    render(<PRCommentSection comments={mockComments} />);
    expect(screen.getByText('2 fixed')).toBeInTheDocument();
    expect(screen.getByText('1 failed')).toBeInTheDocument();
    expect(screen.getByText('1 skipped')).toBeInTheDocument();
  });

  it('renders file_path:line for each comment', () => {
    render(<PRCommentSection comments={mockComments} />);
    expect(screen.getByText('src/auth.ts:42')).toBeInTheDocument();
    expect(screen.getByText('src/db.ts:10')).toBeInTheDocument();
    expect(screen.getByText('src/utils.ts:5')).toBeInTheDocument();
  });

  it('renders "General" when file_path is null', () => {
    render(<PRCommentSection comments={mockComments} />);
    expect(screen.getByText('General')).toBeInTheDocument();
  });

  it('renders external link with correct href', () => {
    render(<PRCommentSection comments={mockComments} />);
    const links = screen.getAllByRole('link');
    expect(links.length).toBe(4);
    expect(links[0]).toHaveAttribute('href', 'https://github.com/org/repo/pull/1/comment/1');
    expect(links[0]).toHaveAttribute('target', '_blank');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('handles empty comments array gracefully', () => {
    render(<PRCommentSection comments={[]} />);
    // Should render without crashing, showing zero counts
    expect(screen.getByText('0 fixed')).toBeInTheDocument();
    expect(screen.getByText('0 failed')).toBeInTheDocument();
    expect(screen.getByText('0 skipped')).toBeInTheDocument();
  });

  it('renders section header', () => {
    render(<PRCommentSection comments={mockComments} />);
    expect(screen.getByText('REVIEW COMMENTS')).toBeInTheDocument();
  });

  it('renders status_reason text when a comment row is expanded', async () => {
    render(<PRCommentSection comments={mockComments} />);
    // The failed comment (3rd row, index 2) has status_reason 'Circular dependency detected'
    const triggers = screen.getAllByRole('button');
    // Click the 3rd trigger to expand the failed comment
    await triggers[2].click();
    expect(screen.getByText(/Circular dependency detected/)).toBeInTheDocument();
  });
});
