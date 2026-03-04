import { describe, it, expect } from 'vitest';
import { parsePlanPreview, type PlanPreview } from '../plan-parser';

describe('parsePlanPreview', () => {
  describe('goal extraction', () => {
    it('extracts goal from ## Goal heading', () => {
      const markdown = `# Implementation Plan

## Goal

Implement user authentication with JWT tokens.

## Tasks

### Task 1: Set up auth module
`;
      const result = parsePlanPreview(markdown);
      expect(result.goal).toBe('Implement user authentication with JWT tokens.');
    });

    it('extracts multiline goal content', () => {
      const markdown = `# Plan

## Goal

This is a multi-line goal
that spans multiple lines.

## Tasks
`;
      const result = parsePlanPreview(markdown);
      expect(result.goal).toBe('This is a multi-line goal that spans multiple lines.');
    });

    it('returns empty string when no Goal heading found', () => {
      const markdown = `# Plan

## Tasks

### Task 1: Do something
`;
      const result = parsePlanPreview(markdown);
      expect(result.goal).toBe('');
    });

    it('handles Goal heading with extra whitespace', () => {
      const markdown = `## Goal

  Trimmed goal content

## Tasks
`;
      const result = parsePlanPreview(markdown);
      expect(result.goal).toBe('Trimmed goal content');
    });
  });

  describe('task count', () => {
    it('counts tasks from ### Task headings', () => {
      const markdown = `## Tasks

### Task 1: First task
Description

### Task 2: Second task
Description

### Task 3: Third task
`;
      const result = parsePlanPreview(markdown);
      expect(result.taskCount).toBe(3);
    });

    it('counts checklist items as tasks', () => {
      const markdown = `## Tasks

- [ ] First task
- [ ] Second task
- [x] Completed task
`;
      const result = parsePlanPreview(markdown);
      expect(result.taskCount).toBe(3);
    });

    it('counts numbered list items as tasks', () => {
      const markdown = `## Tasks

1. First task
2. Second task
3. Third task
`;
      const result = parsePlanPreview(markdown);
      expect(result.taskCount).toBe(3);
    });

    it('prefers ### Task headings over list items when both exist', () => {
      const markdown = `## Tasks

### Task 1: Main task
- [ ] Sub-item (not counted)
- [ ] Another sub-item

### Task 2: Second task
`;
      const result = parsePlanPreview(markdown);
      expect(result.taskCount).toBe(2);
    });

    it('returns 0 when no tasks found', () => {
      const markdown = `# Plan

Just some text without tasks.
`;
      const result = parsePlanPreview(markdown);
      expect(result.taskCount).toBe(0);
    });
  });

  describe('key files extraction', () => {
    it('extracts files from ## Key Files section', () => {
      const markdown = `## Key Files

- src/auth/login.ts
- src/auth/middleware.ts
- tests/auth.test.ts

## Tasks
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toEqual([
        'src/auth/login.ts',
        'src/auth/middleware.ts',
        'tests/auth.test.ts',
      ]);
    });

    it('extracts files from code blocks', () => {
      const markdown = `## Key Files

\`\`\`
src/components/App.tsx
src/utils/helpers.ts
\`\`\`
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toEqual([
        'src/components/App.tsx',
        'src/utils/helpers.ts',
      ]);
    });

    it('extracts inline code file references', () => {
      const markdown = `## Key Files

- \`src/api/client.ts\`
- \`src/types/index.ts\`
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toEqual([
        'src/api/client.ts',
        'src/types/index.ts',
      ]);
    });

    it('returns empty array when no Key Files section', () => {
      const markdown = `# Plan

## Goal
Do something

## Tasks
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toEqual([]);
    });

    it('filters out non-file entries', () => {
      const markdown = `## Key Files

- src/valid/file.ts
- Not a file path
- another/valid.tsx
- Just some text
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toEqual([
        'src/valid/file.ts',
        'another/valid.tsx',
      ]);
    });

    it('limits key files to first 5', () => {
      const markdown = `## Key Files

- file1.ts
- file2.ts
- file3.ts
- file4.ts
- file5.ts
- file6.ts
- file7.ts
`;
      const result = parsePlanPreview(markdown);
      expect(result.keyFiles).toHaveLength(5);
    });
  });

  describe('title extraction', () => {
    it('extracts title from H1', () => {
      const result = parsePlanPreview('# My Feature\n\n## Goal\nBuild X');
      expect(result.title).toBe('My Feature');
    });

    it('strips Design suffix', () => {
      const result = parsePlanPreview('# Queue Workflows Design\n\n## Goal\n...');
      expect(result.title).toBe('Queue Workflows');
    });

    it('strips Plan suffix', () => {
      const result = parsePlanPreview('# Queue Workflows Plan\n...');
      expect(result.title).toBe('Queue Workflows');
    });

    it('strips Spec suffix', () => {
      const result = parsePlanPreview('# Auth System Spec\n...');
      expect(result.title).toBe('Auth System');
    });

    it('strips RFC suffix', () => {
      const result = parsePlanPreview('# Feature RFC\n...');
      expect(result.title).toBe('Feature');
    });

    it('strips Proposal suffix', () => {
      const result = parsePlanPreview('# New API Proposal\n...');
      expect(result.title).toBe('New API');
    });

    it('strips suffix case-insensitively', () => {
      const result = parsePlanPreview('# My Feature DESIGN\n...');
      expect(result.title).toBe('My Feature');
    });

    it('returns undefined when no H1 found', () => {
      const result = parsePlanPreview('## Only H2\nSome content');
      expect(result.title).toBeUndefined();
    });

    it('returns undefined for empty content', () => {
      const result = parsePlanPreview('');
      expect(result.title).toBeUndefined();
    });
  });

  describe('edge cases', () => {
    it('handles empty input', () => {
      const result = parsePlanPreview('');
      expect(result).toEqual<PlanPreview>({
        title: undefined,
        goal: '',
        taskCount: 0,
        keyFiles: [],
      });
    });

    it('handles whitespace-only input', () => {
      const result = parsePlanPreview('   \n\n  \t  ');
      expect(result).toEqual<PlanPreview>({
        title: undefined,
        goal: '',
        taskCount: 0,
        keyFiles: [],
      });
    });

    it('handles real-world plan format', () => {
      const markdown = `# External Plan: Add User Settings

## Goal

Add a user settings page that allows users to configure their profile and notification preferences.

## Key Files

- \`src/pages/Settings.tsx\`
- \`src/components/SettingsForm.tsx\`
- \`src/api/settings.ts\`
- \`src/types/settings.ts\`

## Tasks

### Task 1: Create settings API types
Define TypeScript interfaces for settings data.

### Task 2: Implement settings API client
Add API methods for fetching and updating settings.

### Task 3: Create SettingsForm component
Build the form with validation.

### Task 4: Add Settings page route
Wire up the route and layout.

### Task 5: Add tests
Unit and integration tests.
`;
      const result = parsePlanPreview(markdown);
      expect(result.goal).toBe(
        'Add a user settings page that allows users to configure their profile and notification preferences.'
      );
      expect(result.taskCount).toBe(5);
      expect(result.keyFiles).toEqual([
        'src/pages/Settings.tsx',
        'src/components/SettingsForm.tsx',
        'src/api/settings.ts',
        'src/types/settings.ts',
      ]);
    });
  });
});
