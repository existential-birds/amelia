/**
 * @fileoverview Settings page for managing agent prompts.
 *
 * Displays all prompts grouped by agent, with edit and reset capabilities.
 */
import { useState, useCallback, useMemo } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { PromptCard, PromptEditModal } from '@/components/prompts';
import { Separator } from '@/components/ui/separator';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
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
import { api } from '@/api/client';
import { success, error as showError } from '@/components/Toast';
import { groupPromptsByAgent } from '@/loaders/prompts';
import type { promptsLoader } from '@/loaders/prompts';

/** Agent display names for section headers. */
const AGENT_LABELS: Record<string, string> = {
  architect: 'Architect',
  developer: 'Developer',
  reviewer: 'Reviewer',
  evaluator: 'Evaluator',
};

/** Agent display order (developer last since not editable). */
const AGENT_ORDER = ['architect', 'reviewer', 'evaluator', 'developer'];

/** Agents that should always show, even if they have no configurable prompts. */
const ALWAYS_SHOW_AGENTS = ['developer'];

/** Agent header text color classes. */
const AGENT_HEADER_COLORS: Record<string, string> = {
  architect: 'text-agent-architect',
  developer: 'text-agent-developer',
  reviewer: 'text-agent-reviewer',
  evaluator: 'text-agent-pm',
};

/**
 * Settings page for managing agent prompts.
 *
 * Features:
 * - Displays prompts grouped by agent
 * - Edit prompts via modal
 * - Reset prompts to default
 * - Version badge showing current version or "Default"
 *
 * @returns The settings page component.
 */
export default function SettingsPage() {
  const { prompts } = useLoaderData<typeof promptsLoader>();
  const revalidator = useRevalidator();

  // Edit modal state
  const [editPromptId, setEditPromptId] = useState<string | null>(null);
  const [editPromptName, setEditPromptName] = useState('');
  const [editPromptAgent, setEditPromptAgent] = useState('');

  // Reset confirmation state
  const [resetPromptId, setResetPromptId] = useState<string | null>(null);
  const [resetPromptName, setResetPromptName] = useState('');
  const [isResetting, setIsResetting] = useState(false);

  // Group prompts by agent
  const groupedPrompts = useMemo(() => groupPromptsByAgent(prompts), [prompts]);

  // Get ordered agents that exist in our data (plus always-show agents)
  const orderedAgents = useMemo(() => {
    const existingAgents = Object.keys(groupedPrompts);
    // Combine existing agents with always-show agents
    const allAgents = [...new Set([...existingAgents, ...ALWAYS_SHOW_AGENTS])];
    // First include agents in defined order, then any remaining agents
    const ordered = AGENT_ORDER.filter((agent) => allAgents.includes(agent));
    const remaining = allAgents.filter((agent) => !AGENT_ORDER.includes(agent));
    return [...ordered, ...remaining];
  }, [groupedPrompts]);

  // Handle edit button click
  const handleEdit = useCallback((promptId: string) => {
    const prompt = prompts.find((p) => p.id === promptId);
    if (prompt) {
      setEditPromptId(promptId);
      setEditPromptName(prompt.name);
      // Extract agent from promptId (e.g., "architect.system" → "architect")
      setEditPromptAgent(promptId.split('.')[0] ?? 'architect');
    }
  }, [prompts]);

  // Handle reset button click
  const handleResetClick = useCallback((promptId: string) => {
    const prompt = prompts.find((p) => p.id === promptId);
    if (prompt) {
      setResetPromptId(promptId);
      setResetPromptName(prompt.name);
    }
  }, [prompts]);

  // Confirm reset
  const handleResetConfirm = useCallback(async () => {
    if (!resetPromptId) return;

    setIsResetting(true);
    try {
      await api.resetPromptToDefault(resetPromptId);
      success('Prompt reset to default');
      revalidator.revalidate();
    } catch (err) {
      showError('Failed to reset prompt');
      console.error('Failed to reset prompt:', err);
    } finally {
      setIsResetting(false);
      setResetPromptId(null);
      setResetPromptName('');
    }
  }, [resetPromptId, revalidator]);

  // Handle save from edit modal
  const handleSave = useCallback(() => {
    revalidator.revalidate();
  }, [revalidator]);

  // Count custom prompts
  const customCount = prompts.filter((p) => p.current_version_id !== null).length;

  return (
    <div className="flex flex-col h-full w-full overflow-y-auto">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>SETTINGS</PageHeader.Label>
          <PageHeader.Title>Agent Prompts</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Label>TOTAL</PageHeader.Label>
          <PageHeader.Value>{prompts.length}</PageHeader.Value>
        </PageHeader.Center>
        <PageHeader.Right>
          <div className="text-sm text-muted-foreground">
            {customCount > 0 ? (
              <span>
                <span className="font-medium text-primary">{customCount}</span>{' '}
                customized
              </span>
            ) : (
              <span>All defaults</span>
            )}
          </div>
        </PageHeader.Right>
      </PageHeader>
      <Separator />

      <div className="flex-1 p-6 space-y-8">
        {orderedAgents.map((agent) => (
          <section key={agent}>
            <h2
              className={`text-lg font-heading font-semibold tracking-wide mb-4 ${AGENT_HEADER_COLORS[agent] ?? 'text-foreground'}`}
            >
              {AGENT_LABELS[agent] || agent}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {groupedPrompts[agent]?.length ? (
                groupedPrompts[agent].map((prompt) => (
                  <PromptCard
                    key={prompt.id}
                    prompt={prompt}
                    onEdit={handleEdit}
                    onReset={handleResetClick}
                  />
                ))
              ) : (
                <Card className="border-dashed bg-muted/30">
                  <CardHeader>
                    <CardTitle className="text-base text-muted-foreground">
                      Dynamic Prompts
                    </CardTitle>
                    <CardDescription>
                      Developer prompts are built dynamically from your
                      implementation plan and review feedback. Unlike other
                      agents, they adapt to each execution context rather than
                      using fixed templates.
                    </CardDescription>
                  </CardHeader>
                </Card>
              )}
            </div>
          </section>
        ))}
      </div>

      {/* Edit Modal */}
      <PromptEditModal
        promptId={editPromptId}
        promptName={editPromptName}
        agent={editPromptAgent}
        open={editPromptId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditPromptId(null);
            setEditPromptName('');
            setEditPromptAgent('');
          }
        }}
        onSave={handleSave}
      />

      {/* Reset Confirmation Dialog */}
      <AlertDialog
        open={resetPromptId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setResetPromptId(null);
            setResetPromptName('');
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset to Default</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset &ldquo;{resetPromptName}&rdquo; to
              its default? This will remove all custom versions and use the
              built-in prompt.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isResetting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleResetConfirm}
              disabled={isResetting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isResetting ? 'Resetting...' : 'Reset'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
