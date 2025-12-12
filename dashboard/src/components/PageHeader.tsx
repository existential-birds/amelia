/**
 * @fileoverview Compound component for consistent page headers across views.
 *
 * Provides a flexible 3-column grid layout with slots that conditionally
 * render based on content presence. Includes typography helpers for
 * consistent styling.
 */
import { Children, isValidElement, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

/* ==========================================================================
   Typography Helpers
   ========================================================================== */

interface TypographyProps {
  children: ReactNode;
  className?: string;
}

/**
 * Small uppercase label text (e.g., "WORKFLOW", "ELAPSED").
 */
function Label({ children, className }: TypographyProps) {
  return (
    <span
      className={cn(
        'block font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-1',
        className
      )}
    >
      {children}
    </span>
  );
}

/**
 * Large display title (e.g., issue ID, page title).
 */
function Title({ children, className }: TypographyProps) {
  return (
    <h2
      className={cn(
        'font-display text-3xl font-bold tracking-wider text-foreground',
        className
      )}
    >
      {children}
    </h2>
  );
}

/**
 * Secondary text next to title (e.g., worktree name).
 */
function Subtitle({ children, className }: TypographyProps) {
  return (
    <span className={cn('font-mono text-sm text-muted-foreground', className)}>
      {children}
    </span>
  );
}

interface ValueProps extends TypographyProps {
  /** Adds glowing text shadow effect */
  glow?: boolean;
}

/**
 * Large monospace value display (e.g., elapsed time, counts).
 */
function Value({ children, glow, className }: ValueProps) {
  return (
    <div
      className={cn(
        'font-mono text-2xl font-semibold text-primary',
        glow && '[text-shadow:0_0_10px_rgba(255,200,87,0.4)]',
        className
      )}
    >
      {children}
    </div>
  );
}

/* ==========================================================================
   Slot Components
   ========================================================================== */

interface SlotProps {
  children: ReactNode;
  className?: string;
}

/**
 * Left slot - primary content area (title, subtitle).
 */
function Left({ children, className }: SlotProps) {
  return <div className={className}>{children}</div>;
}
Left.displayName = 'PageHeader.Left';

/**
 * Center slot - centered content (elapsed time, stats).
 */
function Center({ children, className }: SlotProps) {
  return (
    <div className={cn('text-center justify-self-center', className)}>
      {children}
    </div>
  );
}
Center.displayName = 'PageHeader.Center';

/**
 * Right slot - status/actions area with container styling.
 */
function Right({ children, className }: SlotProps) {
  return (
    <div className={cn('flex items-center gap-2 justify-self-end', className)}>
      {children}
    </div>
  );
}
Right.displayName = 'PageHeader.Right';

/* ==========================================================================
   Main Component
   ========================================================================== */

interface PageHeaderProps {
  children: ReactNode;
  className?: string;
}

/**
 * Flexible page header with 3-column grid layout.
 *
 * Slots (Left, Center, Right) conditionally render based on presence.
 * Grid columns adapt to which slots have content.
 *
 * @example
 * ```tsx
 * <PageHeader>
 *   <PageHeader.Left>
 *     <PageHeader.Label>WORKFLOW</PageHeader.Label>
 *     <PageHeader.Title>ISSUE-123</PageHeader.Title>
 *   </PageHeader.Left>
 *   <PageHeader.Center>
 *     <PageHeader.Label>ELAPSED</PageHeader.Label>
 *     <PageHeader.Value glow>02:34</PageHeader.Value>
 *   </PageHeader.Center>
 *   <PageHeader.Right>
 *     <StatusBadge status="in_progress" />
 *   </PageHeader.Right>
 * </PageHeader>
 * ```
 */
function PageHeader({ children, className }: PageHeaderProps) {
  // Extract slot children by displayName
  let leftSlot: ReactNode = null;
  let centerSlot: ReactNode = null;
  let rightSlot: ReactNode = null;

  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return;

    const displayName = (child.type as { displayName?: string }).displayName;
    switch (displayName) {
      case 'PageHeader.Left':
        leftSlot = child;
        break;
      case 'PageHeader.Center':
        centerSlot = child;
        break;
      case 'PageHeader.Right':
        rightSlot = child;
        break;
    }
  });

  // Determine grid columns based on which slots are present
  const hasCenter = centerSlot !== null;
  const hasRight = rightSlot !== null;

  // Use 3-column grid with equal outer columns for true centering
  // Left and right get 1fr each, center is auto-sized but truly centered
  let gridCols = '';
  if (hasCenter && hasRight) {
    gridCols = 'grid-cols-[1fr_auto_1fr]';
  } else if (hasCenter) {
    gridCols = 'grid-cols-[1fr_auto_1fr]';
  } else if (hasRight) {
    gridCols = 'grid-cols-[1fr_auto]';
  } else {
    gridCols = 'grid-cols-1';
  }

  return (
    <header
      role="banner"
      data-slot="page-header"
      className={cn(
        'grid w-full items-center px-6 py-4 border-b border-border bg-card/50',
        gridCols,
        className
      )}
    >
      {leftSlot}
      {centerSlot}
      {rightSlot}
    </header>
  );
}

// Attach sub-components
PageHeader.Left = Left;
PageHeader.Center = Center;
PageHeader.Right = Right;
PageHeader.Label = Label;
PageHeader.Title = Title;
PageHeader.Subtitle = Subtitle;
PageHeader.Value = Value;

export { PageHeader };
