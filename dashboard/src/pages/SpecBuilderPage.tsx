import { useEffect, useState, useCallback, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Menu, Lightbulb } from "lucide-react";
import { api } from "@/api/client";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputProvider,
  usePromptInputController,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { useBrainstormStore } from "@/store/brainstormStore";
import { useBrainstormSession } from "@/hooks/useBrainstormSession";
import {
  SessionDrawer,
  SessionInfoBar,
  MessageMetadata,
  ArtifactCard,
  HandoffDialog,
} from "@/components/brainstorm";
import type { BrainstormArtifact } from "@/types/api";

function SpecBuilderPageContent() {
  const navigate = useNavigate();
  const {
    activeSessionId,
    activeProfile,
    sessions,
    messages,
    artifacts,
    isStreaming,
    setDrawerOpen,
  } = useBrainstormStore();

  const {
    loadSessions,
    loadSession,
    createSession,
    sendMessage,
    deleteSession,
    handoff,
    startNewSession,
  } = useBrainstormSession();

  const { textInput } = usePromptInputController();
  const [handoffArtifact, setHandoffArtifact] = useState<BrainstormArtifact | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const activeProfileRef = useRef<string>("");

  // Load sessions and config on mount
  useEffect(() => {
    loadSessions();

    // Fetch active_profile from config for session creation
    api.getConfig().then((config) => {
      activeProfileRef.current = config.active_profile;
    }).catch(() => {
      // Fall back to empty string on error - backend will use its default
    });
  }, [loadSessions]);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage, _event: FormEvent<HTMLFormElement>) => {
      const content = message.text.trim();
      if (!content || isSubmitting) return;

      setIsSubmitting(true);

      try {
        if (activeSessionId) {
          await sendMessage(content);
        } else {
          // Create new session with first message using active profile from config
          await createSession(activeProfileRef.current, content);
        }
        textInput.clear();
      } catch {
        // Restore input on error
        textInput.setInput(content);
        // TODO: Show error toast
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting, activeSessionId, sendMessage, createSession, textInput]
  );

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      await loadSession(sessionId);
    },
    [loadSession]
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      await deleteSession(sessionId);
    },
    [deleteSession]
  );

  const handleHandoffClick = useCallback((artifact: BrainstormArtifact) => {
    setHandoffArtifact(artifact);
  }, []);

  const handleHandoffConfirm = useCallback(
    async (issueTitle: string) => {
      if (!handoffArtifact) return;

      setIsHandingOff(true);
      try {
        const result = await handoff(handoffArtifact.path, issueTitle);
        setHandoffArtifact(null);
        // Navigate to the new workflow
        navigate(`/workflows/${result.workflow_id}`);
      } finally {
        setIsHandingOff(false);
      }
    },
    [handoffArtifact, handoff, navigate]
  );

  const handleHandoffCancel = useCallback(() => {
    setHandoffArtifact(null);
  }, []);

  const getStatus = () => {
    if (isStreaming) return "streaming";
    if (isSubmitting) return "submitted";
    return "ready";
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Title>Spec Builder</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Right>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open sessions"
          >
            <Menu className="h-5 w-5" />
          </Button>
        </PageHeader.Right>
      </PageHeader>

      {/* Session Drawer */}
      <SessionDrawer
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewSession={startNewSession}
      />

      {/* Session Info Bar - shown when there's an active session */}
      {activeSessionId && messages.length > 0 && (
        <SessionInfoBar
          profile={activeProfile}
          status={sessions.find((s) => s.id === activeSessionId)?.status ?? "active"}
          messageCount={messages.length}
        />
      )}

      {/* Conversation Area */}
      <Conversation className="flex-1 overflow-hidden">
        <ConversationContent className="px-4 py-6">
          {messages.length === 0 ? (
            <ConversationEmptyState
              icon={<Lightbulb className="h-12 w-12" />}
              title="Start a brainstorming session"
              description="Type a message below to begin exploring ideas and producing design documents."
            />
          ) : (
            <div className="w-full space-y-4 max-w-3xl mx-auto">
              {messages.map((message) => {
                const hasReasoning = message.parts?.some((p) => p.type === "reasoning");
                const reasoningText = message.parts
                  ?.filter((p) => p.type === "reasoning")
                  .map((p) => p.text)
                  .join("\n") || "";
                const isStreamingEmpty = message.role === "assistant" && message.status === "streaming" && !message.content;

                const isComplete = message.role === "assistant" && message.status !== "streaming" && message.content;

                return (
                  <Message key={message.id} from={message.role}>
                    <MessageContent className={message.role === "assistant" ? "w-full" : undefined}>
                      {hasReasoning && (
                        <Reasoning isStreaming={isStreaming}>
                          <ReasoningTrigger />
                          <ReasoningContent>{reasoningText}</ReasoningContent>
                        </Reasoning>
                      )}
                      {isStreamingEmpty ? (
                        <Shimmer className="text-muted-foreground">Thinking...</Shimmer>
                      ) : (
                        <MessageResponse>{message.content}</MessageResponse>
                      )}
                      {isComplete && (
                        <MessageMetadata
                          timestamp={message.created_at}
                          content={message.content}
                        />
                      )}
                    </MessageContent>
                  </Message>
                );
              })}

              {/* Inline artifacts */}
              {artifacts.map((artifact) => (
                <ArtifactCard
                  key={artifact.id}
                  artifact={artifact}
                  onHandoff={handleHandoffClick}
                  isHandingOff={isHandingOff && handoffArtifact?.id === artifact.id}
                />
              ))}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Input Area */}
      <div className="border-t bg-background p-4">
        <PromptInput
          className="max-w-3xl mx-auto"
          onSubmit={handleSubmit}
        >
          <PromptInputTextarea
            placeholder="What would you like to design?"
            disabled={isStreaming}
          />
          <PromptInputFooter>
            <div />
            <PromptInputSubmit
              disabled={!textInput.value.trim() || isStreaming}
              status={getStatus()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>

      {/* Handoff Dialog */}
      <HandoffDialog
        open={handoffArtifact !== null}
        artifact={handoffArtifact}
        onConfirm={handleHandoffConfirm}
        onCancel={handleHandoffCancel}
        isLoading={isHandingOff}
      />
    </div>
  );
}

export default function SpecBuilderPage() {
  return (
    <PromptInputProvider>
      <SpecBuilderPageContent />
    </PromptInputProvider>
  );
}
