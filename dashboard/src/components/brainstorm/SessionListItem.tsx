import { formatDistanceToNow } from "date-fns";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
          isSelected && "bg-accent"
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
          <span className="text-xs text-muted-foreground">{timeAgo}</span>
        </div>
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100"
            aria-label="Options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => onDelete(session.id)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
