/**
 * @fileoverview Shared node dimension constants for workflow canvas.
 *
 * Used by both AgentNode component (CSS) and layout utility (dagre).
 * Keep these in sync with Tailwind classes in AgentNode.tsx.
 */

/** Node width in pixels (matches lg breakpoint). */
export const NODE_WIDTH = 120;

/** Node height in pixels (approximate based on content). */
export const NODE_HEIGHT = 140;

/** Horizontal spacing between nodes in the same rank. */
export const NODE_SEP = 30;

/** Spacing between ranks (edge length). */
export const RANK_SEP = 40;
