/**
 * @fileoverview Client-side plan preview extraction for external plan import.
 */

/**
 * Extracted preview information from a plan markdown document.
 */
export interface PlanPreview {
  /** Title extracted from the first H1 heading, with common suffixes stripped. */
  title?: string;
  /** The goal/objective extracted from the plan. */
  goal: string;
  /** Number of tasks found in the plan. */
  taskCount: number;
  /** List of key files mentioned in the plan (max 5). */
  keyFiles: string[];
}

/**
 * Extracts a title from the first H1 heading, stripping common document-type suffixes.
 */
function parseTitle(markdown: string): string | undefined {
  const match = markdown.match(/^#\s+(.+?)(?:\s+(?:Design|Plan|Spec|RFC|Proposal))?\s*$/mi);
  if (!match || !match[1]) {
    return undefined;
  }
  return match[1].trim();
}

/**
 * File extension pattern for identifying file paths.
 * Matches common source file extensions.
 */
const FILE_PATH_PATTERN = /^[\w./\\-]+\.(ts|tsx|js|jsx|py|go|rs|java|kt|swift|md|json|yaml|yml|toml|css|scss|html)$/i;

/**
 * Extracts the content under a ## heading, stopping at the next ## heading.
 */
function extractSection(markdown: string, headingName: string): string {
  const regex = new RegExp(`^##\\s+${headingName}\\s*$`, 'mi');
  const match = markdown.match(regex);
  if (!match || match.index === undefined) {
    return '';
  }

  const startIndex = match.index + match[0].length;
  const remainingContent = markdown.slice(startIndex);

  // Find next ## heading or end of string
  const nextHeadingMatch = remainingContent.match(/^##\s+\w/m);
  const endIndex = nextHeadingMatch?.index ?? remainingContent.length;

  return remainingContent.slice(0, endIndex).trim();
}

/**
 * Parses the goal from the ## Goal section.
 * Collapses multiline content into a single line.
 */
function parseGoal(markdown: string): string {
  const section = extractSection(markdown, 'Goal');
  if (!section) {
    return '';
  }

  // Collapse multiple lines into one, preserving sentence structure
  return section
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .join(' ')
    .trim();
}

/**
 * Counts tasks in the plan using several heuristics.
 * Priority: ### Task headings > checklist items > numbered lists
 */
function countTasks(markdown: string): number {
  // First, try ### Task headings (most explicit)
  const taskHeadings = markdown.match(/^###\s+Task\s+\d+/gim);
  if (taskHeadings && taskHeadings.length > 0) {
    return taskHeadings.length;
  }

  // Fall back to checklist items (- [ ] or - [x])
  const checklistItems = markdown.match(/^-\s+\[[ x]\]/gim);
  if (checklistItems && checklistItems.length > 0) {
    return checklistItems.length;
  }

  // Fall back to numbered list items in Tasks section
  const tasksSection = extractSection(markdown, 'Tasks');
  if (tasksSection) {
    const numberedItems = tasksSection.match(/^\d+\.\s+/gm);
    if (numberedItems && numberedItems.length > 0) {
      return numberedItems.length;
    }
  }

  return 0;
}

/**
 * Extracts key files from the ## Key Files section.
 * Supports:
 * - List items with file paths
 * - Code blocks with file paths
 * - Inline code with file paths
 */
function parseKeyFiles(markdown: string): string[] {
  const section = extractSection(markdown, 'Key Files');
  if (!section) {
    return [];
  }

  const files: string[] = [];

  // Extract from code blocks first
  const codeBlockMatch = section.match(/```[\s\S]*?```/);
  if (codeBlockMatch) {
    const codeContent = codeBlockMatch[0].replace(/```/g, '').trim();
    const lines = codeContent.split('\n').map((l) => l.trim()).filter(Boolean);
    for (const line of lines) {
      if (FILE_PATH_PATTERN.test(line)) {
        files.push(line);
      }
    }
  }

  // Extract from list items (- path or - `path`)
  const listItemPattern = /^-\s+`?([^`\n]+)`?\s*$/gm;
  let match;
  while ((match = listItemPattern.exec(section)) !== null) {
    const path = match[1]?.trim();
    if (path && FILE_PATH_PATTERN.test(path)) {
      files.push(path);
    }
  }

  // Deduplicate and limit to 5
  const uniqueFiles = [...new Set(files)];
  return uniqueFiles.slice(0, 5);
}

/**
 * Parses a plan markdown document and extracts preview information.
 *
 * @param markdown - The raw markdown content of the plan
 * @returns Extracted preview with goal, task count, and key files
 *
 * @example
 * ```typescript
 * const preview = parsePlanPreview(`
 * # Plan
 *
 * ## Goal
 * Implement user authentication.
 *
 * ## Key Files
 * - src/auth/login.ts
 *
 * ## Tasks
 * ### Task 1: Create login form
 * ### Task 2: Add validation
 * `);
 *
 * console.log(preview);
 * // { goal: 'Implement user authentication.', taskCount: 2, keyFiles: ['src/auth/login.ts'] }
 * ```
 */
export function parsePlanPreview(markdown: string): PlanPreview {
  if (!markdown || !markdown.trim()) {
    return {
      title: undefined,
      goal: '',
      taskCount: 0,
      keyFiles: [],
    };
  }

  return {
    title: parseTitle(markdown),
    goal: parseGoal(markdown),
    taskCount: countTasks(markdown),
    keyFiles: parseKeyFiles(markdown),
  };
}
