import { useEffect, useState, useCallback, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Menu, Lightbulb, Bot, Cpu } from "lucide-react";
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
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
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
import type { ConfigProfileInfo } from "@/types";

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
  const [configProfileInfo, setConfigProfileInfo] = useState<ConfigProfileInfo | null>(null);
  const activeProfileRef = useRef<string>("");

  // Load sessions and config on mount
  useEffect(() => {
    loadSessions();

    // Fetch active_profile from config for session creation and display
    api.getConfig().then((config) => {
      activeProfileRef.current = config.active_profile;
      setConfigProfileInfo(config.active_profile_info);
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
            >
              <>
                <div className="text-muted-foreground">
                  <Lightbulb className="h-12 w-12" />
                </div>
                <div className="space-y-1">
                  <h3 className="font-medium text-sm">Start a brainstorming session</h3>
                  <p className="text-muted-foreground text-sm">
                    Type a message below to begin exploring ideas and producing design documents.
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
                    <MessageContent className={message.role === "assistant" ? "w-full" : undefined}>
                      {hasReasoning && (
                        <Reasoning isStreaming={isStreaming}>
                          <ReasoningTrigger />
                          <ReasoningContent>{reasoningText}</ReasoningContent>
                        </Reasoning>
                      )}
                      {message.toolCalls?.map((toolCall) => (
                        <Tool key={toolCall.tool_call_id}>
                          <ToolHeader
                            title={toolCall.tool_name}
                            type="tool-invocation"
                            state={toolCall.state}
                          />
                          <ToolContent>
                            <ToolInput input={toolCall.input} />
                            <ToolOutput
                              output={toolCall.output}
                              errorText={toolCall.errorText}
                            />
                          </ToolContent>
                        </Tool>
                      ))}
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
