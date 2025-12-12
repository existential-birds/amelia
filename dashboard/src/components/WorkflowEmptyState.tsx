/**
 * @fileoverview Empty state component for workflow-related screens.
 */
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from '@/components/ui/empty';
import { Button } from '@/components/ui/button';
import { Inbox, Activity, AlertCircle, FileX } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Available empty state variants for different contexts. */
type EmptyStateVariant = 'no-workflows' | 'no-activity' | 'no-results' | 'error';

/**
 * Props for the WorkflowEmptyState component.
 * @property variant - Type of empty state to display
 * @property title - Optional override for the default title
 * @property description - Optional override for the default description
 * @property action - Optional action button configuration
 * @property className - Optional additional CSS classes
 */
interface WorkflowEmptyStateProps {
  variant: EmptyStateVariant;
  title?: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

/** Default configuration for each empty state variant. */
const variantConfig: Record<EmptyStateVariant, {
  icon: typeof Inbox;
  title: string;
  description: string;
}> = {
  'no-workflows': {
    icon: Inbox,
    title: 'No Active Workflows',
    description: 'Start a new workflow to see it here. Workflows track issue progress through the development pipeline.',
  },
  'no-activity': {
    icon: Activity,
    title: 'No Activity Yet',
    description: 'Activity will appear here once the workflow starts processing.',
  },
  'no-results': {
    icon: FileX,
    title: 'No Results Found',
    description: 'Try adjusting your search or filter criteria.',
  },
  'error': {
    icon: AlertCircle,
    title: 'Something Went Wrong',
    description: 'An error occurred while loading. Please try again.',
  },
};

/**
 * Displays a contextual empty state with icon, message, and optional action.
 *
 * Supports multiple variants for different scenarios (no workflows,
 * no activity, no results, error). Title and description can be overridden.
 *
 * @param props - Component props
 * @returns The empty state UI
 *
 * @example
 * ```tsx
 * <WorkflowEmptyState
 *   variant="no-workflows"
 *   action={{ label: 'Start Workflow', onClick: handleStart }}
 * />
 * ```
 */
export function WorkflowEmptyState({
  variant,
  title,
  description,
  action,
  className,
}: WorkflowEmptyStateProps) {
  const config = variantConfig[variant];
  const Icon = config.icon;

  return (
    <Empty className={cn('py-12', className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon className="size-6" />
        </EmptyMedia>

        <EmptyTitle className="font-heading">
          {title ?? config.title}
        </EmptyTitle>

        <EmptyDescription>
          {description ?? config.description}
        </EmptyDescription>
      </EmptyHeader>

      {action && (
        <EmptyContent>
          <Button
            variant="outline"
            onClick={action.onClick}
            className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
          >
            {action.label}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}
