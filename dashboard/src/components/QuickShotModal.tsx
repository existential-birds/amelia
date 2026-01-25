/**
 * @fileoverview Quick Shot modal for starting workflows without issue tracker.
 *
 * A "high-voltage command console" styled modal that allows users to
 * quickly launch workflows directly from the dashboard UI.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Zap, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '@/api/client';
import { extractTitle, extractTitleFromFilename, generateDesignId, buildDescriptionReference } from '@/lib/design-doc';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { WorktreePathField } from '@/components/WorktreePathField';
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
 * Default values for pre-populating the Quick Shot form.
 */
interface QuickShotDefaults {
  /** Default worktree path from most recent workflow. */
  worktree_path?: string;
  /** Default profile from most recent workflow. */
  profile?: string;
  /** Recent worktree paths from workflow history. */
  recent_worktree_paths?: string[];
}

/**
 * Props for the QuickShotModal component.
 */
interface QuickShotModalProps {
  /** Whether the modal is open. */
  open: boolean;
  /** Callback when the modal open state changes. */
  onOpenChange: (open: boolean) => void;
  /** Optional defaults to pre-populate the form. */
  defaults?: QuickShotDefaults;
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

/**
 * Fields rendered with standard input styling.
 * Note: worktree_path uses a custom component (WorktreePathField).
 */
const fields: FieldConfig[] = [
  {
    name: 'issue_id',
    label: 'Task ID',
    placeholder: 'TASK-001',
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
export function QuickShotModal({ open, onOpenChange, defaults }: QuickShotModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [importPath, setImportPath] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [serverWorkingDir, setServerWorkingDir] = useState<string>('');

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
    getValues,
    setValue,
    watch,
  } = useForm<QuickShotFormData>({
    resolver: zodResolver(quickShotSchema),
    mode: 'all',
    defaultValues: {
      issue_id: '',
      worktree_path: defaults?.worktree_path ?? '',
      profile: defaults?.profile ?? '',
      task_title: '',
      task_description: '',
    },
  });

  // Watch worktree_path for controlled input
  const worktreePath = watch('worktree_path');

  // Ref for hidden file input (keyboard accessibility)
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize form when modal opens: fetch server config and apply defaults with priority
  // Priority: user-typed value > props defaults > server config
  useEffect(() => {
    if (!open) return;

    let mounted = true;

    async function initializeForm() {
      // Fetch server config first
      let serverDir: string = '';
      try {
        const config = await api.getConfig();
        if (!mounted) return;
        serverDir = config.working_dir;
        setServerWorkingDir(serverDir);
      } catch (error) {
        if (!mounted) return;
        console.debug('Config fetch failed, using defaults', error);
      }

      if (!mounted) return;

      // Apply values with clear priority: current value > props defaults > server config
      reset(
        (currentValues) => ({
          ...currentValues,
          worktree_path:
            currentValues.worktree_path ||
            defaults?.worktree_path ||
            serverDir ||
            '',
          profile: currentValues.profile || defaults?.profile || '',
        }),
        { keepDirty: true }
      );
    }

    initializeForm();

    return () => {
      mounted = false;
    };
  }, [open, defaults, reset]);

  /**
   * Populates form fields from design document content.
   */
  const populateFromContent = useCallback((content: string, filename: string) => {
    let title = extractTitle(content);
    if (title === 'Untitled') {
      title = extractTitleFromFilename(filename);
    }

    reset({
      issue_id: generateDesignId(),
      worktree_path: getValues('worktree_path'),
      profile: getValues('profile'),
      task_title: title,
      task_description: buildDescriptionReference(filename),
    });
  }, [reset, getValues]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  /**
   * Processes a markdown file and populates the form.
   */
  const processFile = useCallback(async (file: File) => {
    if (!file.name.endsWith('.md')) {
      toast.error('Only .md files supported');
      return;
    }

    setIsImporting(true);
    try {
      const content = await file.text();
      populateFromContent(content, file.name);
      setImportPath(file.name);
    } catch {
      toast.error('Failed to read file');
    } finally {
      setIsImporting(false);
    }
  }, [populateFromContent]);

  /**
   * Handles drag-drop of markdown files.
   */
  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    const mdFile = files.find((f) => f.name.endsWith('.md'));

    if (!mdFile) {
      toast.error('Only .md files supported');
      return;
    }

    await processFile(mdFile);
  }, [processFile]);

  /**
   * Handles file input change (keyboard accessible file selection).
   */
  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
    // Reset input so the same file can be selected again
    e.target.value = '';
  }, [processFile]);

  /**
   * Opens file picker when import zone is clicked.
   */
  const handleImportZoneClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  /**
   * Submits the workflow with the specified action type.
   *
   * @param action - The action type: 'start' (immediate), 'queue' (add to queue),
   *                 or 'plan_queue' (plan then queue)
   */
  const submitWithAction = (action: 'start' | 'queue' | 'plan_queue') => {
    return handleSubmit(async (data: QuickShotFormData) => {
      // Start submission immediately - animation is CSS-only via isSubmitting state
      setIsSubmitting(true);

      try {
        const result = await api.createWorkflow({
          issue_id: data.issue_id,
          worktree_path: data.worktree_path,
          profile: data.profile || undefined,
          task_title: data.task_title,
          task_description: data.task_description || undefined,
          start: action === 'start',
          plan_now: action === 'plan_queue',
        });

        const actionLabel =
          action === 'start'
            ? 'started'
            : action === 'plan_queue'
              ? 'queued for planning'
              : 'queued';

        toast.success(
          <span>
            Workflow {actionLabel}:{' '}
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
    });
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
          <DialogDescription className="sr-only">
            Create a new workflow by specifying task details and worktree path
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Import Zone */}
          <Card
            data-testid="import-zone"
            role="button"
            tabIndex={0}
            className={cn(
              'border-2 border-dashed p-3 text-center transition-colors cursor-pointer',
              isDragOver ? 'border-primary bg-primary/5' : 'border-border',
              isImporting && 'opacity-50',
              'hover:border-primary/50 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20'
            )}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={handleImportZoneClick}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleImportZoneClick();
              }
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".md"
              className="sr-only"
              onChange={handleFileInputChange}
              aria-label="Import design document"
            />
            <div className="flex items-center justify-center gap-2">
              <Upload className="h-4 w-4 text-muted-foreground" />
              {importPath ? (
                <span className="text-sm font-mono text-foreground">{importPath}</span>
              ) : (
                <span className="text-sm text-muted-foreground">Drop or click to import design doc</span>
              )}
            </div>
          </Card>

          {/* Worktree Path - Critical Field with Enhanced UX */}
          <div className="animate-quick-shot-field">
            <WorktreePathField
              id="worktree_path"
              value={worktreePath}
              onChange={(value) => setValue('worktree_path', value, { shouldValidate: true })}
              error={errors.worktree_path?.message}
              disabled={isSubmitting}
              serverWorkingDir={serverWorkingDir}
              recentPaths={defaults?.recent_worktree_paths}
            />
          </div>

          {fields.map((field, index) => (
            <div
              key={field.name}
              className="animate-quick-shot-field"
              style={{ animationDelay: `${(index + 1) * 50}ms` }}
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
                    aria-required={field.required}
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
                    aria-required={field.required}
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
              variant="ghost"
              onClick={handleClose}
              className="font-heading uppercase tracking-wide"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!isValid || isSubmitting}
              onClick={submitWithAction('queue')}
              className="font-heading uppercase tracking-wide"
            >
              Queue
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!isValid || isSubmitting}
              onClick={submitWithAction('plan_queue')}
              className="font-heading uppercase tracking-wide"
            >
              Plan & Queue
            </Button>
            <Button
              type="button"
              disabled={!isValid || isSubmitting}
              onClick={submitWithAction('start')}
              className={cn(
                'font-heading uppercase tracking-wide relative overflow-hidden',
                'transition-all duration-normal',
                isValid && !isSubmitting && 'animate-quick-shot-charge'
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
                  Start
                </>
              )}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
