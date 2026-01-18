import { Plus } from "lucide-react";
import { useBrainstormStore } from "@/store/brainstormStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SessionListItem } from "./SessionListItem";
import type { BrainstormingSession, SessionStatus } from "@/types/api";

interface SessionDrawerProps {
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewSession: () => void;
}

const statusOrder: SessionStatus[] = [
  "active",
  "ready_for_handoff",
  "completed",
  "failed",
];

const statusLabels: Record<SessionStatus, string> = {
  active: "Active",
  ready_for_handoff: "Ready for Handoff",
  completed: "Completed",
  failed: "Failed",
};

function groupByStatus(
  sessions: BrainstormingSession[]
): Record<SessionStatus, BrainstormingSession[]> {
  const groups: Record<SessionStatus, BrainstormingSession[]> = {
    active: [],
    ready_for_handoff: [],
    completed: [],
    failed: [],
  };

  for (const session of sessions) {
    groups[session.status].push(session);
  }

  return groups;
}

export function SessionDrawer({
  onSelectSession,
  onDeleteSession,
  onNewSession,
}: SessionDrawerProps) {
  const { sessions, activeSessionId, drawerOpen, setDrawerOpen } =
    useBrainstormStore();

  const groupedSessions = groupByStatus(sessions);
  const hasAnySessions = sessions.length > 0;

  return (
    <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
      <SheetContent side="left" className="w-80 p-0">
        <SheetHeader className="px-4 py-4 border-b">
          <SheetTitle>Sessions</SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1 h-[calc(100vh-8rem)]">
          <div className="p-2">
            {!hasAnySessions ? (
              <p className="text-center text-muted-foreground py-8">
                No sessions yet. Start a new conversation below.
              </p>
            ) : (
              statusOrder.map((status) => {
                const sessionsInGroup = groupedSessions[status];
                if (sessionsInGroup.length === 0) return null;

                return (
                  <div key={status} className="mb-4">
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-2">
                      {statusLabels[status]}
                    </h3>
                    <div className="space-y-1">
                      {sessionsInGroup.map((session) => (
                        <SessionListItem
                          key={session.id}
                          session={session}
                          isSelected={session.id === activeSessionId}
                          onSelect={onSelectSession}
                          onDelete={onDeleteSession}
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>

        <div className="border-t p-4">
          <Button
            variant="outline"
            className="w-full"
            onClick={onNewSession}
            aria-label="New Session"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Session
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
