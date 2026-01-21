import { useEffect, useState, useCallback, useRef, type FormEvent } from "react";
import { useShallow } from "zustand/react/shallow";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Menu, Lightbulb, Bot, Cpu } from "lucide-react";
import { api } from "@/api/client";
import { formatDriver, formatModel } from "@/lib/utils";
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
import { ToolExecutionStrip } from "@/components/ai-elements/tool-execution-strip";
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
  CopyButton,
} from "@/components/brainstorm";
import type { BrainstormArtifact } from "@/types/api";
import type { ConfigProfileInfo } from "@/types";

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
    sessionUsage,
  } = useBrainstormStore(useShallow((state) => ({
    activeSessionId: state.activeSessionId,
    activeProfile: state.activeProfile,
    sessions: state.sessions,
    messages: state.messages,
    artifacts: state.artifacts,
    isStreaming: state.isStreaming,
    setDrawerOpen: state.setDrawerOpen,
    sessionUsage: state.sessionUsage,
  })));

  const {
    loadSessions,
    loadSession,
    createSession,
    sendMessage,
    deleteSession,
    handoff,
    startNewSession,
    startPrimedSession,
  } = useBrainstormSession();

  const { textInput } = usePromptInputController();
  const [handoffArtifact, setHandoffArtifact] = useState<BrainstormArtifact | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [configProfileInfo, setConfigProfileInfo] = useState<ConfigProfileInfo | null>(null);
  const activeProfileRef = useRef<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load sessions and config on mount
  useEffect(() => {
    let mounted = true;

    const init = async () => {
      await loadSessions();
      if (!mounted) return;

      try {
        const config = await api.getConfig();
        if (mounted) {
          activeProfileRef.current = config.active_profile;
          setConfigProfileInfo(config.active_profile_info);
        }
      } catch (error) {
        if (mounted) {
          console.warn('Failed to load config, using defaults:', error);
        }
      }
    };

    init();

    return () => {
      mounted = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
        // Return focus to input after submit
        textareaRef.current?.focus();
      } catch {
        // Restore input on error
        textInput.setInput(content);
        toast.error("Failed to send message");
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
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        toast.error(`Handoff failed: ${message}`);
        // Keep artifact so user can retry - don't clear or navigate
      } finally {
        setIsHandingOff(false);
      }
    },
    [handoffArtifact, handoff, navigate]
  );

  const handleHandoffCancel = useCallback(() => {
    setHandoffArtifact(null);
  }, []);

  const handleStartBrainstorming = useCallback(async () => {
    if (isStreaming) return;
    try {
      await startPrimedSession(activeProfileRef.current);
    } catch {
      toast.error("Failed to start session");
    }
  }, [isStreaming, startPrimedSession]);

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
          usageSummary={sessionUsage ?? undefined}
        />
      )}

      {/* Conversation Area */}
      <Conversation
        className="flex-1 overflow-hidden"
        aria-live="polite"
        aria-atomic="false"
        aria-busy={isStreaming}
      >
        <ConversationContent className="px-2 sm:px-4 py-4 sm:py-6">
          {messages.length === 0 ? (
            <ConversationEmptyState>
              <>
                <div className="text-muted-foreground">
                  <Lightbulb className="h-12 w-12" />
                </div>
                <div className="space-y-1">
                  <h3 className="font-medium text-sm">Start a brainstorming session</h3>
                  <p className="text-muted-foreground text-sm">
                    Select a session from the sidebar or start a new one to begin exploring ideas and producing design documents.
                  </p>
                </div>
                {/* Profile Info Badge */}
                {configProfileInfo && (
                  <div className="flex items-center gap-2 mt-4 text-xs font-mono">
                    <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-primary/10 border border-primary/20">
                      <Bot className="h-3 w-3 text-primary" />
                      <span className="text-foreground font-medium">
                        {formatModel(configProfileInfo.model)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 px-1.5 py-1 rounded bg-muted/50">
                      <Cpu className="h-3 w-3 text-muted-foreground" />
                      <span className="text-muted-foreground text-[10px] uppercase tracking-wider">
                        {formatDriver(configProfileInfo.driver)}
                      </span>
                    </div>
                  </div>
                )}
                {/* Start Brainstorming Button */}
                <Button
                  className="mt-6"
                  onClick={handleStartBrainstorming}
                  disabled={isStreaming}
                >
                  <Lightbulb className="h-4 w-4 mr-2" />
                  Start Brainstorming
                </Button>
              </>
            </ConversationEmptyState>
          ) : (
            <div className="w-full space-y-6 max-w-3xl mx-auto">
              {messages.map((message) => {
                // Check both message.parts (for completed messages) and message.reasoning (for streaming)
                const hasReasoning = message.parts?.some((p) => p.type === "reasoning") || !!message.reasoning;
                const reasoningText = message.parts
                  ?.filter((p) => p.type === "reasoning")
                  .map((p) => p.text)
                  .join("\n") || message.reasoning || "";
                const isStreamingEmpty = message.role === "assistant" && message.status === "streaming" && !message.content && !message.reasoning;

                const isComplete = message.role === "assistant" && message.status !== "streaming" && message.content;

                return (
                  <Message key={message.id} from={message.role}>
                    {message.role === "user" && (
                      <div className="flex items-center gap-1.5 ml-auto">
                        <CopyButton content={message.content} />
                        <MessageContent from={message.role}>
                          <MessageResponse>{message.content}</MessageResponse>
                        </MessageContent>
                      </div>
                    )}
                    {message.role !== "user" && (
                      <MessageContent from={message.role} className="w-full">
                        {hasReasoning && (
                          <Reasoning isStreaming={isStreaming}>
                            <ReasoningTrigger />
                            <ReasoningContent>{reasoningText}</ReasoningContent>
                          </Reasoning>
                        )}
                        {message.toolCalls && message.toolCalls.length > 0 && (
                          <ToolExecutionStrip
                            toolCalls={message.toolCalls}
                            isStreaming={message.status === "streaming"}
                          />
                        )}
                        {isStreamingEmpty ? (
                          <Shimmer className="text-muted-foreground">Thinking...</Shimmer>
                        ) : (
                          <MessageResponse>{message.content}</MessageResponse>
                        )}
                        {message.status === "error" && (
                          <div className="text-red-500 text-sm mt-2 flex items-center gap-1">
                            <span>⚠</span>
                            <span>{message.errorMessage || "Message failed"}</span>
                          </div>
                        )}
                        {isComplete && (
                          <MessageMetadata
                            timestamp={message.created_at}
                            content={message.content}
                            usage={message.usage}
                          />
                        )}
                      </MessageContent>
                    )}
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

      {/* Input Area - only shown when there's an active session */}
      {activeSessionId && (
        <div className="border-t bg-background p-2 sm:p-4">
          <PromptInput
            className="max-w-3xl mx-auto"
            onSubmit={handleSubmit}
          >
            <PromptInputTextarea
              ref={textareaRef}
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
      )}

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
