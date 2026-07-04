import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentsSection } from '../AgentsSection';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';
import type { AgentFormData } from '../types';

vi.mock('@/store/useModelsStore');

vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: ['claude-sonnet-4'],
    addRecentModel: vi.fn(),
  }),
}));

const defaultAgents: Record<string, AgentFormData> = {
  architect: { driver: 'claude', model: 'opus', options: {} },
  developer: { driver: 'claude', model: 'opus', options: {} },
  reviewer: { driver: 'claude', model: 'sonnet', options: {} },
  plan_validator: { driver: 'claude', model: 'haiku', options: {} },
  task_reviewer: { driver: 'claude', model: 'haiku', options: {} },
  evaluator: { driver: 'claude', model: 'haiku', options: {} },
  brainstormer: { driver: 'claude', model: 'haiku', options: {} },
};

describe('AgentsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(makeMockModelsStore());
  });

  it('renders a row per primary agent with driver and model controls', () => {
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={vi.fn()}
        onAgentOption={vi.fn()}
        onBulkApply={vi.fn()}
      />
    );
    expect(screen.getByText(/architect/i)).toBeInTheDocument();
    expect(screen.getByText(/developer/i)).toBeInTheDocument();
    expect(screen.getByText(/reviewer/i)).toBeInTheDocument();
    // each primary agent has a combobox for driver + model (3 agents × 2 = 6)
    expect(screen.getAllByRole('combobox').length).toBeGreaterThanOrEqual(6);
  });

  it('calls onAgentChange when a driver changes', async () => {
    const user = userEvent.setup();
    const onAgentChange = vi.fn();
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={onAgentChange}
        onAgentOption={vi.fn()}
        onBulkApply={vi.fn()}
      />
    );
    const driverSelect = screen.getAllByRole('combobox')[0]!; // Safe: AgentsSection always renders driver selects
    await user.click(driverSelect);
    await user.click(screen.getByRole('option', { name: /codex/i }));
    expect(onAgentChange).toHaveBeenCalledWith('architect', 'driver', 'codex');
  });

  it('reveals utility agent rows when the collapsible is opened', async () => {
    const user = userEvent.setup();
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={vi.fn()}
        onAgentOption={vi.fn()}
        onBulkApply={vi.fn()}
      />
    );
    // Utility agents are collapsed by default with an "N configured" badge.
    expect(screen.getByText(/4 configured/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /utility agents/i }));
    expect(screen.getByText(/brainstormer/i)).toBeInTheDocument();
  });

  it('renders an options expand button per agent row', () => {
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={vi.fn()}
        onAgentOption={vi.fn()}
        onBulkApply={vi.fn()}
      />
    );
    // One options button per primary agent (architect, developer, reviewer).
    expect(screen.getAllByRole('button', { name: /options for/i }).length).toBe(3);
  });

  it('expanding options shows MoA controls', async () => {
    const user = userEvent.setup();
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={vi.fn()}
        onAgentOption={vi.fn()}
        onBulkApply={vi.fn()}
      />
    );
    await user.click(screen.getAllByRole('button', { name: /options for/i })[0]!);
    expect(screen.getByLabelText('MoA Enabled')).toBeInTheDocument();
    expect(screen.getByLabelText('Proposer Count')).toBeInTheDocument();
    expect(screen.getByLabelText('Proposer Models')).toBeInTheDocument();
    expect(screen.getByLabelText('Isolation')).toBeInTheDocument();
  });

  it('changing MoA enabled calls onAgentOption', async () => {
    const user = userEvent.setup();
    const onAgentOption = vi.fn();
    render(
      <AgentsSection
        agents={defaultAgents}
        errors={{}}
        onAgentChange={vi.fn()}
        onAgentOption={onAgentOption}
        onBulkApply={vi.fn()}
      />
    );
    await user.click(screen.getAllByRole('button', { name: /options for/i })[0]!);
    await user.click(screen.getByLabelText('MoA Enabled'));
    expect(onAgentOption).toHaveBeenCalledWith(
      'architect',
      'moa',
      expect.objectContaining({ enabled: true })
    );
  });
});
