import { formatDistanceToNow } from "date-fns";
import { Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { BrainstormingSession, SessionStatus } from "@/types/api";

interface SessionListItemProps {
  session: BrainstormingSession;
  isSelected: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

const statusStyles: Record<SessionStatus, string> = {
  active: "bg-status-running",
  ready_for_handoff: "bg-status-pending",
  completed: "bg-status-completed",
  failed: "bg-status-failed",
};

export function SessionListItem({
  session,
  isSelected,
  onSelect,
  onDelete,
}: SessionListItemProps) {
  const timeAgo = formatDistanceToNow(new Date(session.updated_at), {
    addSuffix: true,
  });

  return (
    <div className="group flex w-full items-center gap-2 rounded-lg p-2 min-w-0 overflow-hidden">
      <Button
        variant="ghost"
        className={cn(
          "min-w-0 flex-1 !shrink justify-start gap-3 h-auto py-2 px-2",
          "hover:bg-session-hover",
          isSelected && "bg-session-selected border-l-2 border-session-active-border rounded-l-none"
        )}
        onClick={() => onSelect(session.id)}
        aria-label={session.topic || "Untitled"}
      >
        <span
          data-testid="status-indicator"
          className={cn("h-2 w-2 rounded-full shrink-0", statusStyles[session.status])}
        />
        <div className="flex flex-col items-start text-left min-w-0 w-0 flex-1">
          <span className="text-sm font-medium truncate max-w-full">
            {session.topic || "Untitled"}
          </span>
          <span className={cn(
            "text-xs",
            isSelected ? "text-session-selected-foreground/70" : "text-muted-foreground"
          )}>
            {timeAgo}
          </span>
        </div>
      </Button>

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100 text-destructive hover:text-destructive hover:bg-destructive/10"
        aria-label="Delete session"
        onClick={() => onDelete(session.id)}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
