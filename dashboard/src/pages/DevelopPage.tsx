/**
 * @fileoverview Develop page for creating workflows from GitHub issues.
 *
 * Supports GitHub issue selection via searchable combobox when the
 * selected profile uses a GitHub tracker.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Zap, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { api, ApiError } from '@/api/client';
import { getProfiles, type Profile } from '@/api/settings';
import { extractTitle, extractTitleFromFilename, generateDesignId, buildDescriptionReference } from '@/lib/design-doc';
import { PlanImportSection, type PlanData } from '@/components/PlanImportSection';
import { GitHubIssueCombobox } from '@/components/GitHubIssueCombobox';
import { ProfileSelect } from '@/components/ProfileSelect';
import { WorktreePathField } from '@/components/WorktreePathField';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { GitHubIssueSummary } from '@/types';

/**
 * Zod schema for the develop form validation.
 */
const developSchema = z.object({
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

type DevelopFormData = z.infer<typeof developSchema>;

/**
 * Develop page component for creating workflows with optional GitHub issue selection.
 *
 * Features:
 * - Profile selection with automatic GitHub issue combobox when profile uses GitHub tracker
 * - Form validation with react-hook-form and zod
 * - Design document import via drag-drop
 * - External plan import via PlanImportSection
 * - Start, Queue, and Plan & Queue submission actions
 */
export default function DevelopPage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [importPath, setImportPath] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [serverWorkingDir, setServerWorkingDir] = useState('');
  const [planData, setPlanData] = useState<PlanData>({});
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [trackerType, setTrackerType] = useState<string>('');

  const hasExternalPlan = !!(planData.plan_file || planData.plan_content);
  const hasDesignDoc = !!importPath;

  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
    getValues,
    setValue,
    watch,
  } = useForm<DevelopFormData>({
    resolver: zodResolver(developSchema),
    mode: 'all',
    defaultValues: {
      issue_id: '',
      worktree_path: '',
      profile: '',
      task_title: '',
      task_description: '',
    },
  });

  const worktreePath = watch('worktree_path');
  const profileValue = watch('profile');

  // Fetch server config on mount
  useEffect(() => {
    let mounted = true;

    async function init() {
      try {
        const config = await api.getConfig();
        if (!mounted) return;
        setServerWorkingDir(config.repo_root);
        setValue('worktree_path', config.repo_root, { shouldValidate: true });
        if (config.active_profile) {
          setValue('profile', config.active_profile, { shouldValidate: true });
        }
      } catch {
        if (!mounted) return;
        // Config fetch is best-effort
      }
    }

    init();
    return () => { mounted = false; };
  }, [setValue]);

  // Fetch profiles to determine tracker type
  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();

    async function fetchProfiles() {
      try {
        const result = await getProfiles(controller.signal);
        if (mounted) setProfiles(result);
      } catch {
        // Ignore abort errors
      }
    }

    fetchProfiles();
    return () => { mounted = false; controller.abort(); };
  }, []);

  // Update tracker type when profile changes
  useEffect(() => {
    if (profileValue) {
      const profile = profiles.find((p) => p.id === profileValue);
      setTrackerType(profile?.tracker ?? '');
    } else {
      setTrackerType('');
    }
  }, [profileValue, profiles]);

  const handleProfileChange = useCallback(
    (profileId: string) => {
      setValue('profile', profileId, { shouldValidate: true });
    },
    [setValue],
  );

  const handlePlanChange = useCallback(
    (data: PlanData) => {
      setPlanData(data);
      if (data.extracted_title && !getValues('task_title')) {
        setValue('task_title', data.extracted_title, { shouldValidate: true });
      }
    },
    [getValues, setValue],
  );

  const handleIssueSelect = useCallback(
    (issue: GitHubIssueSummary | { number: number; title: string }) => {
      setValue('issue_id', String(issue.number), { shouldValidate: true });
      setValue('task_title', issue.title, { shouldValidate: true });
    },
    [setValue],
  );

  // Design document import handlers
  const populateFromContent = useCallback(
    (content: string, filename: string) => {
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
    },
    [reset, getValues],
  );

  const processFile = useCallback(
    async (file: File) => {
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
    },
    [populateFromContent],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);

      const files = Array.from(e.dataTransfer.files);
      const mdFile = files.find((f) => f.name.endsWith('.md'));

      if (!mdFile) {
        toast.error('Only .md files supported');
        return;
      }

      await processFile(mdFile);
    },
    [processFile],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) processFile(file);
      e.target.value = '';
    },
    [processFile],
  );

  const handleImportZoneClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  /**
   * Submits the workflow with the specified action type.
   */
  const submitWithAction = (action: 'start' | 'queue' | 'plan_queue') => {
    return handleSubmit(async (data: DevelopFormData) => {
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
          plan_file: planData.plan_file,
          plan_content: planData.plan_content,
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
          </span>,
        );
        reset();
        setPlanData({});
        setImportPath('');
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

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center gap-2 px-6 py-4">
        <Zap className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-display tracking-wider text-primary">
          Develop
        </h1>
      </div>
      <Separator />

      {/* Form content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-5">
          {/* Design document import zone */}
          <Card
            data-testid="import-zone"
            role="button"
            tabIndex={0}
            className={cn(
              'border-2 border-dashed p-3 text-center transition-colors cursor-pointer',
              isDragOver ? 'border-primary bg-primary/5' : 'border-border',
              isImporting && 'opacity-50',
              'hover:border-primary/50 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20',
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
                <span className="text-sm text-muted-foreground">
                  Drop or click to import design doc
                </span>
              )}
            </div>
          </Card>

          {/* Worktree path */}
          <WorktreePathField
            id="worktree_path"
            value={worktreePath}
            onChange={(value) => setValue('worktree_path', value, { shouldValidate: true })}
            error={errors.worktree_path?.message}
            disabled={isSubmitting}
            serverWorkingDir={serverWorkingDir}
          />

          {/* Profile selection */}
          <ProfileSelect
            id="profile"
            value={profileValue}
            onChange={handleProfileChange}
            error={errors.profile?.message}
            disabled={isSubmitting}
          />

          {/* GitHub issue combobox — shown when profile uses GitHub tracker */}
          {trackerType === 'github' && profileValue && (
            <div>
              <Label htmlFor="github-issue" className="text-[11px] font-heading uppercase tracking-wider text-muted-foreground mb-1 block">
                GitHub Issue
              </Label>
              <GitHubIssueCombobox
                id="github-issue"
                profile={profileValue}
                onSelect={handleIssueSelect}
              />
            </div>
          )}

          {/* Task ID */}
          <div className="relative">
            <Label
              htmlFor="issue_id"
              className="absolute -top-2 left-3 bg-card px-1 text-[11px] font-heading uppercase tracking-wider text-muted-foreground z-10"
            >
              Task ID<span className="ml-1 text-primary">*</span>
            </Label>
            <Input
              id="issue_id"
              placeholder="TASK-001"
              aria-invalid={!!errors.issue_id}
              aria-required
              aria-describedby={errors.issue_id ? 'issue_id-error' : undefined}
              className={cn(
                'mt-1 font-mono text-sm bg-background border-input',
                'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
                errors.issue_id && 'border-destructive',
              )}
              {...register('issue_id')}
            />
            {errors.issue_id && (
              <p id="issue_id-error" className="mt-1 text-xs text-destructive">
                {errors.issue_id.message}
              </p>
            )}
          </div>

          {/* Task Title */}
          <div className="relative">
            <Label
              htmlFor="task_title"
              className="absolute -top-2 left-3 bg-card px-1 text-[11px] font-heading uppercase tracking-wider text-muted-foreground z-10"
            >
              Task Title<span className="ml-1 text-primary">*</span>
            </Label>
            <Input
              id="task_title"
              placeholder="Add logout button to navbar"
              aria-invalid={!!errors.task_title}
              aria-required
              aria-describedby={errors.task_title ? 'task_title-error' : undefined}
              className={cn(
                'mt-1 font-mono text-sm bg-background border-input',
                'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
                errors.task_title && 'border-destructive',
              )}
              {...register('task_title')}
            />
            {errors.task_title && (
              <p id="task_title-error" className="mt-1 text-xs text-destructive">
                {errors.task_title.message}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="relative">
            <Label
              htmlFor="task_description"
              className="absolute -top-2 left-3 bg-card px-1 text-[11px] font-heading uppercase tracking-wider text-muted-foreground z-10"
            >
              Description
            </Label>
            <Textarea
              id="task_description"
              placeholder="Add a logout button to the top navigation bar..."
              aria-invalid={!!errors.task_description}
              aria-describedby={errors.task_description ? 'task_description-error' : undefined}
              className={cn(
                'mt-1 font-mono text-sm bg-background border-input',
                'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
                errors.task_description && 'border-destructive',
              )}
              rows={3}
              {...register('task_description')}
            />
            {errors.task_description && (
              <p id="task_description-error" className="mt-1 text-xs text-destructive">
                {errors.task_description.message}
              </p>
            )}
          </div>

          {/* External Plan Import */}
          <PlanImportSection
            onPlanChange={handlePlanChange}
            worktreePath={worktreePath}
            planOutputDir="docs/plans"
          />

          {/* Action buttons */}
          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="secondary"
              disabled={!isValid || isSubmitting}
              onClick={submitWithAction('queue')}
              className="font-heading uppercase tracking-wide"
            >
              Queue
            </Button>
            {hasDesignDoc && !hasExternalPlan && (
              <Button
                type="button"
                variant="secondary"
                disabled={!isValid || isSubmitting}
                onClick={submitWithAction('plan_queue')}
                className="font-heading uppercase tracking-wide"
              >
                Plan & Queue
              </Button>
            )}
            <Button
              type="button"
              disabled={!isValid || isSubmitting}
              onClick={submitWithAction('start')}
              className={cn(
                'font-heading uppercase tracking-wide relative overflow-hidden',
                'transition-all duration-normal',
              )}
            >
              {isSubmitting ? (
                'Launching...'
              ) : (
                <>
                  <Zap className="mr-2 h-4 w-4" />
                  Start
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
