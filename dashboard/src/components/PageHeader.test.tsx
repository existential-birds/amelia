import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders all three slots when provided', () => {
    render(
      <PageHeader>
        <PageHeader.Left>Left content</PageHeader.Left>
        <PageHeader.Center>Center content</PageHeader.Center>
        <PageHeader.Right>Right content</PageHeader.Right>
      </PageHeader>
    );

    expect(screen.getByText('Left content')).toBeInTheDocument();
    expect(screen.getByText('Center content')).toBeInTheDocument();
    expect(screen.getByText('Right content')).toBeInTheDocument();
  });

  it('positions slots correctly in grid layout', () => {
    render(
      <PageHeader>
        <PageHeader.Left>Left</PageHeader.Left>
        <PageHeader.Center>
          <span data-testid="center-inner">Centered</span>
        </PageHeader.Center>
        <PageHeader.Right>
          <span data-testid="right-inner">Right aligned</span>
        </PageHeader.Right>
      </PageHeader>
    );

    const centerInner = screen.getByTestId('center-inner');
    const centerSlot = centerInner.closest('[class*="justify-self-center"]');
    expect(centerSlot).toBeInTheDocument();

    const rightInner = screen.getByTestId('right-inner');
    const rightSlot = rightInner.closest('[class*="justify-self-end"]');
    expect(rightSlot).toHaveClass('flex');
  });
});
