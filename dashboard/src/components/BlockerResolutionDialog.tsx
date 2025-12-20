/**
 * @fileoverview Blocker resolution dialog for workflow execution blockers.
 */
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { BlockerReport } from '@/types';
import { cn } from '@/lib/utils';
import { AlertCircle, RefreshCw, SkipForward, Wrench, XCircle } from 'lucide-react';

/**
 * Props for the BlockerResolutionDialog component.
 * @property blocker - The blocker report containing error details
 * @property cascadeSkips - Optional list of step IDs that will be skipped if this step is skipped
 * @property isOpen - Whether the dialog is open
 * @property onClose - Callback when dialog is closed
 * @property onRetry - Callback when retry is selected
 * @property onSkip - Callback when skip step is selected
 * @property onFixInstruction - Callback when fix instruction is provided
 * @property onAbort - Callback when abort is selected (param: revert batch)
 */
interface BlockerResolutionDialogProps {
  blocker: BlockerReport;
  cascadeSkips?: string[];
  isOpen: boolean;
  onClose: () => void;
  onRetry: () => void;
  onSkip: () => void;
  onFixInstruction: (instruction: string) => void;
  onAbort: (revert: boolean) => void;
  error?: string | null;
}

/**
 * Modal for blocker resolution with multiple resolution options.
 *
 * Displays blocker details and provides options to:
 * - Retry the step
 * - Skip the step (with cascade warning)
 * - Provide fix instruction
 * - Abort (keep changes or revert batch)
 *
 * @param props - Component props
 * @returns The blocker resolution dialog UI
 *
 * @example
 * ```tsx
 * <BlockerResolutionDialog
 *   blocker={blockerReport}
 *   cascadeSkips={['step-2', 'step-3']}
 *   isOpen={true}
 *   onClose={() => setOpen(false)}
 *   onRetry={() => console.log('Retrying...')}
 *   onSkip={() => console.log('Skipping...')}
 *   onFixInstruction={(instruction) => console.log('Fix:', instruction)}
 *   onAbort={(revert) => console.log('Abort, revert:', revert)}
 * />
 * ```
 */
export function BlockerResolutionDialog({
  blocker,
  cascadeSkips,
  isOpen,
  onClose,
  onRetry,
  onSkip,
  onFixInstruction,
  onAbort,
  error,
}: BlockerResolutionDialogProps) {
  const [fixInstruction, setFixInstruction] = useState('');
  const [showKeepChangesAlert, setShowKeepChangesAlert] = useState(false);
  const [showRevertAlert, setShowRevertAlert] = useState(false);

  const hasCascadeSkips = cascadeSkips && cascadeSkips.length > 0;

  const handleApplyFix = () => {
    if (fixInstruction.trim()) {
      onFixInstruction(fixInstruction);
      setFixInstruction('');
    }
  };

  const handleKeepChanges = () => {
    setShowKeepChangesAlert(false);
    onAbort(false);
  };

  const handleRevertBatch = () => {
    setShowRevertAlert(false);
    onAbort(true);
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-destructive" />
              Execution Blocked
            </DialogTitle>
            <DialogDescription>
              Step {blocker.step_id} encountered a blocker. Choose how to proceed.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Blocker Details */}
            <div className="space-y-3">
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">Step Details</h4>
                <p className="text-sm font-mono bg-muted px-3 py-2 rounded-md">{blocker.step_id}</p>
                <p className="text-sm mt-2">{blocker.step_description}</p>
              </div>

              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">Blocker Type</h4>
                <Badge variant="destructive">{blocker.blocker_type}</Badge>
              </div>

              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">Error Message</h4>
                <p className="text-sm bg-destructive/10 text-destructive px-3 py-2 rounded-md border border-destructive/20">
                  {blocker.error_message}
                </p>
              </div>

              {blocker.attempted_actions.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">Attempted Actions</h4>
                  <ul className="text-sm space-y-1">
                    {blocker.attempted_actions.map((action, index) => (
                      <li key={`${action}-${index}`} className="flex items-start gap-2">
                        <span className="text-muted-foreground mt-0.5">•</span>
                        <span>{action}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {blocker.suggested_resolutions.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">AI Suggestions</h4>
                  <ul className="text-sm space-y-1">
                    {blocker.suggested_resolutions.map((suggestion, index) => (
                      <li key={`${suggestion}-${index}`} className="flex items-start gap-2">
                        <span className="text-muted-foreground mt-0.5">•</span>
                        <span>{suggestion}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Resolution Options */}
            <div className="border-t pt-4 space-y-4">
              <h3 className="font-heading text-base font-semibold">Resolution Options</h3>

              {error && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md border border-destructive/20">
                  {error}
                </p>
              )}

              {/* Retry */}
              <div className="flex flex-col gap-2">
                <Button onClick={onRetry} className="w-full justify-start gap-2">
                  <RefreshCw className="w-4 h-4" />
                  Retry Step
                </Button>
              </div>

              {/* Skip */}
              <div className="flex flex-col gap-2">
                <Button
                  onClick={onSkip}
                  variant="outline"
                  className="w-full justify-start gap-2 border-yellow-500/50 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/10"
                >
                  <SkipForward className="w-4 h-4" />
                  Skip Step
                  {hasCascadeSkips && (
                    <Badge variant="outline" className="ml-auto border-yellow-500/50 text-yellow-700 dark:text-yellow-400">
                      {cascadeSkips.length}
                    </Badge>
                  )}
                </Button>

                {hasCascadeSkips && (
                  <div className="ml-6 text-xs text-muted-foreground bg-yellow-500/5 px-3 py-2 rounded-md border border-yellow-500/20">
                    <p className="font-medium mb-1">Skipping this step will also skip:</p>
                    <ul className="space-y-0.5">
                      {cascadeSkips.map((stepId) => (
                        <li key={stepId} className="font-mono">
                          {stepId}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Fix Instruction */}
              <div className="flex flex-col gap-2">
                <label htmlFor="fix-instruction" className="text-sm font-medium">
                  Provide Fix Instruction
                </label>
                <textarea
                  id="fix-instruction"
                  value={fixInstruction}
                  onChange={(e) => setFixInstruction(e.target.value)}
                  placeholder="Describe the fix you want the agent to apply..."
                  rows={3}
                  className={cn(
                    'placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input w-full min-w-0 rounded-md border bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm resize-none',
                    'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]'
                  )}
                />
                <Button
                  onClick={handleApplyFix}
                  disabled={!fixInstruction.trim()}
                  variant="outline"
                  className="w-full justify-start gap-2"
                >
                  <Wrench className="w-4 h-4" />
                  Apply Fix
                </Button>
              </div>

              {/* Abort Options */}
              <div className="border-t pt-4">
                <h4 className="text-sm font-medium text-muted-foreground mb-2">Abort Options</h4>
                <div className="flex gap-2">
                  <Button
                    onClick={() => setShowKeepChangesAlert(true)}
                    variant="outline"
                    className="flex-1 justify-start gap-2 border-destructive/50 text-destructive hover:bg-destructive/10"
                  >
                    <XCircle className="w-4 h-4" />
                    Keep Changes
                  </Button>
                  <Button
                    onClick={() => setShowRevertAlert(true)}
                    variant="outline"
                    className="flex-1 justify-start gap-2 border-destructive/50 text-destructive hover:bg-destructive/10"
                  >
                    <XCircle className="w-4 h-4" />
                    Revert Batch
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Keep Changes Confirmation */}
      <AlertDialog open={showKeepChangesAlert} onOpenChange={setShowKeepChangesAlert}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure you want to abort and keep changes?</AlertDialogTitle>
            <AlertDialogDescription>
              This will stop execution and keep all changes made so far in this batch. The batch will be
              marked as partial, and you can manually complete or fix the remaining steps.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleKeepChanges}
              className="bg-destructive hover:bg-destructive/90 focus-visible:ring-destructive/50"
            >
              Keep Changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Revert Batch Confirmation */}
      <AlertDialog open={showRevertAlert} onOpenChange={setShowRevertAlert}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure you want to abort and revert?</AlertDialogTitle>
            <AlertDialogDescription>
              This will stop execution and revert all changes made in this batch. The worktree will be
              restored to the state before the batch started. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevertBatch}
              className="bg-destructive hover:bg-destructive/90 focus-visible:ring-destructive/50"
            >
              Revert Batch
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
