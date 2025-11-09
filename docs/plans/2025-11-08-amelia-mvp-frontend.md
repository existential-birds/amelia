# Amelia MVP Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build dual-interface frontend (Web UI + Terminal UI) for Amelia with shared state management, real-time WebSocket updates, and shadcn/ui components.

**Architecture:** React 19 with Vite for Web UI, Ink for Terminal UI, shared TypeScript services/stores via Zustand, WebSocket for real-time updates, shadcn/ui + Tailwind CSS for styling.

**Tech Stack:** React 19, TypeScript, Vite, React Router v7, Zustand, Axios, shadcn/ui, Tailwind CSS 4, Ink (Terminal), Motion (animations)

---

## Phase 1: Web UI Foundation

### Task 1: Web UI Project Setup

**Files:**
- Create: `frontend-web/package.json`
- Create: `frontend-web/tsconfig.json`
- Create: `frontend-web/vite.config.ts`
- Create: `frontend-web/index.html`
- Create: `frontend-web/.gitignore`

**Step 1: Initialize Vite project**

```bash
cd frontend-web
npm create vite@latest . -- --template react-ts
```

**Step 2: Install core dependencies**

```bash
npm install react@19.2.0 react-dom@19.2.0
npm install react-router@7.9.5 @remix-run/router@1.23.0
npm install zustand@5.0.8 axios@1.13.2
npm install class-variance-authority clsx tailwind-merge
npm install motion@1.6.0 lucide-react@0.553.0
```

**Step 3: Install shadcn/ui dependencies**

```bash
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu
npm install @radix-ui/react-select @radix-ui/react-tabs
npm install @radix-ui/react-toast @radix-ui/react-tooltip
npm install @radix-ui/react-scroll-area @radix-ui/react-slot
```

**Step 4: Install dev dependencies**

```bash
npm install -D tailwindcss@4.1.17 autoprefixer postcss
npm install -D @types/node
```

**Step 5: Create Vite config**

```typescript
// frontend-web/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

**Step 6: Create TypeScript config**

```json
// frontend-web/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

**Step 7: Create index.html**

```html
<!-- frontend-web/index.html -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Amelia - LLM Workflow Orchestration</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 8: Create .gitignore**

```bash
# frontend-web/.gitignore
node_modules
dist
dist-ssr
*.local
.DS_Store
```

**Step 9: Commit**

```bash
git add frontend-web/
git commit -m "feat(web): initialize Vite React TypeScript project"
```

---

### Task 2: Tailwind CSS Setup

**Files:**
- Create: `frontend-web/tailwind.config.ts`
- Create: `frontend-web/postcss.config.js`
- Create: `frontend-web/src/styles/globals.css`

**Step 1: Create Tailwind config**

```typescript
// frontend-web/tailwind.config.ts
import type { Config } from 'tailwindcss'

export default {
  darkMode: ['class'],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
```

**Step 2: Install tailwindcss-animate**

```bash
npm install -D tailwindcss-animate
```

**Step 3: Create PostCSS config**

```javascript
// frontend-web/postcss.config.js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

**Step 4: Create global CSS with design tokens**

```css
/* frontend-web/src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;

    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;

    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;

    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;

    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;

    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;

    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;

    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;

    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;

    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;

    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;

    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;

    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;

    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;

    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;

    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;

    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;

    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

**Step 5: Commit**

```bash
git add frontend-web/
git commit -m "feat(web): setup Tailwind CSS with design tokens"
```

---

### Task 3: Base TypeScript Types

**Files:**
- Create: `frontend-web/src/types/agent.ts`
- Create: `frontend-web/src/types/workflow.ts`
- Create: `frontend-web/src/types/document.ts`
- Create: `frontend-web/src/types/chat.ts`
- Create: `frontend-web/src/types/common.ts`

**Step 1: Create common types**

```typescript
// frontend-web/src/types/common.ts
export type UUID = string;

export interface Timestamped {
  created_at: string;
  updated_at: string;
}

export type Status = 'idle' | 'running' | 'completed' | 'failed' | 'paused';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  detail: string;
  status_code: number;
}
```

**Step 2: Create agent types**

```typescript
// frontend-web/src/types/agent.ts
import { UUID, Timestamped, Status } from './common';

export interface AgentConfig {
  name: string;
  description: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  timeout: number;
  retry_attempts: number;
  context_sources: string[];
}

export interface AgentResult {
  status: Status;
  output: Record<string, any>;
  error?: string;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  metadata: Record<string, any>;
}

export interface Agent extends Timestamped {
  id: UUID;
  config: AgentConfig;
  status: Status;
  result?: AgentResult;
}

export interface AgentCreateRequest {
  config: AgentConfig;
}

export interface AgentExecuteRequest {
  input_data: Record<string, any>;
  timeout?: number;
}
```

**Step 3: Create workflow types**

```typescript
// frontend-web/src/types/workflow.ts
import { UUID, Timestamped, Status } from './common';

export interface WorkflowNode {
  id: string;
  type: 'agent' | 'condition' | 'parallel';
  agent_name?: string;
  config?: Record<string, any>;
}

export interface WorkflowEdge {
  from: string;
  to: string;
  condition?: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: Record<string, any>;
}

export interface Workflow extends Timestamped {
  id: UUID;
  name: string;
  description: string;
  definition: WorkflowDefinition;
  status: Status;
  started_at?: string;
  completed_at?: string;
  current_node?: string;
  result?: Record<string, any>;
}

export interface WorkflowCreateRequest {
  name: string;
  description: string;
  definition: WorkflowDefinition;
}

export interface WorkflowExecuteRequest {
  input_data: Record<string, any>;
}
```

**Step 4: Create document types**

```typescript
// frontend-web/src/types/document.ts
import { UUID, Timestamped } from './common';

export type DocumentType = 'pdf' | 'markdown' | 'text' | 'html' | 'code' | 'web_page';

export interface Document extends Timestamped {
  id: UUID;
  title: string;
  content: string;
  document_type: DocumentType;
  source_url?: string;
  file_path?: string;
  file_size?: number;
  metadata: Record<string, any>;
}

export interface DocumentUploadRequest {
  file: File;
  metadata?: Record<string, any>;
}

export interface DocumentSearchRequest {
  query: string;
  top_k?: number;
  similarity_threshold?: number;
}

export interface DocumentSearchResult {
  document: Document;
  chunk_content: string;
  similarity: number;
  chunk_index: number;
}
```

**Step 5: Create chat types**

```typescript
// frontend-web/src/types/chat.ts
import { UUID, Timestamped } from './common';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: UUID;
  role: MessageRole;
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface ChatSession extends Timestamped {
  id: UUID;
  title: string;
  messages: Message[];
  model: string;
  temperature: number;
  max_tokens: number;
}

export interface ChatSendRequest {
  message: string;
  context_documents?: UUID[];
  stream?: boolean;
}

export interface ChatStreamChunk {
  delta: string;
  finish_reason?: 'stop' | 'length' | 'error';
}
```

**Step 6: Commit**

```bash
git add frontend-web/src/types/
git commit -m "feat(web): add TypeScript type definitions"
```

---

### Task 4: API Client Service

**Files:**
- Create: `frontend-web/src/services/api.ts`
- Create: `frontend-web/src/services/agentService.ts`
- Create: `frontend-web/src/services/workflowService.ts`
- Create: `frontend-web/src/services/documentService.ts`
- Create: `frontend-web/src/services/chatService.ts`

**Step 1: Create base API client**

```typescript
// frontend-web/src/services/api.ts
import axios, { AxiosInstance, AxiosError } from 'axios';
import { ApiError } from '@/types/common';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: '/api',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add any auth tokens here if needed
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ApiError>) => {
        const apiError: ApiError = {
          detail: error.response?.data?.detail || error.message,
          status_code: error.response?.status || 500,
        };
        return Promise.reject(apiError);
      }
    );
  }

  getInstance(): AxiosInstance {
    return this.client;
  }
}

export const apiClient = new ApiClient().getInstance();
```

**Step 2: Create agent service**

```typescript
// frontend-web/src/services/agentService.ts
import { apiClient } from './api';
import {
  Agent,
  AgentCreateRequest,
  AgentExecuteRequest,
  AgentResult,
} from '@/types/agent';
import { UUID } from '@/types/common';

export const agentService = {
  async list(): Promise<Agent[]> {
    const response = await apiClient.get<Agent[]>('/agents');
    return response.data;
  },

  async get(id: UUID): Promise<Agent> {
    const response = await apiClient.get<Agent>(`/agents/${id}`);
    return response.data;
  },

  async create(request: AgentCreateRequest): Promise<Agent> {
    const response = await apiClient.post<Agent>('/agents', request);
    return response.data;
  },

  async execute(id: UUID, request: AgentExecuteRequest): Promise<AgentResult> {
    const response = await apiClient.post<AgentResult>(
      `/agents/${id}/execute`,
      request
    );
    return response.data;
  },

  async cancel(id: UUID): Promise<void> {
    await apiClient.post(`/agents/${id}/cancel`);
  },

  async delete(id: UUID): Promise<void> {
    await apiClient.delete(`/agents/${id}`);
  },
};
```

**Step 3: Create workflow service**

```typescript
// frontend-web/src/services/workflowService.ts
import { apiClient } from './api';
import {
  Workflow,
  WorkflowCreateRequest,
  WorkflowExecuteRequest,
} from '@/types/workflow';
import { UUID } from '@/types/common';

export const workflowService = {
  async list(): Promise<Workflow[]> {
    const response = await apiClient.get<Workflow[]>('/workflows');
    return response.data;
  },

  async get(id: UUID): Promise<Workflow> {
    const response = await apiClient.get<Workflow>(`/workflows/${id}`);
    return response.data;
  },

  async create(request: WorkflowCreateRequest): Promise<Workflow> {
    const response = await apiClient.post<Workflow>('/workflows', request);
    return response.data;
  },

  async execute(id: UUID, request: WorkflowExecuteRequest): Promise<void> {
    await apiClient.post(`/workflows/${id}/execute`, request);
  },

  async cancel(id: UUID): Promise<void> {
    await apiClient.post(`/workflows/${id}/cancel`);
  },

  async delete(id: UUID): Promise<void> {
    await apiClient.delete(`/workflows/${id}`);
  },

  async getPresets(): Promise<string[]> {
    const response = await apiClient.get<string[]>('/workflows/presets');
    return response.data;
  },
};
```

**Step 4: Create document service**

```typescript
// frontend-web/src/services/documentService.ts
import { apiClient } from './api';
import {
  Document,
  DocumentUploadRequest,
  DocumentSearchRequest,
  DocumentSearchResult,
} from '@/types/document';
import { UUID } from '@/types/common';

export const documentService = {
  async list(): Promise<Document[]> {
    const response = await apiClient.get<Document[]>('/rag/documents');
    return response.data;
  },

  async get(id: UUID): Promise<Document> {
    const response = await apiClient.get<Document>(`/rag/documents/${id}`);
    return response.data;
  },

  async upload(request: DocumentUploadRequest): Promise<Document> {
    const formData = new FormData();
    formData.append('file', request.file);
    if (request.metadata) {
      formData.append('metadata', JSON.stringify(request.metadata));
    }

    const response = await apiClient.post<Document>(
      '/rag/documents/upload',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  },

  async search(
    request: DocumentSearchRequest
  ): Promise<DocumentSearchResult[]> {
    const response = await apiClient.post<DocumentSearchResult[]>(
      '/rag/search',
      request
    );
    return response.data;
  },

  async delete(id: UUID): Promise<void> {
    await apiClient.delete(`/rag/documents/${id}`);
  },

  async scrapeWeb(url: string): Promise<Document> {
    const response = await apiClient.post<Document>('/rag/scrape', { url });
    return response.data;
  },
};
```

**Step 5: Create chat service**

```typescript
// frontend-web/src/services/chatService.ts
import { apiClient } from './api';
import {
  ChatSession,
  ChatSendRequest,
  Message,
} from '@/types/chat';
import { UUID } from '@/types/common';

export const chatService = {
  async listSessions(): Promise<ChatSession[]> {
    const response = await apiClient.get<ChatSession[]>('/chat/sessions');
    return response.data;
  },

  async getSession(id: UUID): Promise<ChatSession> {
    const response = await apiClient.get<ChatSession>(`/chat/sessions/${id}`);
    return response.data;
  },

  async createSession(title?: string): Promise<ChatSession> {
    const response = await apiClient.post<ChatSession>('/chat/sessions', {
      title,
    });
    return response.data;
  },

  async sendMessage(
    sessionId: UUID,
    request: ChatSendRequest
  ): Promise<Message> {
    const response = await apiClient.post<Message>(
      `/chat/sessions/${sessionId}/messages`,
      request
    );
    return response.data;
  },

  async deleteSession(id: UUID): Promise<void> {
    await apiClient.delete(`/chat/sessions/${id}`);
  },
};
```

**Step 6: Commit**

```bash
git add frontend-web/src/services/
git commit -m "feat(web): add API client services"
```

---

### Task 5: WebSocket Service

**Files:**
- Create: `frontend-web/src/services/websocketService.ts`

**Step 1: Create WebSocket service with reconnection**

```typescript
// frontend-web/src/services/websocketService.ts
type EventHandler = (data: any) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private clientId: string | null = null;
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: number | null = null;

  constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    this.url = `${protocol}//${host}/ws`;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        resolve();
      };

      this.ws.onmessage = (event) => {
        const message = JSON.parse(event.data);

        // Handle connection message
        if (message.type === 'connection') {
          this.clientId = message.data.client_id;
          return;
        }

        // Handle pong
        if (message.type === 'pong') {
          return;
        }

        // Dispatch to registered handlers
        const handlers = this.handlers.get(message.type);
        if (handlers) {
          handlers.forEach((handler) => handler(message.data));
        }

        // Also dispatch to wildcard handlers
        const wildcardHandlers = this.handlers.get('*');
        if (wildcardHandlers) {
          wildcardHandlers.forEach((handler) => handler(message));
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.stopHeartbeat();
        this.attemptReconnect();
      };
    });
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  on(eventType: string, handler: EventHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.handlers.get(eventType)?.delete(handler);
    };
  }

  send(type: string, data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = window.setInterval(() => {
      this.send('ping', {});
    }, 30000); // 30 seconds
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(
      `Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms`
    );

    setTimeout(() => {
      this.connect().catch((error) => {
        console.error('Reconnection failed:', error);
      });
    }, delay);
  }

  getClientId(): string | null {
    return this.clientId;
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const websocketService = new WebSocketService();
```

**Step 2: Commit**

```bash
git add frontend-web/src/services/websocketService.ts
git commit -m "feat(web): add WebSocket service with auto-reconnect"
```

---

### Task 6: Zustand State Stores

**Files:**
- Create: `frontend-web/src/store/agentStore.ts`
- Create: `frontend-web/src/store/workflowStore.ts`
- Create: `frontend-web/src/store/documentStore.ts`
- Create: `frontend-web/src/store/chatStore.ts`
- Create: `frontend-web/src/store/uiStore.ts`
- Create: `frontend-web/src/store/index.ts`

**Step 1: Create agent store**

```typescript
// frontend-web/src/store/agentStore.ts
import { create } from 'zustand';
import { Agent } from '@/types/agent';
import { agentService } from '@/services/agentService';

interface AgentStore {
  agents: Agent[];
  loading: boolean;
  error: string | null;

  fetchAgents: () => Promise<void>;
  getAgent: (id: string) => Agent | undefined;
  updateAgent: (agent: Agent) => void;
  clearError: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  loading: false,
  error: null,

  fetchAgents: async () => {
    set({ loading: true, error: null });
    try {
      const agents = await agentService.list();
      set({ agents, loading: false });
    } catch (error: any) {
      set({ error: error.detail, loading: false });
    }
  },

  getAgent: (id: string) => {
    return get().agents.find((a) => a.id === id);
  },

  updateAgent: (agent: Agent) => {
    set((state) => ({
      agents: state.agents.map((a) => (a.id === agent.id ? agent : a)),
    }));
  },

  clearError: () => set({ error: null }),
}));
```

**Step 2: Create workflow store**

```typescript
// frontend-web/src/store/workflowStore.ts
import { create } from 'zustand';
import { Workflow } from '@/types/workflow';
import { workflowService } from '@/services/workflowService';

interface WorkflowStore {
  workflows: Workflow[];
  loading: boolean;
  error: string | null;

  fetchWorkflows: () => Promise<void>;
  getWorkflow: (id: string) => Workflow | undefined;
  updateWorkflow: (workflow: Workflow) => void;
  clearError: () => void;
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  workflows: [],
  loading: false,
  error: null,

  fetchWorkflows: async () => {
    set({ loading: true, error: null });
    try {
      const workflows = await workflowService.list();
      set({ workflows, loading: false });
    } catch (error: any) {
      set({ error: error.detail, loading: false });
    }
  },

  getWorkflow: (id: string) => {
    return get().workflows.find((w) => w.id === id);
  },

  updateWorkflow: (workflow: Workflow) => {
    set((state) => ({
      workflows: state.workflows.map((w) => (w.id === workflow.id ? workflow : w)),
    }));
  },

  clearError: () => set({ error: null }),
}));
```

**Step 3: Create document store**

```typescript
// frontend-web/src/store/documentStore.ts
import { create } from 'zustand';
import { Document } from '@/types/document';
import { documentService } from '@/services/documentService';

interface DocumentStore {
  documents: Document[];
  loading: boolean;
  error: string | null;

  fetchDocuments: () => Promise<void>;
  getDocument: (id: string) => Document | undefined;
  addDocument: (document: Document) => void;
  removeDocument: (id: string) => void;
  clearError: () => void;
}

export const useDocumentStore = create<DocumentStore>((set, get) => ({
  documents: [],
  loading: false,
  error: null,

  fetchDocuments: async () => {
    set({ loading: true, error: null });
    try {
      const documents = await documentService.list();
      set({ documents, loading: false });
    } catch (error: any) {
      set({ error: error.detail, loading: false });
    }
  },

  getDocument: (id: string) => {
    return get().documents.find((d) => d.id === id);
  },

  addDocument: (document: Document) => {
    set((state) => ({
      documents: [...state.documents, document],
    }));
  },

  removeDocument: (id: string) => {
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== id),
    }));
  },

  clearError: () => set({ error: null }),
}));
```

**Step 4: Create chat store**

```typescript
// frontend-web/src/store/chatStore.ts
import { create } from 'zustand';
import { ChatSession, Message } from '@/types/chat';
import { chatService } from '@/services/chatService';

interface ChatStore {
  sessions: ChatSession[];
  currentSessionId: string | null;
  loading: boolean;
  error: string | null;

  fetchSessions: () => Promise<void>;
  setCurrentSession: (id: string) => void;
  getCurrentSession: () => ChatSession | undefined;
  addMessage: (sessionId: string, message: Message) => void;
  clearError: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  loading: false,
  error: null,

  fetchSessions: async () => {
    set({ loading: true, error: null });
    try {
      const sessions = await chatService.listSessions();
      set({ sessions, loading: false });
    } catch (error: any) {
      set({ error: error.detail, loading: false });
    }
  },

  setCurrentSession: (id: string) => {
    set({ currentSessionId: id });
  },

  getCurrentSession: () => {
    const { sessions, currentSessionId } = get();
    return sessions.find((s) => s.id === currentSessionId);
  },

  addMessage: (sessionId: string, message: Message) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId
          ? { ...s, messages: [...s.messages, message] }
          : s
      ),
    }));
  },

  clearError: () => set({ error: null }),
}));
```

**Step 5: Create UI store**

```typescript
// frontend-web/src/store/uiStore.ts
import { create } from 'zustand';

interface Toast {
  id: string;
  title: string;
  description?: string;
  variant?: 'default' | 'destructive';
}

interface UIStore {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  toasts: Toast[];

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleTheme: () => void;
  setTheme: (theme: 'light' | 'dark') => void;
  showToast: (toast: Omit<Toast, 'id'>) => void;
  dismissToast: (id: string) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  theme: 'light',
  toasts: [],

  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (open: boolean) =>
    set({ sidebarOpen: open }),

  toggleTheme: () =>
    set((state) => {
      const newTheme = state.theme === 'light' ? 'dark' : 'light';
      document.documentElement.classList.toggle('dark');
      return { theme: newTheme };
    }),

  setTheme: (theme: 'light' | 'dark') => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    set({ theme });
  },

  showToast: (toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).substring(7);
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id }],
    }));

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id),
      }));
    }, 5000);
  },

  dismissToast: (id: string) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}));
```

**Step 6: Create store index**

```typescript
// frontend-web/src/store/index.ts
export { useAgentStore } from './agentStore';
export { useWorkflowStore } from './workflowStore';
export { useDocumentStore } from './documentStore';
export { useChatStore } from './chatStore';
export { useUIStore } from './uiStore';
```

**Step 7: Commit**

```bash
git add frontend-web/src/store/
git commit -m "feat(web): add Zustand state stores"
```

---

## Phase 2: shadcn/ui Components & Pages

### Task 7: Setup shadcn/ui CLI and Base Components

**Files:**
- Create: `frontend-web/components.json`
- Create: `frontend-web/src/lib/utils.ts`
- Create multiple shadcn components via CLI

**Step 1: Create components.json config**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "slate",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

**Step 2: Create utils**

```typescript
// frontend-web/src/lib/utils.ts
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

**Step 3: Install shadcn components**

```bash
npx shadcn-ui@latest add button
npx shadcn-ui@latest add card
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add input
npx shadcn-ui@latest add label
npx shadcn-ui@latest add select
npx shadcn-ui@latest add tabs
npx shadcn-ui@latest add toast
npx shadcn-ui@latest add tooltip
npx shadcn-ui@latest add scroll-area
npx shadcn-ui@latest add separator
npx shadcn-ui@latest add badge
```

**Step 4: Commit**

```bash
git add frontend-web/
git commit -m "feat(web): setup shadcn/ui with base components"
```

---

---

### Task 8: Layout Components

**Files:**
- Create: `frontend-web/src/components/layout/Layout.tsx`
- Create: `frontend-web/src/components/layout/Sidebar.tsx`
- Create: `frontend-web/src/components/layout/Header.tsx`

**Step 1: Create Layout component**

```tsx
// frontend-web/src/components/layout/Layout.tsx
import { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '@/store';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const sidebarOpen = useUIStore((state) => state.sidebarOpen);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

**Step 2: Create Sidebar component**

```tsx
// frontend-web/src/components/layout/Sidebar.tsx
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  Home,
  MessageSquare,
  Workflow,
  FileText,
  Bot,
  Settings,
} from 'lucide-react';
import { useUIStore } from '@/store';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';

const navigation = [
  { name: 'Home', href: '/', icon: Home },
  { name: 'Chat', href: '/chat', icon: MessageSquare },
  { name: 'Workflows', href: '/workflows', icon: Workflow },
  { name: 'Documents', href: '/documents', icon: FileText },
  { name: 'Agents', href: '/agents', icon: Bot },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const location = useLocation();
  const { sidebarOpen, setSidebarOpen } = useUIStore();

  if (!sidebarOpen) return null;

  return (
    <div className="flex w-64 flex-col border-r bg-card">
      <div className="flex h-16 items-center border-b px-6">
        <h1 className="text-xl font-bold">Amelia</h1>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <Separator />

      <div className="p-4">
        <p className="text-xs text-muted-foreground">
          Local LLM Orchestration
        </p>
      </div>
    </div>
  );
}
```

**Step 3: Create Header component**

```tsx
// frontend-web/src/components/layout/Header.tsx
import { Menu, Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useUIStore } from '@/store';

export function Header() {
  const { toggleSidebar, theme, toggleTheme } = useUIStore();

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <Button variant="ghost" size="icon" onClick={toggleSidebar}>
        <Menu className="h-5 w-5" />
      </Button>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={toggleTheme}>
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>
      </div>
    </header>
  );
}
```

**Step 4: Commit**

```bash
git add frontend-web/src/components/layout/
git commit -m "feat(web): add layout components (Sidebar, Header)"
```

---

### Task 9: Router Setup

**Files:**
- Create: `frontend-web/src/router.tsx`
- Create: `frontend-web/src/pages/Home.tsx`
- Create: `frontend-web/src/App.tsx`
- Create: `frontend-web/src/main.tsx`

**Step 1: Create placeholder pages**

```tsx
// frontend-web/src/pages/Home.tsx
export function Home() {
  return (
    <div>
      <h1 className="text-3xl font-bold">Home</h1>
      <p className="mt-2 text-muted-foreground">
        Welcome to Amelia - Local LLM Workflow Orchestration
      </p>
    </div>
  );
}
```

**Step 2: Create router configuration**

```tsx
// frontend-web/src/router.tsx
import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Home } from '@/pages/Home';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout><Home /></Layout>,
  },
  // More routes will be added in subsequent tasks
]);
```

**Step 3: Create App component**

```tsx
// frontend-web/src/App.tsx
import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { websocketService } from '@/services/websocketService';
import { Toaster } from '@/components/ui/toaster';

export function App() {
  useEffect(() => {
    // Connect WebSocket on mount
    websocketService.connect();

    return () => {
      // Disconnect on unmount
      websocketService.disconnect();
    };
  }, []);

  return (
    <>
      <RouterProvider router={router} />
      <Toaster />
    </>
  );
}
```

**Step 4: Create main entry point**

```tsx
// frontend-web/src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

**Step 5: Commit**

```bash
git add frontend-web/src/
git commit -m "feat(web): add router setup with React Router v7"
```

---

### Task 10: Chat Page with Streaming

**Files:**
- Create: `frontend-web/src/pages/Chat.tsx`
- Create: `frontend-web/src/components/chat/ChatInterface.tsx`
- Create: `frontend-web/src/components/chat/MessageList.tsx`
- Create: `frontend-web/src/components/chat/MessageInput.tsx`

**Step 1: Create MessageList component**

```tsx
// frontend-web/src/components/chat/MessageList.tsx
import { Message } from '@/types/chat';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface MessageListProps {
  messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <ScrollArea className="flex-1 p-4">
      <div className="space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'flex',
              message.role === 'user' ? 'justify-end' : 'justify-start'
            )}
          >
            <div
              className={cn(
                'max-w-[80%] rounded-lg px-4 py-2',
                message.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted'
              )}
            >
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              <p className="mt-1 text-xs opacity-70">
                {new Date(message.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
```

**Step 2: Create MessageInput component**

```tsx
// frontend-web/src/components/chat/MessageInput.tsx
import { useState, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send } from 'lucide-react';

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [message, setMessage] = useState('');

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message);
      setMessage('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t p-4">
      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message..."
          disabled={disabled}
          className="min-h-[80px]"
        />
        <Button onClick={handleSend} disabled={disabled || !message.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
```

**Step 3: Create ChatInterface component**

```tsx
// frontend-web/src/components/chat/ChatInterface.tsx
import { useEffect, useState } from 'react';
import { useChatStore } from '@/store';
import { chatService } from '@/services/chatService';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { Card } from '@/components/ui/card';

export function ChatInterface() {
  const { getCurrentSession, addMessage } = useChatStore();
  const [sending, setSending] = useState(false);
  const session = getCurrentSession();

  const handleSend = async (message: string) => {
    if (!session) return;

    setSending(true);
    try {
      // Add user message
      const userMessage = {
        id: crypto.randomUUID(),
        role: 'user' as const,
        content: message,
        timestamp: new Date().toISOString(),
      };
      addMessage(session.id, userMessage);

      // Send to backend and get response
      const response = await chatService.sendMessage(session.id, {
        message,
        stream: false,
      });

      // Add assistant message
      addMessage(session.id, response);
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setSending(false);
    }
  };

  if (!session) {
    return (
      <Card className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">
          No chat session selected
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex h-full flex-col">
      <div className="border-b p-4">
        <h2 className="font-semibold">{session.title}</h2>
      </div>
      <MessageList messages={session.messages} />
      <MessageInput onSend={handleSend} disabled={sending} />
    </Card>
  );
}
```

**Step 4: Create Chat page**

```tsx
// frontend-web/src/pages/Chat.tsx
import { useEffect } from 'react';
import { useChatStore } from '@/store';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { chatService } from '@/services/chatService';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';

export function Chat() {
  const { sessions, fetchSessions, setCurrentSession } = useChatStore();

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleCreateSession = async () => {
    const session = await chatService.createSession();
    setCurrentSession(session.id);
    fetchSessions();
  };

  return (
    <div className="h-full">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-3xl font-bold">Chat</h1>
        <Button onClick={handleCreateSession}>
          <Plus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
      </div>
      <ChatInterface />
    </div>
  );
}
```

**Step 5: Add Textarea component**

```bash
npx shadcn-ui@latest add textarea
```

**Step 6: Add chat route to router**

```tsx
// Update frontend-web/src/router.tsx
import { Chat } from '@/pages/Chat';

// Add to routes array:
{
  path: '/chat',
  element: <Layout><Chat /></Layout>,
}
```

**Step 7: Commit**

```bash
git add frontend-web/src/
git commit -m "feat(web): add chat page with message interface"
```

---

### Task 11: Workflows Page

**Files:**
- Create: `frontend-web/src/pages/Workflows.tsx`
- Create: `frontend-web/src/components/workflows/WorkflowList.tsx`
- Create: `frontend-web/src/components/workflows/WorkflowCard.tsx`

**Step 1: Create WorkflowCard component**

```tsx
// frontend-web/src/components/workflows/WorkflowCard.tsx
import { Workflow } from '@/types/workflow';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Play, Trash } from 'lucide-react';

interface WorkflowCardProps {
  workflow: Workflow;
  onExecute: (id: string) => void;
  onDelete: (id: string) => void;
}

export function WorkflowCard({ workflow, onExecute, onDelete }: WorkflowCardProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-blue-500';
      case 'completed':
        return 'bg-green-500';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{workflow.name}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {workflow.description}
            </p>
          </div>
          <Badge className={getStatusColor(workflow.status)}>
            {workflow.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {workflow.definition.nodes.length} nodes
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => onExecute(workflow.id)}
              disabled={workflow.status === 'running'}
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onDelete(workflow.id)}
            >
              <Trash className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Create WorkflowList component**

```tsx
// frontend-web/src/components/workflows/WorkflowList.tsx
import { Workflow } from '@/types/workflow';
import { WorkflowCard } from './WorkflowCard';

interface WorkflowListProps {
  workflows: Workflow[];
  onExecute: (id: string) => void;
  onDelete: (id: string) => void;
}

export function WorkflowList({ workflows, onExecute, onDelete }: WorkflowListProps) {
  if (workflows.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-muted-foreground">No workflows yet</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {workflows.map((workflow) => (
        <WorkflowCard
          key={workflow.id}
          workflow={workflow}
          onExecute={onExecute}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
```

**Step 3: Create Workflows page**

```tsx
// frontend-web/src/pages/Workflows.tsx
import { useEffect } from 'react';
import { useWorkflowStore, useUIStore } from '@/store';
import { workflowService } from '@/services/workflowService';
import { WorkflowList } from '@/components/workflows/WorkflowList';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';

export function Workflows() {
  const { workflows, fetchWorkflows } = useWorkflowStore();
  const { showToast } = useUIStore();

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  const handleExecute = async (id: string) => {
    try {
      await workflowService.execute(id, { input_data: {} });
      showToast({
        title: 'Workflow started',
        description: 'Workflow execution has begun',
      });
      fetchWorkflows();
    } catch (error: any) {
      showToast({
        title: 'Error',
        description: error.detail,
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await workflowService.delete(id);
      showToast({
        title: 'Workflow deleted',
      });
      fetchWorkflows();
    } catch (error: any) {
      showToast({
        title: 'Error',
        description: error.detail,
        variant: 'destructive',
      });
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">Workflows</h1>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Create Workflow
        </Button>
      </div>
      <WorkflowList
        workflows={workflows}
        onExecute={handleExecute}
        onDelete={handleDelete}
      />
    </div>
  );
}
```

**Step 4: Add toaster component**

```bash
npx shadcn-ui@latest add toaster
```

**Step 5: Add workflows route**

```tsx
// Update frontend-web/src/router.tsx
import { Workflows } from '@/pages/Workflows';

// Add to routes:
{
  path: '/workflows',
  element: <Layout><Workflows /></Layout>,
}
```

**Step 6: Commit**

```bash
git add frontend-web/src/
git commit -m "feat(web): add workflows page with list and controls"
```

---

## Phase 3: Terminal UI with Ink

### Task 12: Terminal UI Setup

**Files:**
- Create: `frontend-terminal/package.json`
- Create: `frontend-terminal/tsconfig.json`
- Create: `frontend-terminal/src/index.tsx`
- Create: `frontend-terminal/src/App.tsx`

**Step 1: Initialize terminal project**

```bash
mkdir -p frontend-terminal/src
cd frontend-terminal
npm init -y
```

**Step 2: Install dependencies**

```bash
npm install ink@5.0.0 react@19.2.0
npm install ink-text-input@6.0.0 ink-spinner@5.0.0 ink-select-input@6.2.0
npm install zustand@5.0.8 axios@1.13.2
npm install -D @types/react typescript tsx
```

**Step 3: Create package.json**

```json
{
  "name": "amelia-terminal",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/index.tsx",
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "bin": {
    "amelia-tui": "./dist/index.js"
  }
}
```

**Step 4: Create TypeScript config**

```json
// frontend-terminal/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "node",
    "jsx": "react",
    "jsxImportSource": "react",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

**Step 5: Create symlinks to shared code**

```bash
cd frontend-terminal
ln -s ../frontend-web/src/services ./src/services
ln -s ../frontend-web/src/types ./src/types
ln -s ../frontend-web/src/store ./src/store
```

**Step 6: Create main entry**

```tsx
// frontend-terminal/src/index.tsx
#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { App } from './App.js';

render(<App />);
```

**Step 7: Create App component**

```tsx
// frontend-terminal/src/App.tsx
import React, { useState } from 'react';
import { Box, Text } from 'ink';
import SelectInput from 'ink-select-input';

const items = [
  { label: 'Chat', value: 'chat' },
  { label: 'Workflows', value: 'workflows' },
  { label: 'Documents', value: 'documents' },
  { label: 'Agents', value: 'agents' },
  { label: 'Exit', value: 'exit' },
];

export function App() {
  const [view, setView] = useState<string>('menu');

  const handleSelect = (item: any) => {
    if (item.value === 'exit') {
      process.exit(0);
    }
    setView(item.value);
  };

  return (
    <Box flexDirection="column" padding={1}>
      <Box marginBottom={1}>
        <Text bold color="cyan">
          🤖 Amelia Terminal UI
        </Text>
      </Box>

      {view === 'menu' && (
        <SelectInput items={items} onSelect={handleSelect} />
      )}

      {view !== 'menu' && (
        <Box flexDirection="column">
          <Text>View: {view}</Text>
          <Text dimColor>Press Ctrl+C to return to menu</Text>
        </Box>
      )}
    </Box>
  );
}
```

**Step 8: Make executable**

```bash
chmod +x frontend-terminal/src/index.tsx
```

**Step 9: Commit**

```bash
git add frontend-terminal/
git commit -m "feat(terminal): add Ink terminal UI foundation"
```

---

## Phase 4: Integration & Scripts

### Task 13: WebSocket Event Handlers

**Files:**
- Create: `frontend-web/src/hooks/useWebSocketEvents.ts`

**Step 1: Create WebSocket events hook**

```tsx
// frontend-web/src/hooks/useWebSocketEvents.ts
import { useEffect } from 'react';
import { websocketService } from '@/services/websocketService';
import { useAgentStore, useWorkflowStore, useUIStore } from '@/store';

export function useWebSocketEvents() {
  const { updateAgent } = useAgentStore();
  const { updateWorkflow } = useWorkflowStore();
  const { showToast } = useUIStore();

  useEffect(() => {
    // Agent events
    const unsubAgentStarted = websocketService.on('agent.started', (data) => {
      showToast({
        title: 'Agent Started',
        description: `Agent ${data.agent_name} has started`,
      });
    });

    const unsubAgentCompleted = websocketService.on('agent.completed', (data) => {
      showToast({
        title: 'Agent Completed',
        description: `Agent ${data.agent_name} completed successfully`,
      });
      if (data.result) {
        updateAgent(data.result);
      }
    });

    const unsubAgentFailed = websocketService.on('agent.failed', (data) => {
      showToast({
        title: 'Agent Failed',
        description: `Agent ${data.agent_name} failed: ${data.error}`,
        variant: 'destructive',
      });
    });

    // Workflow events
    const unsubWorkflowStarted = websocketService.on('workflow.started', (data) => {
      showToast({
        title: 'Workflow Started',
        description: `Workflow execution has begun`,
      });
    });

    const unsubWorkflowProgress = websocketService.on('workflow.progress', (data) => {
      if (data.workflow) {
        updateWorkflow(data.workflow);
      }
    });

    const unsubWorkflowCompleted = websocketService.on('workflow.completed', (data) => {
      showToast({
        title: 'Workflow Completed',
        description: 'Workflow completed successfully',
      });
      if (data.workflow) {
        updateWorkflow(data.workflow);
      }
    });

    // Cleanup
    return () => {
      unsubAgentStarted();
      unsubAgentCompleted();
      unsubAgentFailed();
      unsubWorkflowStarted();
      unsubWorkflowProgress();
      unsubWorkflowCompleted();
    };
  }, [updateAgent, updateWorkflow, showToast]);
}
```

**Step 2: Use hook in App**

```tsx
// Update frontend-web/src/App.tsx
import { useWebSocketEvents } from '@/hooks/useWebSocketEvents';

export function App() {
  useWebSocketEvents(); // Add this

  // ... rest of component
}
```

**Step 3: Commit**

```bash
git add frontend-web/src/hooks/
git commit -m "feat(web): add WebSocket event handlers"
```

---

### Task 14: Build Scripts

**Files:**
- Create: `scripts/start-web.sh`
- Create: `scripts/start-tui.sh`
- Create: `scripts/build-all.sh`

**Step 1: Create web startup script**

```bash
#!/bin/bash
# scripts/start-web.sh
set -e

echo "🌐 Starting Amelia Web UI"

cd frontend-web
npm install
npm run dev
```

**Step 2: Create terminal startup script**

```bash
#!/bin/bash
# scripts/start-tui.sh
set -e

echo "💻 Starting Amelia Terminal UI"

cd frontend-terminal
npm install
npm run dev
```

**Step 3: Create build script**

```bash
#!/bin/bash
# scripts/build-all.sh
set -e

echo "🏗️  Building Amelia (Backend + Frontend)"

# Backend
echo "📦 Building backend..."
poetry install
poetry build

# Web UI
echo "🌐 Building web UI..."
cd frontend-web
npm install
npm run build
cd ..

# Terminal UI
echo "💻 Building terminal UI..."
cd frontend-terminal
npm install
npm run build
cd ..

echo "✅ Build complete!"
```

**Step 4: Make scripts executable**

```bash
chmod +x scripts/start-web.sh
chmod +x scripts/start-tui.sh
chmod +x scripts/build-all.sh
```

**Step 5: Commit**

```bash
git add scripts/
git commit -m "feat: add startup and build scripts"
```

---

## Plan Complete!

**Summary:**

✅ **Phase 1: Web UI Foundation** (Tasks 1-7)
- Vite + React 19 + TypeScript
- Tailwind CSS + shadcn/ui
- TypeScript types
- API services
- WebSocket service
- Zustand stores

✅ **Phase 2: Pages & Components** (Tasks 8-11)
- Layout (Sidebar, Header)
- React Router v7
- Chat page with streaming
- Workflows page

✅ **Phase 3: Terminal UI** (Task 12)
- Ink setup
- Shared services (symlinked)
- Menu navigation

✅ **Phase 4: Integration** (Tasks 13-14)
- WebSocket event handlers
- Build & startup scripts

**Execution Options:**

**1. Subagent-Driven Development (this session)**
- Use @superpowers:subagent-driven-development
- Fresh subagent per task
- Code review between tasks
- Fast iteration

**2. Parallel Session (separate worktree)**
- Open new session with @superpowers:executing-plans
- Batch execution with checkpoints
- Independent progress

Which approach would you like to use?
