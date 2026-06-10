import { cn } from "@/lib/utils";
import { Copy, Check, Clock } from "lucide-react";
import type { MessageUsage } from "@/types/api";
import { Button } from "@/components/ui/button";
import { useCopyFeedback } from "@/hooks/useCopyFeedback";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface MessageMetadataProps {
  timestamp: string;
  content: string;
  usage?: MessageUsage;
  className?: string;
}

/**
 * Formats a token count to a human-readable string (e.g., 12400 -> "12.4K").
 */
function formatTokens(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return count.toString();
}

/**
 * Formats an ISO timestamp to a human-readable relative or absolute time.
 */
function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(date.getFullYear() !== now.getFullYear() && { year: "numeric" }),
  });
}

/**
 * Formats an ISO timestamp to a full date/time string for tooltip.
 */
function formatFullTimestamp(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Message metadata footer with timestamp and copy action.
 *
 * Displayed below assistant messages to provide context and actions.
 */
export function MessageMetadata({
  timestamp,
  content,
  usage,
  className,
}: MessageMetadataProps) {
  const { copied, handleCopy } = useCopyFeedback(content);

  return (
    <div
      className={cn(
        "flex items-center gap-3 mt-2 pt-2 border-t border-border/30",
        "text-[11px] text-muted-foreground/70 font-mono",
        className
      )}
    >
      {/* Timestamp */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-1 cursor-default">
              <Clock className="h-3 w-3" />
              <span>{formatTimestamp(timestamp)}</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            {formatFullTimestamp(timestamp)}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Token usage and cost */}
      {usage && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/50">◈</span>
          <span>{formatTokens(usage.input_tokens + usage.output_tokens)} tok</span>
          <span className="text-emerald-500/70">${usage.cost_usd.toFixed(2)}</span>
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Copy Button */}
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "h-6 w-6 text-muted-foreground/50",
          "hover:text-muted-foreground hover:bg-muted/50",
          "transition-colors"
        )}
        onClick={handleCopy}
        aria-label={copied ? "Copied" : "Copy message"}
      >
        {copied ? (
          <Check className="h-3 w-3 text-emerald-500" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </Button>
    </div>
  );
}
