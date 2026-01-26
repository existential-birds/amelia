/**
 * @fileoverview Modal for setting a plan on a queued workflow.
 */
import { useState, useCallback } from 'react';
import { Loader } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '@/api/client';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { PlanImportSection, type PlanData } from './PlanImportSection';

export interface SetPlanModalProps {
  /** Whether the modal is open. */
  open: boolean;
  /** Callback when open state changes. */
  onOpenChange: (open: boolean) => void;
  /** The workflow ID to set the plan for. */
  workflowId: string;
  /** The worktree path for relative file resolution. */
  worktreePath: string;
  /** Whether the workflow already has a plan. */
  hasPlan?: boolean;
  /** Callback when plan is successfully applied. */
  onSuccess?: () => void;
}

/**
 * Modal for importing and applying an external plan to a queued workflow.
 */
export function SetPlanModal({
  open,
  onOpenChange,
  workflowId,
  worktreePath,
  hasPlan = false,
  onSuccess,
}: SetPlanModalProps) {
  const [planData, setPlanData] = useState<PlanData>({});
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const hasPlanData = !!(planData.plan_file || planData.plan_content);

  const handlePlanChange = useCallback((data: PlanData) => {
    setPlanData(data);
    setError(undefined);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!hasPlanData) return;

    setIsSubmitting(true);
    setError(undefined);

    try {
      const result = await api.setPlan(workflowId, {
        plan_file: planData.plan_file,
        plan_content: planData.plan_content,
        force: forceOverwrite,
      });

      const summary = result.total_tasks > 0
        ? `Plan applied: ${result.total_tasks} tasks`
        : 'Plan applied successfully';
      toast.success(summary);
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to apply plan');
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [workflowId, planData, forceOverwrite, onOpenChange, onSuccess, hasPlanData]);

  const handleCancel = useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Set Plan</DialogTitle>
          <DialogDescription>
            Import an external plan for this workflow. The plan will be used
            instead of generating one with the Architect.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <PlanImportSection
            onPlanChange={handlePlanChange}
            defaultExpanded
            error={error}
            worktreePath={worktreePath}
          />

          {hasPlan && (
            <div className="flex items-center gap-3">
              <Switch
                id="overwrite"
                checked={forceOverwrite}
                onCheckedChange={setForceOverwrite}
              />
              <Label htmlFor="overwrite" className="cursor-pointer">
                Overwrite existing plan
              </Label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!hasPlanData || isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loader className="w-4 h-4 mr-2 animate-spin" />
                Applying...
              </>
            ) : (
              'Apply Plan'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
