/**
 * @fileoverview Modal for editing prompt content.
 *
 * Provides a large textarea for editing prompt content, character count
 * with progressive color feedback, change note input, and save/reset actions.
 */
import { useState, useEffect, useCallback } from 'react';
import { RotateCcw, Save, Loader2, Pencil } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { getAgentAccentStyle } from '@/lib/constants';
import { api } from '@/api/client';
import { success, error as showError } from '@/components/Toast';
import type { DefaultContent } from '@/types';

/** Character count thresholds for progressive color feedback. */
const CHAR_THRESHOLDS = {
  healthy: 5000,
  long: 8000,
  warning: 10000,
} as const;

/**
 * Get color classes based on character count.
 *
 * Returns progressively warmer colors as character count increases:
 * - Green (healthy): 0-5000 characters
 * - Amber (long): 5001-8000 characters
 * - Orange (warning): 8001-10000 characters
 * - Red (danger): 10001+ characters
 *
 * @param count - The current character count.
 * @returns Object containing Tailwind CSS classes for text, background, and border colors.
 */
function getCharCountColors(count: number): {
  text: string;
  bg: string;
  border: string;
} {
  if (count <= CHAR_THRESHOLDS.healthy) {
    return {
      text: 'text-emerald-600 dark:text-emerald-400',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/30',
    };
  }
  if (count <= CHAR_THRESHOLDS.long) {
    return {
      text: 'text-amber-600 dark:text-amber-400',
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/30',
    };
  }
  if (count <= CHAR_THRESHOLDS.warning) {
    return {
      text: 'text-orange-600 dark:text-orange-400',
      bg: 'bg-orange-500/10',
      border: 'border-orange-500/30',
    };
  }
  return {
    text: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
  };
}

interface PromptEditModalProps {
  /** The prompt ID being edited. */
  promptId: string | null;
  /** The prompt name for display. */
  promptName: string;
  /** The agent this prompt belongs to (for accent colors). */
  agent: string;
  /** Whether the modal is open. */
  open: boolean;
  /** Callback to close the modal. */
  onOpenChange: (open: boolean) => void;
  /** Callback when a new version is saved. */
  onSave: () => void;
}

/**
 * Modal for editing prompt content.
 *
 * Features:
 * - Loads default content when opened
 * - Large textarea for editing
 * - Character count with warning for long prompts
 * - Change note input
 * - Reset to default button
 * - Save button that creates a new version
 *
 * @param props - Component props.
 * @returns The prompt edit modal component.
 *
 * @example
 * ```tsx
 * <PromptEditModal
 *   promptId="architect.system"
 *   promptName="Architect System Prompt"
 *   agent="architect"
 *   open={isOpen}
 *   onOpenChange={setIsOpen}
 *   onSave={() => revalidate()}
 * />
 * ```
 */
export function PromptEditModal({
  promptId,
  promptName,
  agent,
  open,
  onOpenChange,
  onSave,
}: PromptEditModalProps) {
  const [content, setContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [defaultData, setDefaultData] = useState<DefaultContent | null>(null);

  // Get agent-specific accent styles (always defined due to fallback)
  const accentStyle = getAgentAccentStyle(agent);

  // Load prompt content when modal opens
  useEffect(() => {
    if (!open || !promptId) {
      return;
    }

    const loadContent = async () => {
      setIsLoading(true);
      try {
        // Get default content
        const defaultContent = await api.getPromptDefault(promptId);
        setDefaultData(defaultContent);

        // Get current version if exists
        const prompt = await api.getPrompt(promptId);
        if (prompt.current_version_id) {
          // Fetch the current version content
          const currentVersion = await api.getPromptVersion(
            promptId,
            prompt.current_version_id
          );
          setContent(currentVersion.content);
          setOriginalContent(currentVersion.content);
        } else {
          // No custom version, use default
          setContent(defaultContent.content);
          setOriginalContent(defaultContent.content);
        }
      } catch (err) {
        showError('Failed to load prompt content');
        console.error('Failed to load prompt:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadContent();
  }, [open, promptId]);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      setContent('');
      setOriginalContent('');
      setChangeNote('');
      setDefaultData(null);
    }
  }, [open]);

  const handleResetToDefault = useCallback(() => {
    if (defaultData) {
      setContent(defaultData.content);
    }
  }, [defaultData]);

  const handleSave = useCallback(async () => {
    if (!promptId || !content.trim()) {
      return;
    }

    setIsSaving(true);
    try {
      await api.createPromptVersion(promptId, content, changeNote || null);
      success('Prompt saved successfully');
      onSave();
      onOpenChange(false);
    } catch (err) {
      showError('Failed to save prompt');
      console.error('Failed to save prompt:', err);
    } finally {
      setIsSaving(false);
    }
  }, [promptId, content, changeNote, onSave, onOpenChange]);

  const hasChanges = content !== originalContent;
  const charCount = content.length;
  const charColors = getCharCountColors(charCount);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          'max-w-4xl h-[80vh] flex flex-col gap-0 p-0 overflow-hidden',
          'border-2',
          accentStyle.border,
          'shadow-2xl',
          accentStyle.shadow,
          'bg-background'
        )}
      >
        {/* Header with agent-specific accent gradient */}
        <DialogHeader
          className={cn(
            'px-6 pt-6 pb-4 border-b border-border/50 bg-gradient-to-r',
            accentStyle.headerGradient
          )}
        >
          <div className="flex items-center gap-3">
            <div className={cn('p-2 rounded-lg', accentStyle.iconBg)}>
              <Pencil className={cn('size-4', accentStyle.iconText)} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <DialogTitle className="text-lg">{promptName}</DialogTitle>
                {hasChanges && (
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                    Modified
                  </span>
                )}
              </div>
              <DialogDescription className="mt-0.5">
                Edit the prompt content below. Changes will create a new
                version.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 flex flex-col gap-4 p-6 overflow-hidden">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2
                className={cn('size-6 animate-spin', accentStyle.iconText)}
              />
            </div>
          ) : (
            <>
              {/* Textarea with enhanced styling */}
              <div className="flex-1 flex flex-col min-h-0">
                <label htmlFor="prompt-content" className="sr-only">
                  Prompt content
                </label>
                <textarea
                  id="prompt-content"
                  aria-describedby="char-count"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className={cn(
                    'flex-1 w-full min-h-0 resize-none rounded-lg border-2 px-4 py-3 text-xs font-mono leading-snug',
                    'bg-muted',
                    'placeholder:text-muted-foreground/60',
                    'focus-visible:outline-none focus-visible:ring-4',
                    accentStyle.focusRing,
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    'border-border/50 hover:border-border transition-colors'
                  )}
                  placeholder="Enter prompt content..."
                />
              </div>

              {/* Character count with progressive colors */}
              <div className="flex items-center justify-between gap-4">
                <div
                  id="char-count"
                  role="status"
                  aria-live="polite"
                  className={cn(
                    'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors',
                    charColors.text,
                    charColors.bg,
                    charColors.border
                  )}
                >
                  <span className="tabular-nums">
                    {charCount.toLocaleString()}
                  </span>
                  <span className="opacity-70">characters</span>
                </div>

                {/* Change note - streamlined without redundant label */}
                <Input
                  id="change-note"
                  aria-label="Change note"
                  value={changeNote}
                  onChange={(e) => setChangeNote(e.target.value)}
                  placeholder="Change note (optional)"
                  className={cn(
                    'flex-1 max-w-sm border-border/50',
                    accentStyle.focusRing
                  )}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t border-border/50 bg-muted gap-2">
          <Button
            variant="ghost"
            onClick={handleResetToDefault}
            disabled={isLoading || isSaving || !defaultData}
            className="text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-4 mr-2" />
            Reset to default
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
            className="border-border/50"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={isLoading || isSaving || !hasChanges || !content.trim()}
            aria-busy={isSaving}
            className={cn(
              'text-white shadow-lg',
              accentStyle.button,
              accentStyle.buttonShadow
            )}
          >
            {isSaving ? (
              <Loader2 className="size-4 mr-2 animate-spin" />
            ) : (
              <Save className="size-4 mr-2" />
            )}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
