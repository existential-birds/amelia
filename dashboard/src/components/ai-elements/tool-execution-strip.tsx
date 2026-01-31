import { cn } from "@/lib/utils";
import type { ToolCall } from "@/types/api";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { memo, useMemo } from "react";

export interface ToolExecutionStripProps {
  toolCalls: ToolCall[];
  className?: string;
  /** Whether the message is still streaming (affects running state display) */
  isStreaming?: boolean;
}

type ToolStatus = "completed" | "running" | "error";

const getToolStatus = (state: ToolCall["state"]): ToolStatus => {
  switch (state) {
    case "output-available":
      return "completed";
    case "output-error":
      return "error";
    default:
      return "running";
  }
};

const statusColors: Record<ToolStatus, string> = {
  completed: "bg-status-completed",
  running: "bg-primary animate-pulse",
  error: "bg-destructive",
};

const statusLabels: Record<ToolStatus, string> = {
  completed: "Completed",
  running: "Running",
  error: "Failed",
};

interface ToolPipProps {
  toolCall: ToolCall;
}

const ToolPip = memo(({ toolCall }: ToolPipProps) => {
  const status = getToolStatus(toolCall.state);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-block size-2 rounded-full transition-colors cursor-default",
            statusColors[status]
          )}
          aria-label={`${toolCall.tool_name}: ${statusLabels[status]}`}
        />
      </TooltipTrigger>
      <TooltipContent side="top" className="font-mono text-xs">
        <span className="font-medium">{toolCall.tool_name}</span>
        <span className="text-muted-foreground ml-2">{statusLabels[status]}</span>
      </TooltipContent>
    </Tooltip>
  );
});

ToolPip.displayName = "ToolPip";

/**
 * A compact single-line strip showing tool execution status.
 * Displays pips for each tool with hover tooltips and summary stats.
 */
export const ToolExecutionStrip = memo(
  ({ toolCalls, className, isStreaming }: ToolExecutionStripProps) => {
    const stats = useMemo(() => {
      const completed = toolCalls.filter(
        (tc) => tc.state === "output-available"
      ).length;
      const errors = toolCalls.filter(
        (tc) => tc.state === "output-error"
      ).length;
      const running = toolCalls.length - completed - errors;

      return { completed, errors, running, total: toolCalls.length };
    }, [toolCalls]);

    if (toolCalls.length === 0) {
      return null;
    }

    // Build summary text
    const summaryParts: string[] = [];
    if (stats.completed > 0) {
      summaryParts.push(`${stats.completed} completed`);
    }
    if (stats.running > 0) {
      summaryParts.push(`${stats.running} running`);
    }
    if (stats.errors > 0) {
      summaryParts.push(`${stats.errors} failed`);
    }

    return (
      <div
        className={cn(
          "flex items-center gap-3 px-3 py-2 rounded-md",
          "bg-secondary/50 border border-border/30",
          "font-mono text-xs text-muted-foreground",
          className
        )}
      >
        {/* Tool pips */}
        <div className="flex items-center gap-1.5" role="list" aria-label="Tool execution status">
          {toolCalls
            .filter((tc) => tc.state !== "output-available")
            .slice(0, 10)
            .map((toolCall) => (
              <ToolPip key={toolCall.tool_call_id} toolCall={toolCall} />
            ))}
        </div>

        {/* Separator */}
        <div className="h-3 w-px bg-border/50" aria-hidden="true" />

        {/* Summary stats */}
        <div className="flex items-center gap-1">
          <span className="tabular-nums">{stats.total}</span>
          <span>tools</span>
          {summaryParts.length > 0 && (
            <>
              <span className="mx-1">·</span>
              <span>{summaryParts.join(", ")}</span>
            </>
          )}
          {isStreaming && stats.running > 0 && (
            <span className="ml-1 text-primary">...</span>
          )}
        </div>
      </div>
    );
  }
);

ToolExecutionStrip.displayName = "ToolExecutionStrip";
