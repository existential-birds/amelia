/**
 * @fileoverview Card component for displaying a prompt summary.
 *
 * Shows prompt name, description, version status, and provides
 * edit and reset actions.
 */
import { Pencil, RotateCcw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { PromptSummary } from '@/types';

interface PromptCardProps {
  /** The prompt summary to display. */
  prompt: PromptSummary;
  /** Callback when the edit button is clicked. */
  onEdit: (promptId: string) => void;
  /** Callback when the reset button is clicked. */
  onReset: (promptId: string) => void;
}

/**
 * Displays a prompt as a card with name, description, and actions.
 *
 * The card shows:
 * - Prompt name and description
 * - A badge showing "Default" or the version number
 * - Edit button to open the edit modal
 * - Reset button (only visible for custom versions)
 *
 * @param props - Component props.
 * @param props.prompt - The prompt summary to display.
 * @param props.onEdit - Callback when edit is clicked.
 * @param props.onReset - Callback when reset is clicked.
 * @returns The prompt card component.
 *
 * @example
 * ```tsx
 * <PromptCard
 *   prompt={prompt}
 *   onEdit={(id) => openEditModal(id)}
 *   onReset={(id) => confirmReset(id)}
 * />
 * ```
 */
export function PromptCard({ prompt, onEdit, onReset }: PromptCardProps) {
  const isCustom = prompt.current_version_id !== null;
  const versionLabel = isCustom
    ? `v${prompt.current_version_number}`
    : 'Default';

  return (
    <Card className="transition-all hover:border-primary/30">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base truncate">{prompt.name}</CardTitle>
            {prompt.description && (
              <CardDescription className="mt-1 line-clamp-2">
                {prompt.description}
              </CardDescription>
            )}
          </div>
          <Badge variant={isCustom ? 'default' : 'secondary'}>
            {versionLabel}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onEdit(prompt.id)}
            className="flex-1"
          >
            <Pencil className="size-3.5 mr-1.5" />
            Edit
          </Button>
          {isCustom && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onReset(prompt.id)}
              className="text-muted-foreground hover:text-destructive"
            >
              <RotateCcw className="size-3.5 mr-1.5" />
              Reset
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
