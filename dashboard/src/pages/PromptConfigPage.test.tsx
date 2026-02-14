/**
 * @fileoverview Tests for PromptConfigPage.
 *
 * Tests the prompt configuration page, including the fallback placeholder card
 * shown when an agent has no configurable prompts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import PromptConfigPage from './PromptConfigPage';
import type { PromptSummary } from '@/types';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    resetPromptToDefault: vi.fn(),
  },
}));

// Mock prompts for architect, reviewer, evaluator (but NOT developer)
const mockPromptsWithoutDeveloper: PromptSummary[] = [
  {
    id: 'architect.system',
    agent: 'architect',
    name: 'System Prompt',
    description: 'Instructions for issue analysis',
    current_version_id: null,
    current_version_number: null,
  },
  {
    id: 'architect.plan',
    agent: 'architect',
    name: 'Plan Format',
    description: 'Format for markdown plans',
    current_version_id: 'v1',
    current_version_number: 2,
  },
  {
    id: 'reviewer.structured',
    agent: 'reviewer',
    name: 'Structured Review',
    description: 'Code review format',
    current_version_id: null,
    current_version_number: null,
  },
  {
    id: 'evaluator.system',
    agent: 'evaluator',
    name: 'Evaluator System',
    description: 'Feedback evaluation',
    current_version_id: null,
    current_version_number: null,
  },
];

// Mock prompts including developer (for comparison)
const mockPromptsWithDeveloper: PromptSummary[] = [
  ...mockPromptsWithoutDeveloper,
  {
    id: 'developer.system',
    agent: 'developer',
    name: 'Developer System',
    description: 'Developer instructions',
    current_version_id: null,
    current_version_number: null,
  },
];

/**
 * Helper to render PromptConfigPage with router context and loader data
 */
function renderWithRouter(prompts: PromptSummary[]) {
  const router = createMemoryRouter(
    [
      {
        path: '/settings/prompts',
        element: <PromptConfigPage />,
        loader: () => ({ prompts }),
        HydrateFallback: () => null,
      },
    ],
    { initialEntries: ['/settings/prompts'] }
  );

  return render(<RouterProvider router={router} />);
}

describe('PromptConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('agent sections', () => {
    it('should display all four agent sections', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      // All four agent sections should be visible
      expect(await screen.findByText('Architect')).toBeInTheDocument();
      expect(screen.getByText('Developer')).toBeInTheDocument();
      expect(screen.getByText('Reviewer')).toBeInTheDocument();
      expect(screen.getByText('Evaluator')).toBeInTheDocument();
    });

    it('should display Developer section last (not editable)', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      await screen.findByText('Architect');

      // Get all section elements and extract their heading text
      const sections = document.querySelectorAll('section');
      const sectionHeadings = Array.from(sections).map(
        (s) => s.querySelector('h2')?.textContent
      );

      // Developer should be last since it's not editable
      expect(sectionHeadings).toEqual([
        'Architect',
        'Reviewer',
        'Evaluator',
        'Developer',
      ]);
    });

    it('should apply agent-specific colors to section headers', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      await screen.findByText('Architect');

      // Each section header should have the agent color class
      expect(screen.getByText('Architect')).toHaveClass('text-agent-architect');
      expect(screen.getByText('Developer')).toHaveClass('text-agent-developer');
      expect(screen.getByText('Reviewer')).toHaveClass('text-agent-reviewer');
      expect(screen.getByText('Evaluator')).toHaveClass('text-agent-pm');
    });

    it('should display prompt cards for agents with prompts', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      // Wait for page to load
      await screen.findByText('Architect');

      // Architect should have 2 prompt cards
      expect(screen.getByText('System Prompt')).toBeInTheDocument();
      expect(screen.getByText('Plan Format')).toBeInTheDocument();

      // Reviewer should have 1 prompt card
      expect(screen.getByText('Structured Review')).toBeInTheDocument();

      // Evaluator should have 1 prompt card
      expect(screen.getByText('Evaluator System')).toBeInTheDocument();
    });
  });

  describe('developer placeholder card', () => {
    it('should show placeholder card when developer has no prompts', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      // Wait for page to load
      await screen.findByText('Architect');

      // Developer section should exist
      const developerSection = screen.getByText('Developer').closest('section');
      expect(developerSection).toBeInTheDocument();

      // Should show the placeholder card with explanatory text
      expect(
        within(developerSection!).getByText('No Configurable Prompt')
      ).toBeInTheDocument();
    });

    it('should explain that no prompt template is available', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      await screen.findByText('Architect');

      // Find the developer section
      const developerSection = screen.getByText('Developer').closest('section');
      expect(developerSection).toBeInTheDocument();

      // Should contain generic placeholder explanation
      expect(
        within(developerSection!).getByText(/no prompt template available/i)
      ).toBeInTheDocument();
    });

    it('should not show placeholder card when developer has prompts', async () => {
      renderWithRouter(mockPromptsWithDeveloper);

      await screen.findByText('Architect');

      // Developer section should show the actual prompt, not placeholder
      const developerSection = screen.getByText('Developer').closest('section');
      expect(developerSection).toBeInTheDocument();

      // Should show the actual prompt card
      expect(
        within(developerSection!).getByText('Developer System')
      ).toBeInTheDocument();

      // Should NOT show the placeholder
      expect(
        within(developerSection!).queryByText('No Configurable Prompt')
      ).not.toBeInTheDocument();
    });
  });

  describe('header stats', () => {
    it('should display correct total count', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      await screen.findByText('Architect');

      // Should show total count of 4 prompts
      expect(screen.getByText('4')).toBeInTheDocument();
    });

    it('should display customized count when prompts are customized', async () => {
      renderWithRouter(mockPromptsWithoutDeveloper);

      await screen.findByText('Architect');

      // One prompt has a custom version (architect.plan)
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('customized')).toBeInTheDocument();
    });

    it('should display "All defaults" when no prompts are customized', async () => {
      const allDefaultPrompts = mockPromptsWithoutDeveloper.map((p) => ({
        ...p,
        current_version_id: null,
        current_version_number: null,
      }));

      renderWithRouter(allDefaultPrompts);

      await screen.findByText('Architect');

      expect(screen.getByText('All defaults')).toBeInTheDocument();
    });
  });
});
