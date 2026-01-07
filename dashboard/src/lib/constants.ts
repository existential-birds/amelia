/**
 * @fileoverview Application-wide constants and configuration values.
 *
 * Centralizes version info and other constants derived from package.json.
 */

import packageJson from '../../package.json';

/** Current application version from package.json. */
export const APP_VERSION = packageJson.version;

/** Style mapping for different agent types in activity logs and UI. */
export const AGENT_STYLES: Record<string, { text: string; bg: string }> = {
  PM: { text: 'text-agent-pm', bg: 'bg-agent-pm-bg' },
  ORCHESTRATOR: { text: 'text-muted-foreground', bg: '' },
  ARCHITECT: { text: 'text-agent-architect', bg: 'bg-agent-architect-bg' },
  DEVELOPER: { text: 'text-agent-developer', bg: 'bg-agent-developer-bg' },
  REVIEWER: { text: 'text-agent-reviewer', bg: 'bg-agent-reviewer-bg' },
  VALIDATOR: { text: 'text-agent-pm', bg: 'bg-agent-pm-bg' },
  EVALUATOR: { text: 'text-agent-pm', bg: 'bg-agent-pm-bg' },
  HUMAN_APPROVAL: { text: 'text-destructive', bg: 'bg-destructive/10' },
  SYSTEM: { text: 'text-muted-foreground', bg: '' },
};

/** Agent accent style definition. */
export interface AgentAccentStyle {
  border: string;
  shadow: string;
  headerGradient: string;
  iconBg: string;
  iconText: string;
  focusRing: string;
  button: string;
  buttonShadow: string;
}

/** Extended style mapping for agent modal accents (borders, shadows, buttons). */
const AGENT_ACCENT_STYLES_MAP: Record<string, AgentAccentStyle> = {
  architect: {
    border: 'border-agent-architect/20',
    shadow: 'shadow-agent-architect/10 dark:shadow-agent-architect/5',
    headerGradient: 'from-agent-architect/5 via-transparent to-agent-architect/5',
    iconBg: 'bg-agent-architect/10',
    iconText: 'text-agent-architect',
    focusRing: 'focus-visible:border-agent-architect/50 focus-visible:ring-agent-architect/20',
    button: 'bg-agent-architect hover:bg-agent-architect/90',
    buttonShadow: 'shadow-agent-architect/25',
  },
  developer: {
    border: 'border-agent-developer/20',
    shadow: 'shadow-agent-developer/10 dark:shadow-agent-developer/5',
    headerGradient: 'from-agent-developer/5 via-transparent to-agent-developer/5',
    iconBg: 'bg-agent-developer/10',
    iconText: 'text-agent-developer',
    focusRing: 'focus-visible:border-agent-developer/50 focus-visible:ring-agent-developer/20',
    button: 'bg-agent-developer hover:bg-agent-developer/90 text-background',
    buttonShadow: 'shadow-agent-developer/25',
  },
  reviewer: {
    border: 'border-agent-reviewer/20',
    shadow: 'shadow-agent-reviewer/10 dark:shadow-agent-reviewer/5',
    headerGradient: 'from-agent-reviewer/5 via-transparent to-agent-reviewer/5',
    iconBg: 'bg-agent-reviewer/10',
    iconText: 'text-agent-reviewer',
    focusRing: 'focus-visible:border-agent-reviewer/50 focus-visible:ring-agent-reviewer/20',
    button: 'bg-agent-reviewer hover:bg-agent-reviewer/90 text-white',
    buttonShadow: 'shadow-agent-reviewer/25',
  },
  evaluator: {
    border: 'border-agent-pm/20',
    shadow: 'shadow-agent-pm/10 dark:shadow-agent-pm/5',
    headerGradient: 'from-agent-pm/5 via-transparent to-agent-pm/5',
    iconBg: 'bg-agent-pm/10',
    iconText: 'text-agent-pm',
    focusRing: 'focus-visible:border-agent-pm/50 focus-visible:ring-agent-pm/20',
    button: 'bg-agent-pm hover:bg-agent-pm/90 text-white',
    buttonShadow: 'shadow-agent-pm/25',
  },
  plan_validator: {
    border: 'border-agent-pm/20',
    shadow: 'shadow-agent-pm/10 dark:shadow-agent-pm/5',
    headerGradient: 'from-agent-pm/5 via-transparent to-agent-pm/5',
    iconBg: 'bg-agent-pm/10',
    iconText: 'text-agent-pm',
    focusRing: 'focus-visible:border-agent-pm/50 focus-visible:ring-agent-pm/20',
    button: 'bg-agent-pm hover:bg-agent-pm/90 text-white',
    buttonShadow: 'shadow-agent-pm/25',
  },
  human_approval: {
    border: 'border-destructive/20',
    shadow: 'shadow-destructive/10 dark:shadow-destructive/5',
    headerGradient: 'from-destructive/5 via-transparent to-destructive/5',
    iconBg: 'bg-destructive/10',
    iconText: 'text-destructive',
    focusRing: 'focus-visible:border-destructive/50 focus-visible:ring-destructive/20',
    button: 'bg-destructive hover:bg-destructive/90 text-white',
    buttonShadow: 'shadow-destructive/25',
  },
};

/** Default accent style for unknown agents (architect/blue). */
export const DEFAULT_ACCENT_STYLE: AgentAccentStyle = {
  border: 'border-agent-architect/20',
  shadow: 'shadow-agent-architect/10 dark:shadow-agent-architect/5',
  headerGradient: 'from-agent-architect/5 via-transparent to-agent-architect/5',
  iconBg: 'bg-agent-architect/10',
  iconText: 'text-agent-architect',
  focusRing:
    'focus-visible:border-agent-architect/50 focus-visible:ring-agent-architect/20',
  button: 'bg-agent-architect hover:bg-agent-architect/90',
  buttonShadow: 'shadow-agent-architect/25',
};

/**
 * Get accent style for an agent, with fallback to default.
 * Always returns a defined style.
 *
 * @param agent - The agent type identifier (e.g., "architect", "developer", "reviewer").
 * @returns The AgentAccentStyle object for the specified agent, or DEFAULT_ACCENT_STYLE if not found.
 */
export function getAgentAccentStyle(agent: string): AgentAccentStyle {
  return AGENT_ACCENT_STYLES_MAP[agent] ?? DEFAULT_ACCENT_STYLE;
}
