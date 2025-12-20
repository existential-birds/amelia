/**
 * @fileoverview Agent progress bar showing workflow stages.
 */
import { Check, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Agent stage identifier type.
 */
export type AgentStage = 'pm' | 'architect' | 'developer' | 'reviewer';

/**
 * Props for the AgentProgressBar component.
 * @property currentStage - The stage currently in progress (null if none)
 * @property completedStages - Array of completed stages
 * @property className - Optional additional CSS classes
 */
export interface AgentProgressBarProps {
  currentStage: AgentStage | null;
  completedStages: AgentStage[];
  className?: string;
}

/**
 * Stage configuration for display.
 */
interface StageConfig {
  id: AgentStage;
  label: string;
}

/**
 * Ordered list of agent stages.
 */
const STAGES: StageConfig[] = [
  { id: 'pm', label: 'PM' },
  { id: 'architect', label: 'Architect' },
  { id: 'developer', label: 'Developer' },
  { id: 'reviewer', label: 'Reviewer' },
];

/**
 * Compact horizontal stepper showing agent workflow progress.
 *
 * Displays PM → Architect → Developer → Reviewer with visual indicators:
 * - Completed stages: checkmark icon with muted styling
 * - Current stage: highlighted with primary color and pulse animation
 * - Pending stages: muted/greyed out appearance
 *
 * Uses data-slot attributes for styling hooks and semantic HTML for accessibility.
 *
 * @param props - Component props
 * @returns The agent progress bar UI
 *
 * @example
 * ```tsx
 * <AgentProgressBar
 *   currentStage="developer"
 *   completedStages={['pm', 'architect']}
 * />
 * ```
 */
export function AgentProgressBar({
  currentStage,
  completedStages,
  className,
}: AgentProgressBarProps) {
  const isCompleted = (stageId: AgentStage) =>
    completedStages.includes(stageId) && currentStage !== stageId;
  const isCurrent = (stageId: AgentStage) => currentStage === stageId;
  const isPending = (stageId: AgentStage) =>
    !isCompleted(stageId) && !isCurrent(stageId);

  return (
    <nav
      data-slot="agent-progress-bar"
      aria-label="Agent workflow progress"
      className={cn('flex items-center gap-2', className)}
    >
      <ol className="flex items-center gap-2">
        {STAGES.map((stage, index) => {
          const completed = isCompleted(stage.id);
          const current = isCurrent(stage.id);
          const pending = isPending(stage.id);

          return (
            <li key={stage.id} className="flex items-center gap-2">
              <div
                data-slot="stage-item"
                data-completed={completed || undefined}
                data-current={current || undefined}
                data-pending={pending || undefined}
                aria-current={current ? 'step' : undefined}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-all',
                  // Completed state
                  completed && 'bg-muted text-muted-foreground',
                  // Current state
                  current &&
                    'bg-primary/10 text-primary border border-primary/30 shadow-sm',
                  // Pending state
                  pending && 'text-muted-foreground/50'
                )}
              >
                {completed && (
                  <Check className="size-4 shrink-0" aria-hidden="true" />
                )}
                {current && (
                  <span
                    className="size-2 shrink-0 rounded-full bg-primary animate-pulse"
                    aria-hidden="true"
                  />
                )}
                <span className="whitespace-nowrap">{stage.label}</span>
              </div>

              {/* Connector arrow between stages */}
              {index < STAGES.length - 1 && (
                <ChevronRight
                  className={cn(
                    'size-4 shrink-0 transition-colors',
                    completed ? 'text-muted-foreground' : 'text-muted-foreground/30'
                  )}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
