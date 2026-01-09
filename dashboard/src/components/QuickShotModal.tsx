/**
 * @fileoverview Quick Shot modal for starting noop tracker workflows.
 *
 * A "high-voltage command console" styled modal that allows users to
 * quickly launch workflows directly from the dashboard UI.
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Zap } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '@/api/client';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/**
 * Zod schema for Quick Shot form validation.
 * All fields are strings to match form defaults.
 */
const quickShotSchema = z.object({
  issue_id: z
    .string()
    .min(1, 'Task ID is required')
    .max(100, 'Task ID must be 100 characters or less')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Only letters, numbers, hyphens, and underscores'),
  worktree_path: z
    .string()
    .min(1, 'Worktree path is required')
    .regex(/^\//, 'Must be an absolute path'),
  profile: z
    .string()
    .regex(/^[a-z0-9_-]*$/, 'Lowercase letters, numbers, hyphens, and underscores only'),
  task_title: z
    .string()
    .min(1, 'Title is required')
    .max(500, 'Title must be 500 characters or less'),
  task_description: z
    .string()
    .max(5000, 'Description must be 5000 characters or less'),
});

type QuickShotFormData = z.infer<typeof quickShotSchema>;

/**
 * Props for the QuickShotModal component.
 */
interface QuickShotModalProps {
  /** Whether the modal is open. */
  open: boolean;
  /** Callback when the modal open state changes. */
  onOpenChange: (open: boolean) => void;
}

/**
 * Field configuration for rendering form fields.
 */
interface FieldConfig {
  name: keyof QuickShotFormData & string;
  label: string;
  placeholder: string;
  required: boolean;
  multiline?: boolean;
}

const fields: FieldConfig[] = [
  {
    name: 'issue_id',
    label: 'Task ID',
    placeholder: 'TASK-001',
    required: true,
  },
  {
    name: 'worktree_path',
    label: 'Worktree Path',
    placeholder: '/Users/me/projects/my-repo',
    required: true,
  },
  {
    name: 'profile',
    label: 'Profile',
    placeholder: 'noop-local',
    required: false,
  },
  {
    name: 'task_title',
    label: 'Task Title',
    placeholder: 'Add logout button to navbar',
    required: true,
  },
  {
    name: 'task_description',
    label: 'Description',
    placeholder: 'Add a logout button to the top navigation bar that clears the session and redirects to login...',
    required: false,
    multiline: true,
  },
];

/**
 * Quick Shot modal component for starting workflows.
 *
 * Features:
 * - Form validation with react-hook-form and zod
 * - Staggered field reveal animation
 * - "Charging" submit button with pulse animation
 * - Toast notifications for success/error states
 *
 * @param props - Component props
 * @param props.open - Whether the modal is open
 * @param props.onOpenChange - Callback when open state changes
 */
export function QuickShotModal({ open, onOpenChange }: QuickShotModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
  } = useForm<QuickShotFormData>({
    resolver: zodResolver(quickShotSchema),
    mode: 'all',
    defaultValues: {
      issue_id: '',
      worktree_path: '',
      profile: '',
      task_title: '',
      task_description: '',
    },
  });

  const onSubmit = async (data: QuickShotFormData) => {
    setIsLaunching(true);
    // Brief ripple animation
    await new Promise((r) => setTimeout(r, 400));
    setIsLaunching(false);
    setIsSubmitting(true);

    try {
      const result = await api.createWorkflow({
        issue_id: data.issue_id,
        worktree_path: data.worktree_path,
        profile: data.profile || undefined,
        task_title: data.task_title,
        task_description: data.task_description || undefined,
      });
      toast.success(
        <span>
          Workflow started:{' '}
          <a
            href={`/workflows/${result.id}`}
            className="underline hover:text-primary"
          >
            {result.id}
          </a>
        </span>
      );
      reset();
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.message);
      } else {
        toast.error('Connection failed. Check your network.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="sm:max-w-[560px] bg-card border-border"
        showCloseButton={true}
      >
        <DialogHeader className="border-b border-border pb-4">
          <DialogTitle className="flex items-center gap-2 text-2xl font-display tracking-wider text-primary">
            <Zap className="h-6 w-6" />
            QUICK SHOT
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-4">
          {fields.map((field, index) => (
            <div
              key={field.name}
              className="animate-quick-shot-field"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div className="relative">
                <Label
                  htmlFor={field.name}
                  className="absolute -top-2 left-3 bg-card px-1 text-[11px] font-heading uppercase tracking-wider text-muted-foreground"
                >
                  {field.label}
                  {field.required && (
                    <span className="ml-1 text-primary">*</span>
                  )}
                </Label>
                {field.multiline ? (
                  <Textarea
                    id={field.name}
                    placeholder={field.placeholder}
                    aria-invalid={!!errors[field.name]}
                    aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
                    className={cn(
                      'mt-1 font-mono text-sm bg-background border-input',
                      'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
                      errors[field.name] && 'border-destructive'
                    )}
                    rows={3}
                    {...register(field.name)}
                  />
                ) : (
                  <Input
                    id={field.name}
                    placeholder={field.placeholder}
                    aria-invalid={!!errors[field.name]}
                    aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
                    className={cn(
                      'mt-1 font-mono text-sm bg-background border-input',
                      'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
                      errors[field.name] && 'border-destructive'
                    )}
                    {...register(field.name)}
                  />
                )}
                {errors[field.name] && (
                  <p id={`${field.name}-error`} className="mt-1 text-xs text-destructive">
                    {errors[field.name]?.message}
                  </p>
                )}
              </div>
            </div>
          ))}

          <DialogFooter className="gap-2 pt-4">
            <Button
              type="button"
              variant="secondary"
              onClick={handleClose}
              className="font-heading uppercase tracking-wide"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!isValid || isSubmitting || isLaunching}
              className={cn(
                'font-heading uppercase tracking-wide relative overflow-hidden',
                'transition-all duration-normal',
                isValid && !isSubmitting && 'animate-quick-shot-charge',
                isLaunching && 'after:absolute after:inset-0 after:animate-quick-shot-ripple after:bg-primary/20 after:rounded-[inherit]'
              )}
            >
              {isSubmitting ? (
                <>
                  <span className="absolute inset-0 bg-gradient-to-r from-transparent via-primary-foreground/30 to-transparent animate-quick-shot-scan" />
                  Launching...
                </>
              ) : (
                <>
                  <Zap className="mr-2 h-4 w-4" />
                  Start Workflow
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
