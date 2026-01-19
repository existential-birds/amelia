import { cn } from "@/lib/utils";
import { Bot, Cpu, MessageSquare, Circle } from "lucide-react";
import type { ProfileInfo, SessionStatus } from "@/types/api";

interface SessionInfoBarProps {
  profile: ProfileInfo | null;
  status: SessionStatus;
  messageCount: number;
  className?: string;
}

/**
 * Formats driver string for display.
 * "api:openrouter" -> "API"
 * "cli:claude" -> "CLI"
 */
function formatDriver(driver: string): string {
  if (driver.startsWith("api:")) return "API";
  if (driver.startsWith("cli:")) return "CLI";
  return driver.toUpperCase();
}

/**
 * Formats model name for display.
 * "sonnet" -> "Sonnet"
 * "claude-3-5-sonnet" -> "Claude 3.5 Sonnet"
 */
function formatModel(model: string): string {
  // Handle simple names like "sonnet", "opus", "haiku"
  if (/^(sonnet|opus|haiku)$/i.test(model)) {
    return model.charAt(0).toUpperCase() + model.slice(1).toLowerCase();
  }
  // Handle longer model names - capitalize and clean up
  return model
    .split(/[-_]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
    .replace(/(\d)(\d)/g, "$1.$2"); // "35" -> "3.5"
}

const statusConfig: Record<SessionStatus, { label: string; color: string }> = {
  active: { label: "Active", color: "text-emerald-400" },
  ready_for_handoff: { label: "Ready", color: "text-amber-400" },
  completed: { label: "Done", color: "text-blue-400" },
  failed: { label: "Failed", color: "text-red-400" },
};

/**
 * Session info bar displaying model, driver, status and message count.
 *
 * Features a compact, information-dense layout with visual badges
 * for quick scanning of session context.
 */
export function SessionInfoBar({
  profile,
  status,
  messageCount,
  className,
}: SessionInfoBarProps) {
  const statusInfo = statusConfig[status];

  return (
    <div
      className={cn(
        "flex items-center gap-3 px-4 py-2 border-b border-border/50",
        "bg-gradient-to-r from-background via-muted/30 to-background",
        "text-xs font-mono",
        className
      )}
    >
      {/* Model + Driver Badge */}
      {profile && (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-primary/10 border border-primary/20">
            <Bot className="h-3 w-3 text-primary" />
            <span className="text-foreground font-medium">
              {formatModel(profile.model)}
            </span>
          </div>
          <div className="flex items-center gap-1 px-1.5 py-1 rounded bg-muted/50">
            <Cpu className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground text-[10px] uppercase tracking-wider">
              {formatDriver(profile.driver)}
            </span>
          </div>
        </div>
      )}

      {/* Divider when profile exists */}
      {profile && <div className="h-4 w-px bg-border/50" />}

      {/* Status Indicator */}
      <div className="flex items-center gap-1.5">
        <Circle
          className={cn("h-2 w-2 fill-current", statusInfo.color)}
        />
        <span className={cn("text-muted-foreground", statusInfo.color)}>
          {statusInfo.label}
        </span>
      </div>

      {/* Message Count */}
      <div className="flex items-center gap-1 ml-auto text-muted-foreground">
        <MessageSquare className="h-3 w-3" />
        <span>{messageCount}</span>
      </div>
    </div>
  );
}
