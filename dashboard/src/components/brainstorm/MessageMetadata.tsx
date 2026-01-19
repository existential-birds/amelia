import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Copy, Check, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface MessageMetadataProps {
  timestamp: string;
  content: string;
  className?: string;
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

  // Within last hour - show relative
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  // Older - show date
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
  className,
}: MessageMetadataProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard write failed - silently ignore
    }
  }, [content]);

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

      {/* Spacer */}
      <div className="flex-1" />

      {/* Copy Button */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
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
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            {copied ? "Copied!" : "Copy message"}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
