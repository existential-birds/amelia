# Skill Creation Plan for Amelia Dashboard Development

> **For Claude:** This is a standalone plan for creating skills in a new session. All source repositories have been cloned to `~/github/`. Use the exploration summaries below as primary source material, reading repo files only when additional detail is needed.

**Status:** Not Started

**Goal:** Create 7 comprehensive skills to support Phase 2.3 dashboard development, Spec Builder, and Debate Mode features. Each skill follows the established pattern with SKILL.md (main entry + frontmatter) and companion topic files.

**Skill Directory:** `.claude/skills/amelia/`

---

## Prerequisites

The following repositories are available at `~/github/`:
- `ui` - shadcn/ui (component patterns, CVA, registry)
- `ai-elements` - Vercel workflow components
- `xyflow` - React Flow (custom nodes/edges)
- `tailwindcss` - Tailwind v4 (CSS-first config)
- `vercel-ai-sdk` - AI SDK (useChat, streaming)
- `docling` - Document parsing
- `sqlite-vec` - Vector search extension

---

## Skill Structure Pattern

Each skill follows this structure:

```
.claude/skills/amelia/{skill-name}/
├── SKILL.md          # Main entry with YAML frontmatter
├── {TOPIC1}.md       # Detailed topic file
├── {TOPIC2}.md       # Detailed topic file
└── ...
```

**SKILL.md frontmatter format:**
```yaml
---
name: {skill-name}
description: {Brief description}. Use when {trigger conditions}. Triggers on {keywords}.
---
```

**Content guidelines:**
- SKILL.md: Quick reference, key patterns, decision tables, links to companions
- Companion files: Deep dives on specific topics, extensive code examples
- All code examples must be TypeScript with proper typing
- Focus on patterns relevant to Amelia's aviation-themed dashboard

---

## Skill 1: shadcn-ui

**Directory:** `.claude/skills/amelia/shadcn-ui/`

**Files to create:**

### SKILL.md
```yaml
---
name: shadcn-ui
description: shadcn/ui component patterns with Radix primitives and Tailwind styling. Use when building UI components, using CVA variants, implementing compound components, or styling with data-slot attributes. Triggers on shadcn, cva, cn(), data-slot, Radix, Button, Card, Dialog, VariantProps.
---
```

**Content sections:**
- Quick reference: cn() utility, basic CVA pattern
- Component anatomy: props typing, asChild pattern
- data-slot usage for CSS targeting
- Decision table: When to use each pattern
- Links to companion files

### COMPONENTS.md
**Content:**
- Button with variants (default, destructive, outline, ghost, link)
- Card compound component (Card, CardHeader, CardTitle, CardContent, CardFooter)
- Badge with status variants
- Input, Label, Textarea patterns
- Dialog/Sheet modal patterns
- Each with full TypeScript types

### CVA.md
**Content:**
- Basic variant definition
- Compound variants
- Default variants
- Responsive variants with container queries
- Integration with cn() utility
- VariantProps type extraction

### PATTERNS.md
**Content:**
- Compound component pattern (Card, Form, Sidebar)
- asChild/Slot polymorphism
- Controlled vs uncontrolled state
- Context for complex components (Sidebar, Form)
- data-slot CSS targeting patterns
- has() selector usage

**Source files to reference:**
- `~/github/ui/apps/v4/lib/utils.ts` (cn utility)
- `~/github/ui/apps/v4/registry/new-york-v4/ui/button.tsx`
- `~/github/ui/apps/v4/registry/new-york-v4/ui/card.tsx`
- `~/github/ui/apps/v4/registry/new-york-v4/ui/badge.tsx`
- `~/github/ui/apps/v4/registry/new-york-v4/ui/sidebar.tsx`

---

## Skill 2: tailwind-v4

**Directory:** `.claude/skills/amelia/tailwind-v4/`

**Files to create:**

### SKILL.md
```yaml
---
name: tailwind-v4
description: Tailwind CSS v4 with CSS-first configuration and design tokens. Use when setting up Tailwind v4, defining theme variables, using OKLCH colors, or configuring dark mode. Triggers on @theme, @tailwindcss/vite, oklch, CSS variables, --color-, tailwind v4.
---
```

**Content sections:**
- Quick reference: Vite plugin setup, @import pattern
- @theme inline directive basics
- OKLCH color format explanation
- Key differences from v3
- Links to companion files

### SETUP.md
**Content:**
- Vite plugin configuration (NOT PostCSS)
- package.json dependencies
- tsconfig.json with @types/node
- index.css with @import 'tailwindcss'
- Why no tailwind.config.js or postcss.config.js

### THEMING.md
**Content:**
- @theme directive modes (default, inline, reference)
- CSS variable naming conventions
- Aviation theme color palette in OKLCH
- Two-tier variable system (semantic + tailwind-mapped)
- Custom fonts configuration
- Animation keyframes

### DARK-MODE.md
**Content:**
- Media query strategy (prefers-color-scheme)
- Class-based strategy (.dark)
- Attribute-based strategy (data-theme)
- Theme switching implementation
- Respecting prefers-reduced-motion

**Source files to reference:**
- `~/github/tailwindcss/packages/tailwindcss/theme.css`
- `~/github/tailwindcss/packages/@tailwindcss-vite/src/index.ts`
- `~/github/tailwindcss/playgrounds/vite/vite.config.ts`

---

## Skill 3: react-flow

**Directory:** `.claude/skills/amelia/react-flow/`

**Files to create:**

### SKILL.md
```yaml
---
name: react-flow
description: React Flow (@xyflow/react) for workflow visualization with custom nodes and edges. Use when building graph visualizations, creating custom workflow nodes, implementing edge labels, or controlling viewport. Triggers on ReactFlow, @xyflow/react, Handle, NodeProps, EdgeProps, useReactFlow, fitView.
---
```

**Content sections:**
- Quick reference: Basic ReactFlow setup
- Node and edge type definitions
- Key props overview
- Links to companion files

### CUSTOM-NODES.md
**Content:**
- NodeProps typing pattern
- Handle component (target/source)
- Dynamic handles with useUpdateNodeInternals
- Styling nodes (CSS, Tailwind, inline)
- Aviation map pin node example
- Status-based styling (beacon glow)

### CUSTOM-EDGES.md
**Content:**
- EdgeProps typing pattern
- getBezierPath, getStraightPath utilities
- EdgeLabelRenderer for interactive labels
- Animated edges (dash animation, moving circle)
- BaseEdge usage
- Time label edge example

### VIEWPORT.md
**Content:**
- useReactFlow() hook methods
- fitView() with options
- setViewport(), zoomIn(), zoomOut()
- screenToFlowPosition()
- Save/restore viewport state
- Programmatic pan to node

### EVENTS.md
**Content:**
- Node events (click, drag, hover, context menu)
- Edge events (click, reconnect)
- Connection events (onConnect, onConnectStart, onConnectEnd)
- Selection events (useOnSelectionChange)
- Viewport events (useOnViewportChange)

**Source files to reference:**
- `~/github/xyflow/packages/react/src/types/`
- `~/github/xyflow/packages/react/src/components/Handle/`
- `~/github/xyflow/packages/react/src/hooks/useReactFlow.ts`
- `~/github/xyflow/examples/react/src/examples/`

---

## Skill 4: ai-elements

**Directory:** `.claude/skills/amelia/ai-elements/`

**Files to create:**

### SKILL.md
```yaml
---
name: ai-elements
description: Vercel AI Elements for workflow UI components. Use when building chat interfaces, displaying tool execution, showing reasoning/thinking, or creating job queues. Triggers on ai-elements, Queue, Confirmation, Tool, Reasoning, Shimmer, Loader, Message, Conversation, PromptInput.
---
```

**Content sections:**
- Quick reference: Installation via shadcn registry
- Component categories overview
- Integration with shadcn/ui theming
- Links to companion files

### CONVERSATION.md
**Content:**
- Conversation, ConversationContent, ConversationEmptyState
- Message, MessageContent, MessageResponse, MessageActions
- MessageAttachment for files/images
- MessageBranch for alternative responses
- Auto-scroll behavior (use-stick-to-bottom)

### PROMPT-INPUT.md
**Content:**
- PromptInput with file attachments
- PromptInputTextarea (auto-expanding)
- PromptInputSubmit (status-aware icons)
- PromptInputAttachments display
- PromptInputProvider for global state
- Drag-and-drop file handling
- Speech input (Web Speech API)

### WORKFLOW.md
**Content:**
- Queue, QueueItem, QueueSection patterns
- Tool component with state handling
- Confirmation for approval workflows
- Tool states: input-streaming → output-available
- Reasoning with auto-collapse
- Shimmer loading animation
- Loader spinner

### VISUALIZATION.md
**Content:**
- Canvas (ReactFlow wrapper)
- Node with handles
- Edge (Temporary, Animated)
- Controls, Panel, Toolbar
- Integration with custom aviation nodes

**Source files to reference:**
- `~/github/ai-elements/packages/elements/src/`
- `~/github/ai-elements/packages/elements/src/queue.tsx`
- `~/github/ai-elements/packages/elements/src/tool.tsx`
- `~/github/ai-elements/packages/elements/src/confirmation.tsx`

---

## Skill 5: vercel-ai-sdk

**Directory:** `.claude/skills/amelia/vercel-ai-sdk/`

**Files to create:**

### SKILL.md
```yaml
---
name: vercel-ai-sdk
description: Vercel AI SDK for building chat interfaces with streaming. Use when implementing useChat hook, handling tool calls, streaming responses, or building chat UI. Triggers on useChat, @ai-sdk/react, UIMessage, ChatStatus, streamText, toUIMessageStreamResponse.
---
```

**Content sections:**
- Quick reference: useChat basic usage
- ChatStatus states (ready, submitted, streaming, error)
- Message structure overview
- Links to companion files

### USE-CHAT.md
**Content:**
- Full useChat options and return values
- sendMessage, stop, regenerate methods
- Error handling (error, clearError)
- onFinish, onError callbacks
- experimental_throttle for performance
- Custom transport (DefaultChatTransport)

### MESSAGES.md
**Content:**
- UIMessage structure (id, role, parts)
- Part types: text, file, tool-*, reasoning
- TextUIPart with streaming state
- ToolUIPart with full state machine
- FileUIPart for attachments
- Type-safe message definitions

### STREAMING.md
**Content:**
- Server-side: streamText + toUIMessageStreamResponse
- UIMessageChunk types
- SSE format and parsing
- Tool execution flow
- Backpressure handling

### TOOLS.md
**Content:**
- Server-side tool definition (inputSchema, execute)
- Client-side tools (no execute)
- onToolCall handler
- addToolOutput for client tools
- addToolApprovalResponse for approval flow
- Tool state rendering patterns

**Source files to reference:**
- `~/github/vercel-ai-sdk/packages/react/src/use-chat.ts`
- `~/github/vercel-ai-sdk/packages/ai/src/ui/ui-messages.ts`
- `~/github/vercel-ai-sdk/packages/ai/src/ui-message-stream/`
- `~/github/vercel-ai-sdk/examples/next-openai/`

---

## Skill 6: docling

**Directory:** `.claude/skills/amelia/docling/`

**Files to create:**

### SKILL.md
```yaml
---
name: docling
description: Docling document parser for PDF, DOCX, and other formats. Use when parsing documents, extracting text, chunking for RAG, or batch processing files. Triggers on docling, DocumentConverter, convert, export_to_markdown, HierarchicalChunker.
---
```

**Content sections:**
- Quick reference: Basic conversion
- Supported formats list
- Output formats (Markdown, HTML, JSON)
- Links to companion files

### PARSING.md
**Content:**
- DocumentConverter initialization
- Single file conversion
- URL conversion
- Binary stream conversion (BytesIO)
- Format-specific options (PdfPipelineOptions)
- OCR configuration

### BATCH.md
**Content:**
- convert_all() for multiple files
- ConversionStatus handling (SUCCESS, PARTIAL_SUCCESS, FAILURE)
- Error handling and recovery
- ThreadPoolExecutor concurrency
- Resource limits (max_file_size, max_num_pages)

### CHUNKING.md
**Content:**
- HierarchicalChunker (structure-aware)
- HybridChunker (semantic + size)
- Chunk metadata access
- Integration with embeddings
- RAG pipeline patterns

### OUTPUT.md
**Content:**
- DoclingDocument structure
- export_to_markdown()
- export_to_html()
- export_to_dict() / export_to_json()
- save_as_* methods
- Accessing document elements (iter_all)

**Source files to reference:**
- `~/github/docling/docling/document_converter.py`
- `~/github/docling/docling/chunking/`
- `~/github/docling/examples/`
- `~/github/docling/README.md`

---

## Skill 7: sqlite-vec

**Directory:** `.claude/skills/amelia/sqlite-vec/`

**Files to create:**

### SKILL.md
```yaml
---
name: sqlite-vec
description: sqlite-vec for vector similarity search in SQLite. Use when storing embeddings, performing KNN queries, or building semantic search. Triggers on sqlite-vec, vec0, MATCH, vec_distance, partition key, float[N], serialize_float32.
---
```

**Content sections:**
- Quick reference: Extension loading, basic query
- Vector types (float32, int8, bit)
- Binary serialization format
- Links to companion files

### SETUP.md
**Content:**
- Python binding installation
- Extension loading pattern
- serialize_float32() helper
- NumPy integration (register_numpy)
- Connection setup

### TABLES.md
**Content:**
- vec0 virtual table creation
- Column types: float[N], int8[N], bit[N]
- Metadata columns (searchable)
- Partition key columns (sharding)
- Auxiliary columns (+prefix, stored only)
- chunk_size tuning

### QUERIES.md
**Content:**
- KNN query syntax (WHERE MATCH, AND k=N)
- Distance functions (L2, cosine, hamming)
- Metadata filtering in KNN
- Partition key filtering
- Point queries (by rowid)
- Full table scan

### OPERATIONS.md
**Content:**
- Vector constructor functions (vec_f32, vec_int8, vec_bit)
- Arithmetic (vec_add, vec_sub)
- vec_normalize, vec_slice
- vec_quantize_binary, vec_quantize_i8
- vec_each for iteration
- Batch insert patterns

**Source files to reference:**
- `~/github/sqlite-vec/bindings/python/`
- `~/github/sqlite-vec/examples/simple-python/`
- `~/github/sqlite-vec/examples/python-recipes/`
- `~/github/sqlite-vec/ARCHITECTURE.md`

---

## Implementation Order

### Phase 1: Core Dashboard Skills (Priority 1)

| Order | Skill | Reason |
|-------|-------|--------|
| 1 | tailwind-v4 | Foundation - theming affects all components |
| 2 | shadcn-ui | Foundation - all UI components depend on this |
| 3 | react-flow | Custom WorkflowCanvas needs this |
| 4 | ai-elements | Queue, Confirmation, Tool components |

### Phase 2: Spec Builder Skills (Priority 2)

| Order | Skill | Reason |
|-------|-------|--------|
| 5 | vercel-ai-sdk | Chat interface for Spec Builder |
| 6 | docling | Document parsing for Spec Builder |
| 7 | sqlite-vec | Vector search for Spec Builder |

---

## Verification Checklist

After creating each skill:

- [ ] SKILL.md has valid YAML frontmatter
- [ ] Description includes trigger keywords
- [ ] Quick reference has working code examples
- [ ] All TypeScript examples have proper types
- [ ] Companion files are linked from SKILL.md
- [ ] Code examples are tested/verified against source repos
- [ ] Patterns are relevant to Amelia's aviation theme where applicable

---

## Session Instructions

When starting the new session, provide these instructions:

```
I need to create skills for the Amelia dashboard project.

Read the plan at docs/plans/2025-12-06-skill-creation-plan.md

The source repositories are cloned at ~/github/:
- ui (shadcn/ui)
- ai-elements
- xyflow (React Flow)
- tailwindcss (v4)
- vercel-ai-sdk
- docling
- sqlite-vec

Create skills in the order specified in the plan. For each skill:
1. Create the directory at .claude/skills/amelia/{skill-name}/
2. Write SKILL.md with proper frontmatter
3. Write each companion file with detailed code examples
4. Reference source files from ~/github/ for accurate patterns

Start with tailwind-v4 (Phase 1, Order 1).
```

---

## Exploration Summaries (Reference)

### shadcn/ui Key Findings
- cn() = clsx + tailwind-merge in utils.ts
- CVA for variants with defaultVariants, compoundVariants
- data-slot on every component for CSS hooks
- asChild pattern uses @radix-ui/react-slot
- TypeScript: React.ComponentProps<> + VariantProps<typeof variants>
- 54 components in registry/new-york-v4/ui/

### Tailwind v4 Key Findings
- No tailwind.config.js - CSS-first with @theme
- @tailwindcss/vite plugin (NOT PostCSS)
- @theme inline maps CSS vars to utilities
- OKLCH colors: oklch(L% C H)
- Dark mode via media query, class, or attribute

### React Flow Key Findings
- NodeProps<Node<Data, 'type'>> for custom nodes
- Handle component with type="target"/"source"
- getBezierPath() for edge paths
- EdgeLabelRenderer for interactive labels
- useReactFlow() for viewport control
- useUpdateNodeInternals() for dynamic handles

### ai-elements Key Findings
- 30+ components for AI interfaces
- Queue, Confirmation, Tool, Reasoning core components
- Tool states: input-streaming → output-available
- Integrates with shadcn/ui theming
- Canvas wraps ReactFlow for workflows

### Vercel AI SDK Key Findings
- useChat returns messages, status, sendMessage, stop, regenerate
- ChatStatus: 'ready' | 'submitted' | 'streaming' | 'error'
- UIMessage has parts array (text, tool-*, file, reasoning)
- streamText().toUIMessageStreamResponse() for server
- onToolCall, addToolOutput for client-side tools

### Docling Key Findings
- 15+ formats: PDF, DOCX, PPTX, HTML, MD, images
- DocumentConverter().convert() → doc.export_to_markdown()
- HierarchicalChunker, HybridChunker for RAG
- convert_all() for batch with ThreadPoolExecutor
- Sync API only (no native async)

### sqlite-vec Key Findings
- sqlite_vec.load(db) to enable
- vec0 virtual table with float[N], int8[N], bit[N]
- KNN: WHERE embedding MATCH ? AND k=10 ORDER BY distance
- partition key for multi-tenant sharding
- struct.pack for binary serialization
