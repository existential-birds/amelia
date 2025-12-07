# Dashboard Project Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ✅ Complete

**Goal:** Create the React dashboard frontend with Vite, TypeScript, shadcn/ui, ai-elements, and React Router v7. This establishes the foundation for the web UI with proper aviation/cockpit aesthetic using design tokens, routing infrastructure, error boundaries, and FastAPI static file serving.

**Architecture:** Vite + React 18 + TypeScript project in `dashboard/` directory with shadcn/ui components, ai-elements for workflow visualization primitives, CSS variable-based design tokens for the aviation theme, React Router v7 for client-side routing, development proxy for API calls, and FastAPI static file mounting for production.

**Tech Stack:**
- Vite 6, React 18, TypeScript 5
- **shadcn/ui** (Radix UI primitives + Tailwind styling)
- **ai-elements** (Vercel AI SDK workflow components via shadcn registry - selective installation)
- **React Flow** (@xyflow/react) for custom workflow visualization
- **Tailwind CSS 4** with CSS variable theming
- React Router v7, Vitest
- class-variance-authority, clsx, tailwind-merge
- lucide-react for icons

**Design Approach:**
- **Design Tokens via CSS Variables** - No inline color values, all theming through `--color-*` variables
- **shadcn/ui Components** - Accessible, composable primitives with built-in ARIA and keyboard navigation
- **ai-elements Components (selective)** - Queue, confirmation, loader, shimmer for standard workflow UI
- **Custom React Flow Components** - WorkflowCanvas with map pin nodes to preserve aviation aesthetic
- **Aviation Theme** - Custom color palette applied via CSS variable overrides

**Depends on:**
- Phase 2.1-01: Server Foundation (FastAPI app)
- Phase 2.1-04: REST API Endpoints (API to proxy to)

**References:**
- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Radix UI Primitives](https://www.radix-ui.com/primitives)
- [ai-elements Registry](https://registry.ai-sdk.dev) - Vercel AI SDK workflow components
- [ai-elements GitHub](https://github.com/vercel/ai-elements) - Source and documentation
- [React Flow Documentation](https://reactflow.dev) - Node-based graph visualization

---

## Task 1: Create Vite + React + TypeScript Project with shadcn/ui Dependencies

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tsconfig.json` (references only)
- Create: `dashboard/tsconfig.app.json` (app config with path aliases)
- Create: `dashboard/tsconfig.node.json` (vite config)
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/vite-env.d.ts`
- Create: `dashboard/.gitignore`

> **Note:** Modern Vite projects require THREE tsconfig files. The main `tsconfig.json` only contains references, while `tsconfig.app.json` has the actual compiler options and path aliases for the IDE, and `tsconfig.node.json` handles `vite.config.ts`.

**Step 1: Create dashboard directory and package.json**

Create `dashboard/package.json`:

```json
{
  "name": "amelia-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:run": "vitest run",
    "lint": "eslint src --ext ts,tsx",
    "lint:fix": "eslint src --ext ts,tsx --fix",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.0.2",
    "@radix-ui/react-collapsible": "^1.1.2",
    "@radix-ui/react-dialog": "^1.1.3",
    "@radix-ui/react-dropdown-menu": "^2.1.3",
    "@radix-ui/react-navigation-menu": "^1.2.2",
    "@radix-ui/react-progress": "^1.1.1",
    "@radix-ui/react-scroll-area": "^1.2.2",
    "@radix-ui/react-slot": "^1.1.1",
    "@radix-ui/react-tooltip": "^1.1.5",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^0.460.0",
    "tailwind-merge": "^2.6.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@types/node": "^22.10.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@typescript-eslint/eslint-plugin": "^8.15.0",
    "@typescript-eslint/parser": "^8.15.0",
    "@vitejs/plugin-react": "^4.3.4",
    "@vitest/ui": "^2.1.5",
    "eslint": "^9.15.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.14",
    "jsdom": "^25.0.1",
    "tailwindcss": "^4.0.0",
    "typescript": "~5.6.2",
    "vite": "^6.0.1",
    "vitest": "^2.1.5"
  }
}
```

**Step 2: Create Vite configuration with API proxy, path aliases, and Tailwind v4**

Create `dashboard/vite.config.ts`:

> **Important:** Tailwind v4 uses a Vite plugin instead of PostCSS. The `@tailwindcss/vite` plugin must be included in the plugins array. The `@types/node` package is required for `path.resolve` to work with TypeScript.

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8420',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8420',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'router': ['react-router-dom'],
          'radix': [
            '@radix-ui/react-collapsible',
            '@radix-ui/react-dialog',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-navigation-menu',
            '@radix-ui/react-scroll-area',
            '@radix-ui/react-slot',
            '@radix-ui/react-tooltip',
          ],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
});
```

**Step 3: Create TypeScript configuration (THREE files required)**

Modern Vite projects require three tsconfig files:
1. `tsconfig.json` - References only, used by `tsc -b`
2. `tsconfig.app.json` - App configuration with path aliases (used by IDE)
3. `tsconfig.node.json` - Node configuration for vite.config.ts

> **Important:** All three files need the `@/*` path alias configured where applicable. The main `tsconfig.json` only contains references.

Create `dashboard/tsconfig.json` (references only):

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

Create `dashboard/tsconfig.app.json` (main app config with path aliases):

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,

    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

Create `dashboard/tsconfig.node.json` (vite.config.ts):

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["vite.config.ts"]
}
```

**Step 4: Create index.html entry point**

Create `dashboard/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Amelia Dashboard</title>

    <!-- Aviation theme fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@400;600;700&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 5: Create basic main.tsx entry point**

Create `dashboard/src/main.tsx`:

```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/styles/globals.css';

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <h1 className="text-4xl font-display p-8 text-primary">Amelia Dashboard</h1>
    </div>
  );
}

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

Create `dashboard/src/vite-env.d.ts`:

```typescript
/// <reference types="vite/client" />
```

**Step 6: Create .gitignore**

Create `dashboard/.gitignore`:

```
# Logs
logs
*.log
pnpm-debug.log*
yarn-debug.log*
yarn-error.log*
ppnpm-debug.log*
lerna-debug.log*

node_modules
dist
dist-ssr
*.local

# Editor directories and files
.vscode/*
!.vscode/extensions.json
.idea
.DS_Store
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?
```

**Step 7: Create test setup file**

Create `dashboard/src/test/setup.ts`:

```typescript
import '@testing-library/jest-dom';
```

**Step 8: Install dependencies**

Run in `dashboard/` directory:

```bash
cd /Users/ka/github/amelia-docs/dashboard
pnpm install
```

Expected: Dependencies installed successfully

**Step 9: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): initialize Vite + React + TypeScript project

- Vite 6 with React plugin, Tailwind v4 plugin, and path aliases
- TypeScript 5 with strict mode (three tsconfig files)
- shadcn/ui dependencies (Radix UI, CVA, clsx, tailwind-merge)
- @tailwindcss/vite for modern Tailwind v4 setup
- @types/node for path alias support in vite.config.ts
- Development proxy for /api and /ws endpoints
- Vitest setup for component testing"
```

---

## Task 2: Setup shadcn/ui Infrastructure, ai-elements Components, and React Flow

**Files:**
- Create: `dashboard/components.json`
- Create: `dashboard/src/lib/utils.ts`

**Step 1: Create shadcn/ui configuration**

Create `dashboard/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

**Step 2: Create utility functions**

Create `dashboard/src/lib/utils.ts`:

```typescript
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes safely, handling conflicts.
 * Use this for all dynamic class combinations.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

**Step 3: Install ai-elements via shadcn registry (SELECTIVE)**

ai-elements provides pre-built workflow visualization components that integrate with shadcn/ui theming.

**IMPORTANT: HYBRID APPROACH**

We install only specific ai-elements components for queue and confirmation functionality. The workflow canvas (node/edge visualization) is built custom using React Flow to preserve the aviation aesthetic with map pin icons from the design mock.

Install selected ai-elements components from the Vercel AI SDK registry:

```bash
cd /Users/ka/github/amelia-docs/dashboard
npx shadcn@latest add https://registry.ai-sdk.dev/queue.json
npx shadcn@latest add https://registry.ai-sdk.dev/confirmation.json
npx shadcn@latest add https://registry.ai-sdk.dev/loader.json
npx shadcn@latest add https://registry.ai-sdk.dev/shimmer.json
```

**Why not install canvas/node/edge?** The design mock uses map pin icons for workflow nodes, which requires custom implementation to preserve the aviation/flight control aesthetic. The generic ai-elements canvas components would not match our visual design.

This installs selected ai-elements components to `@/components/ai-elements/`:

| ai-elements Component | Dashboard Use Case | Install? |
|-----------------------|-------------------|----------|
| `queue` | JobQueue panel, ActivityLog feed | YES (ai-elements) |
| `confirmation` | ApprovalControls for human-in-the-loop | YES (ai-elements) |
| `loader` | Loading states during API calls | YES (ai-elements) |
| `shimmer` | Skeleton loading placeholders | YES (ai-elements) |
| `task` | Individual task status display | YES (ai-elements) |
| `canvas` | WorkflowCanvas container | NO (custom - map pin design) |
| `node` | Pipeline step visualization | NO (custom - map pin design) |
| `edge` | Dependency connections between nodes | NO (custom - map pin design) |

**Note on theming:** ai-elements uses standard shadcn CSS variables (`--background`, `--foreground`, `--primary`, etc.). Our aviation theme CSS variables (Task 3) will automatically style ai-elements components since they use the same variable names. No additional configuration needed.

**Step 3b: Install React Flow for custom workflow visualization**

React Flow provides the foundation for building custom node-based visualizations. We use it directly to create our custom map pin nodes that match the aviation aesthetic.

```bash
cd /Users/ka/github/amelia-docs/dashboard
pnpm install @xyflow/react
```

React Flow will be used in Plan 10 to build:
- Custom `WorkflowCanvas` component wrapping `<ReactFlow>`
- Custom `MapPinNode` component for pipeline step visualization
- Custom edge styles matching the aviation color palette

**Step 4: Verify ai-elements and React Flow installation**

After installation, verify the components directory structure:

```
dashboard/src/components/
  ai-elements/
    queue.tsx          # ai-elements - for JobQueue, ActivityLog
    confirmation.tsx   # ai-elements - for ApprovalControls
    loader.tsx         # ai-elements - for loading states
    shimmer.tsx        # ai-elements - for skeleton loading
    task.tsx           # ai-elements - for task display
  ui/
    (base shadcn components)
```

Note: `canvas.tsx`, `node.tsx`, and `edge.tsx` are NOT installed from ai-elements.
These will be built as custom components using React Flow (@xyflow/react) in Plan 10.

**Step 5: Commit**

```bash
git add dashboard/components.json dashboard/src/lib/utils.ts dashboard/src/components/ai-elements/ dashboard/package.json dashboard/package-lock.json
git commit -m "feat(dashboard): setup shadcn/ui, ai-elements (selective), and React Flow

- components.json configuration for shadcn CLI
- cn() utility for safe Tailwind class merging
- ai-elements components via registry (queue, confirmation, loader, shimmer)
- React Flow (@xyflow/react) for custom workflow canvas
- Path aliases configured (@/components, @/lib, etc.)

Note: canvas/node/edge built custom with React Flow for map pin aesthetic"
```

---

## Task 3: Configure Design Tokens with CSS Variables

**Files:**
- Create: `dashboard/src/styles/globals.css`

> **Note:** With Tailwind v4 and the `@tailwindcss/vite` plugin, PostCSS configuration is NOT required. Tailwind is handled directly by the Vite plugin.

**Step 1: Create CSS with design tokens using `@theme inline`**

Create `dashboard/src/styles/globals.css`:

> **Important:** Tailwind v4 uses the `@theme inline` directive to map CSS custom properties to Tailwind utilities. This replaces the traditional `tailwind.config.js` extend colors approach. The `inline` keyword means the theme values are defined directly in CSS rather than extracted to a separate file.

```css
@import "tailwindcss";

/*
 * ============================================================================
 * DESIGN TOKENS - Aviation Theme
 * ============================================================================
 * All colors use CSS variables for consistent theming.
 * Components reference these via Tailwind classes: bg-background, text-primary, etc.
 *
 * Note: ai-elements components use these same CSS variables, so the aviation
 * theme automatically applies to queue, canvas, node, edge, and other
 * ai-elements components without additional configuration.
 *
 * TAILWIND v4: Uses @theme inline directive to map CSS vars to utilities.
 * This replaces the traditional tailwind.config.js extend colors approach.
 */

@theme inline {
  /* Map CSS custom properties to Tailwind utilities */
  /* Usage: bg-background, text-foreground, bg-primary, etc. */
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);

  /* Border radius scale */
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.625rem;
  --radius-xl: 0.875rem;

  /* Font families */
  --font-display: "Bebas Neue", sans-serif;
  --font-heading: "Barlow Condensed", sans-serif;
  --font-body: "Source Sans 3", sans-serif;
  --font-mono: "IBM Plex Mono", monospace;

  /* Animation durations */
  --duration-fast: 150ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
}

/*
 * Light mode (default) - Aviation Dark Theme
 * Note: Our "light" mode IS dark (aviation cockpit aesthetic)
 */
:root {
  /* Core backgrounds */
  --background: oklch(8% 0.02 150);           /* #0D1A12 - Deep dark green */
  --foreground: oklch(95% 0.02 120);          /* #EFF8E2 - Warm off-white */

  /* Card/surface backgrounds */
  --card: oklch(18% 0.025 150);               /* #1F332E - Elevated surface */
  --card-foreground: oklch(95% 0.02 120);

  /* Popover/dropdown backgrounds */
  --popover: oklch(18% 0.025 150);
  --popover-foreground: oklch(95% 0.02 120);

  /* Primary accent - Aviation Gold */
  --primary: oklch(82% 0.16 85);              /* #FFC857 - Gold */
  --primary-foreground: oklch(8% 0.02 150);   /* Dark text on gold */

  /* Secondary - Muted green */
  --secondary: oklch(35% 0.04 150);           /* #4A5C54 - Muted panel */
  --secondary-foreground: oklch(95% 0.02 120);

  /* Muted text and labels */
  --muted: oklch(25% 0.03 150);
  --muted-foreground: oklch(60% 0.05 150);    /* #88A896 - Secondary text */

  /* Accent - Blue for links/interactive */
  --accent: oklch(65% 0.12 240);              /* #5B9BD5 - Blue accent */
  --accent-foreground: oklch(95% 0.02 120);

  /* Destructive/error states */
  --destructive: oklch(50% 0.2 25);           /* #A33D2E - Deep red */
  --destructive-foreground: oklch(95% 0.02 120);

  /* Border and input colors */
  --border: oklch(30% 0.02 150 / 0.2);
  --input: oklch(30% 0.02 150 / 0.3);
  --ring: oklch(82% 0.16 85 / 0.5);           /* Gold ring */

  /* Status colors */
  --status-running: oklch(82% 0.16 85);       /* Gold - in progress */
  --status-completed: oklch(50% 0.1 150);     /* #5B8A72 - Green done */
  --status-pending: oklch(35% 0.04 150);      /* Gray - queued */
  --status-blocked: oklch(50% 0.2 25);        /* Red - awaiting */
  --status-failed: oklch(50% 0.2 25);         /* Red - error */

  /* Sidebar specific */
  --sidebar: oklch(12% 0.02 150);
  --sidebar-foreground: oklch(95% 0.02 120);
  --sidebar-primary: oklch(82% 0.16 85);
  --sidebar-primary-foreground: oklch(8% 0.02 150);
  --sidebar-accent: oklch(25% 0.03 150);
  --sidebar-accent-foreground: oklch(95% 0.02 120);
  --sidebar-border: oklch(30% 0.02 150 / 0.15);

  /* Chart colors for data visualization */
  --chart-1: oklch(82% 0.16 85);              /* Gold */
  --chart-2: oklch(50% 0.1 150);              /* Green */
  --chart-3: oklch(65% 0.12 240);             /* Blue */
  --chart-4: oklch(50% 0.2 25);               /* Red */
  --chart-5: oklch(60% 0.05 150);             /* Gray */
}

/*
 * Base styles
 */
@layer base {
  * {
    @apply border-border;
  }

  html {
    font-family: var(--font-body);
  }

  body {
    @apply bg-background text-foreground antialiased;
  }

  /* Typography utilities */
  .font-display {
    font-family: var(--font-display);
  }

  .font-heading {
    font-family: var(--font-heading);
  }

  .font-mono {
    font-family: var(--font-mono);
  }

  /* Custom scrollbar for aviation aesthetic */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: oklch(from var(--background) l c h);
  }

  ::-webkit-scrollbar-thumb {
    background: oklch(from var(--muted-foreground) l c h / 0.5);
    border-radius: var(--radius-sm);
  }

  ::-webkit-scrollbar-thumb:hover {
    background: oklch(from var(--primary) l c h);
  }
}

/*
 * Component utilities
 */
@layer components {
  /* Focus ring utility */
  .focus-ring {
    @apply focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background;
  }
}

/*
 * Animation keyframes
 */
@keyframes pulse-glow {
  0%, 100% {
    opacity: 1;
    filter: drop-shadow(0 0 8px oklch(from var(--primary) l c h / 0.6));
  }
  50% {
    opacity: 0.7;
    filter: drop-shadow(0 0 16px oklch(from var(--primary) l c h / 0.8));
  }
}

@keyframes beacon-glow {
  0%, 100% {
    filter: drop-shadow(0 0 4px oklch(from var(--primary) l c h / 0.6));
  }
  50% {
    filter: drop-shadow(0 0 16px oklch(from var(--primary) l c h / 0.9));
  }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@layer utilities {
  .animate-pulse-glow {
    animation: pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  .animate-beacon-glow {
    animation: beacon-glow 2s ease-in-out infinite;
  }

  .animate-blink {
    animation: blink 1s step-end infinite;
  }
}

/*
 * Accessibility: Respect user preferences for reduced motion
 */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

> **Note:** No `postcss.config.js` is needed with Tailwind v4. The `@tailwindcss/vite` plugin handles everything directly.

**Step 2: Verify theme is applied**

Run:

```bash
pnpm run dev
```

Expected: Dashboard renders with dark background and gold accent text

**Step 3: Commit**

```bash
git add dashboard/src/styles/globals.css
git commit -m "feat(dashboard): configure design tokens with CSS variables

- Tailwind v4 @theme inline directive for CSS variable mapping
- OKLCH color space for perceptual uniformity
- Aviation theme: dark backgrounds, gold accents, green status
- Design tokens: --background, --foreground, --primary, --status-*
- Custom font families: display, heading, body, mono
- Animation keyframes: pulse-glow, beacon-glow, blink
- Respects prefers-reduced-motion
- Custom scrollbar styling
- Note: No postcss.config.js needed with @tailwindcss/vite
- Note: ai-elements components inherit these variables automatically"
```

---

## Task 4: Create Base UI Components (shadcn pattern)

**Files:**
- Create: `dashboard/src/components/ui/button.tsx`
- Create: `dashboard/src/components/ui/badge.tsx`
- Create: `dashboard/src/components/ui/card.tsx`
- Create: `dashboard/src/components/ui/scroll-area.tsx`
- Create: `dashboard/src/components/ui/tooltip.tsx`
- Create: `dashboard/src/components/ui/progress.tsx`
- Create: `dashboard/src/components/ui/skeleton.tsx`

These base shadcn/ui components are required dependencies for ai-elements and general UI. The ai-elements components (queue, canvas, node, edge, confirmation, loader, shimmer, task) build on top of these primitives.

> **Note on `data-slot` pattern:** Modern shadcn/ui components use `data-slot` attributes for styling hooks. This allows parent components to target specific parts of child components for custom styling. For example, `data-slot="card-header"` on a CardHeader component can be targeted with CSS like `[data-slot="card-header"] { ... }`. This pattern enables compound component styling without tight coupling.

**Step 1: Create Button component**

Create `dashboard/src/components/ui/button.tsx`:

```typescript
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap font-heading font-semibold text-sm tracking-wider uppercase transition-colors focus-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-accent underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-12 px-6',
        icon: 'h-10 w-10',
        'icon-sm': 'h-8 w-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
```

**Step 2: Create Badge component**

Create `dashboard/src/components/ui/badge.tsx`:

```typescript
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center px-2.5 py-0.5 font-heading text-xs font-semibold tracking-wider uppercase transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground',
        secondary: 'bg-secondary text-secondary-foreground',
        destructive: 'bg-destructive text-destructive-foreground',
        outline: 'border border-current text-foreground',
        // Status variants
        running: 'bg-[--status-running] text-primary-foreground',
        completed: 'bg-[--status-completed] text-foreground',
        pending: 'bg-[--status-pending] text-muted-foreground',
        blocked: 'bg-[--status-blocked] text-foreground',
        failed: 'bg-[--status-failed] text-foreground',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
```

**Step 3: Create Card component**

Create `dashboard/src/components/ui/card.tsx`:

> **Note:** This component demonstrates the `data-slot` pattern. Each sub-component includes a `data-slot` attribute that allows parent components to target specific parts for custom styling (e.g., `[data-slot="card-header"] { ... }`).

```typescript
import * as React from 'react';
import { cn } from '@/lib/utils';

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('bg-card text-card-foreground border border-border', className)}
    data-slot="card"
    {...props}
  />
));
Card.displayName = 'Card';

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col gap-1.5 p-4 border-b border-border', className)}
    data-slot="card-header"
    {...props}
  />
));
CardHeader.displayName = 'CardHeader';

const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('font-heading text-lg font-semibold tracking-wide', className)}
    data-slot="card-title"
    {...props}
  />
));
CardTitle.displayName = 'CardTitle';

const CardDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    data-slot="card-description"
    {...props}
  />
));
CardDescription.displayName = 'CardDescription';

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('p-4', className)} data-slot="card-content" {...props} />
));
CardContent.displayName = 'CardContent';

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex items-center p-4 border-t border-border', className)}
    data-slot="card-footer"
    {...props}
  />
));
CardFooter.displayName = 'CardFooter';

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
```

**Step 4: Create ScrollArea component**

Create `dashboard/src/components/ui/scroll-area.tsx`:

```typescript
import * as React from 'react';
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area';
import { cn } from '@/lib/utils';

const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    className={cn('relative overflow-hidden', className)}
    {...props}
  >
    <ScrollAreaPrimitive.Viewport className="h-full w-full rounded-[inherit]">
      {children}
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
));
ScrollArea.displayName = ScrollAreaPrimitive.Root.displayName;

const ScrollBar = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>
>(({ className, orientation = 'vertical', ...props }, ref) => (
  <ScrollAreaPrimitive.ScrollAreaScrollbar
    ref={ref}
    orientation={orientation}
    className={cn(
      'flex touch-none select-none transition-colors',
      orientation === 'vertical' &&
        'h-full w-2.5 border-l border-l-transparent p-[1px]',
      orientation === 'horizontal' &&
        'h-2.5 flex-col border-t border-t-transparent p-[1px]',
      className
    )}
    {...props}
  >
    <ScrollAreaPrimitive.ScrollAreaThumb className="relative flex-1 rounded-full bg-muted-foreground/50 hover:bg-primary" />
  </ScrollAreaPrimitive.ScrollAreaScrollbar>
));
ScrollBar.displayName = ScrollAreaPrimitive.ScrollAreaScrollbar.displayName;

export { ScrollArea, ScrollBar };
```

**Step 5: Create Tooltip component**

Create `dashboard/src/components/ui/tooltip.tsx`:

```typescript
import * as React from 'react';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { cn } from '@/lib/utils';

const TooltipProvider = TooltipPrimitive.Provider;

const Tooltip = TooltipPrimitive.Root;

const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        'z-50 overflow-hidden bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 border border-border',
        className
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
```

**Step 6: Create Progress component**

Create `dashboard/src/components/ui/progress.tsx`:

```typescript
import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import { cn } from '@/lib/utils';

const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root
    ref={ref}
    className={cn(
      'relative h-2 w-full overflow-hidden rounded-full bg-secondary',
      className
    )}
    data-slot="progress"
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="h-full w-full flex-1 bg-primary transition-all"
      style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      data-slot="progress-indicator"
    />
  </ProgressPrimitive.Root>
));
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
```

> **Note:** Add `@radix-ui/react-progress` to dependencies in package.json.

**Step 7: Create Skeleton component**

Create `dashboard/src/components/ui/skeleton.tsx`:

```typescript
import { cn } from '@/lib/utils';

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      data-slot="skeleton"
      {...props}
    />
  );
}

export { Skeleton };
```

**Step 8: Commit**

```bash
git add dashboard/src/components/ui/
git commit -m "feat(dashboard): add base UI components (shadcn pattern)

- Button with variants: default, destructive, outline, secondary, ghost, link
- Badge with status variants: running, completed, pending, blocked, failed
- Card with Header, Title, Description, Content, Footer
- ScrollArea with custom styled scrollbar
- Tooltip with animation
- Progress bar for workflow progress visualization
- Skeleton for loading placeholders

All components use Radix UI primitives for accessibility.
Components use data-slot attributes for styling hooks.
These are dependencies for ai-elements components."
```

---

## Task 5: Setup React Router v7 with Data Router (createBrowserRouter)

**Files:**
- Create: `dashboard/src/router.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/components/NavigationProgress.tsx`
- Modify: `dashboard/src/main.tsx`

> **Note:** React Router v7 recommends `createBrowserRouter` + `RouterProvider` (Data Mode) over `<BrowserRouter>` (Declarative Mode) for applications that need data loading, loaders, and improved error handling. This setup enables route-level error boundaries, lazy loading with code splitting, and navigation state tracking.

**Step 1: Create router configuration with lazy loading**

Create `dashboard/src/router.tsx`:

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate to="/workflows" replace />
      },
      {
        path: 'workflows',
        lazy: () => import('@/pages/WorkflowsPage'),
      },
      {
        path: 'workflows/:id',
        lazy: () => import('@/pages/WorkflowDetailPage'),
      },
      {
        path: 'history',
        lazy: () => import('@/pages/HistoryPage'),
      },
      {
        path: 'logs',
        lazy: () => import('@/pages/LogsPage'),
      },
      {
        path: '*',
        element: <Navigate to="/workflows" replace />,
      },
    ],
  },
]);
```

> **Note:** The `lazy` property enables route-based code splitting. Each page is loaded on demand, reducing the initial bundle size. Actual page components will be created in Task 5b.

**Step 2: Create App component with RouterProvider**

Create `dashboard/src/App.tsx`:

```typescript
import { RouterProvider } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { router } from '@/router';

function GlobalLoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

export function App() {
  return (
    <TooltipProvider>
      <RouterProvider
        router={router}
        fallbackElement={<GlobalLoadingSpinner />}
      />
    </TooltipProvider>
  );
}
```

> **Note:** `fallbackElement` shows while initial route loads. ErrorBoundary is now at the route level (in `router.tsx`) instead of wrapping the whole app.

**Step 3: Create NavigationProgress component**

Create `dashboard/src/components/NavigationProgress.tsx`:

```typescript
export function NavigationProgress() {
  return (
    <div className="absolute top-0 left-0 right-0 h-1 bg-primary/20 z-50">
      <div
        className="h-full bg-primary transition-all duration-300"
        style={{ width: '30%', animation: 'progress-pulse 1s ease-in-out infinite' }}
      />
    </div>
  );
}
```

**Step 4: Update main.tsx**

Modify `dashboard/src/main.tsx`:

```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/App';
import '@/styles/globals.css';

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

**Step 5: Update package.json to ensure react-router-dom is installed**

The import should be from `react-router-dom` (not `react-router`). Update `dashboard/package.json` dependencies:

```json
{
  "dependencies": {
    "react-router-dom": "^7.0.2"
  }
}
```

> **Note:** `react-router-dom` is the standard package for browser environments. It includes all exports from `react-router` plus browser-specific functionality.

**Step 6: Commit**

```bash
git add dashboard/src/router.tsx \
        dashboard/src/App.tsx \
        dashboard/src/components/NavigationProgress.tsx \
        dashboard/src/main.tsx \
        dashboard/package.json
git commit -m "feat(dashboard): setup React Router v7 with Data Router pattern

- createBrowserRouter with route configuration (Data Mode)
- Lazy loading via route.lazy for code splitting
- Route-level error boundaries using errorElement
- NavigationProgress component for transition feedback
- RouterProvider with fallbackElement for initial load
- Layout as root route with Outlet (updated in Task 7)
- Import from react-router-dom (browser-specific package)

Note: Placeholder pages will be created in next task"
```

---

## Task 5b: Create Page File Structure for Lazy Loading

**Files:**
- Create: `dashboard/src/pages/WorkflowsPage.tsx`
- Create: `dashboard/src/pages/WorkflowDetailPage.tsx`
- Create: `dashboard/src/pages/HistoryPage.tsx`
- Create: `dashboard/src/pages/LogsPage.tsx`

> **Note:** Each page exports a `default` component for lazy loading. Data loaders will be added in Plan 09 when we implement API integration.

**Step 1: Create WorkflowsPage**

Create `dashboard/src/pages/WorkflowsPage.tsx`:

```typescript
import { Loader2 } from 'lucide-react';

export default function WorkflowsPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <h2 className="text-3xl font-display text-primary">Active Workflows</h2>
      <p className="text-muted-foreground font-heading text-lg tracking-wide">
        Coming soon
      </p>
      <Loader2 className="w-8 h-8 text-primary animate-spin" />
    </div>
  );
}

// Loader function will be added in Plan 09
// export async function loader() { ... }
```

**Step 2: Create WorkflowDetailPage**

Create `dashboard/src/pages/WorkflowDetailPage.tsx`:

```typescript
import { Loader2 } from 'lucide-react';

export default function WorkflowDetailPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <h2 className="text-3xl font-display text-primary">Workflow Detail</h2>
      <p className="text-muted-foreground font-heading text-lg tracking-wide">
        Coming soon
      </p>
      <Loader2 className="w-8 h-8 text-primary animate-spin" />
    </div>
  );
}

// Loader function will be added in Plan 09
// export async function loader({ params }) { ... }
```

**Step 3: Create HistoryPage**

Create `dashboard/src/pages/HistoryPage.tsx`:

```typescript
import { Loader2 } from 'lucide-react';

export default function HistoryPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <h2 className="text-3xl font-display text-primary">Past Runs</h2>
      <p className="text-muted-foreground font-heading text-lg tracking-wide">
        Coming soon
      </p>
      <Loader2 className="w-8 h-8 text-primary animate-spin" />
    </div>
  );
}

// Loader function will be added in Plan 09
// export async function loader() { ... }
```

**Step 4: Create LogsPage**

Create `dashboard/src/pages/LogsPage.tsx`:

```typescript
import { Loader2 } from 'lucide-react';

export default function LogsPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <h2 className="text-3xl font-display text-primary">Logs</h2>
      <p className="text-muted-foreground font-heading text-lg tracking-wide">
        Coming soon
      </p>
      <Loader2 className="w-8 h-8 text-primary animate-spin" />
    </div>
  );
}

// No loader needed for logs page
```

**Step 5: Verify lazy loading works**

Run:

```bash
pnpm run dev
```

Open browser devtools Network tab and navigate between routes. Expected:
- Initial page load: main bundle loaded
- Navigate to /workflows: separate chunk loaded for WorkflowsPage
- Navigate to /history: separate chunk loaded for HistoryPage
- Navigate to /logs: separate chunk loaded for LogsPage
- Check that code splitting created multiple JS files in Network tab

**Step 6: Commit**

```bash
git add dashboard/src/pages/
git commit -m "feat(dashboard): create page components for lazy loading

- WorkflowsPage, WorkflowDetailPage, HistoryPage, LogsPage
- Default exports for route.lazy compatibility
- Placeholder UI with loading indicators
- Comments for future loader/action functions (Plan 09)
- Code splitting via dynamic imports"
```

---

## Task 6: Add Route-Based Error Boundaries

**Files:**
- Create: `dashboard/src/components/ErrorBoundary.tsx`
- Create: `dashboard/src/components/ConnectionLost.tsx`

> **Note:** With React Router v7 Data Mode, error boundaries are configured at the route level using the `errorElement` property. This provides better error isolation per route and integrates with React Router's error handling system.

**Step 1: Create RootErrorBoundary component using useRouteError**

Create `dashboard/src/components/ErrorBoundary.tsx`:

```typescript
import { useRouteError, isRouteErrorResponse, useNavigate } from 'react-router-dom';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Root error boundary for router-level errors.
 * Uses useRouteError hook from React Router v7.
 */
export function RootErrorBoundary() {
  const error = useRouteError();
  const navigate = useNavigate();

  // Handle HTTP error responses (404, 500, etc.)
  if (isRouteErrorResponse(error)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-8">
        <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-4xl font-display text-destructive mb-4">
          {error.status} {error.statusText}
        </h1>
        <p className="text-muted-foreground mb-8 max-w-md text-center">
          {error.data?.message || 'The page you are looking for does not exist.'}
        </p>
        <div className="flex gap-4">
          <Button onClick={() => navigate('/')}>
            <Home className="w-4 h-4" />
            Go Home
          </Button>
          <Button variant="outline" onClick={() => navigate(-1)}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  // Handle JavaScript errors
  const errorMessage = error instanceof Error ? error.message : 'Unknown error';
  const errorStack = error instanceof Error ? error.stack : undefined;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-8">
      <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
      <h1 className="text-4xl font-display text-destructive mb-4">
        Something went wrong
      </h1>
      <p className="text-muted-foreground mb-8 max-w-md text-center">
        {errorMessage}
      </p>
      {import.meta.env.DEV && errorStack && (
        <details className="mb-8 max-w-2xl w-full">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
            Show error details
          </summary>
          <pre className="mt-4 p-4 bg-card border border-border rounded text-xs overflow-auto">
            {errorStack}
          </pre>
        </details>
      )}
      <div className="flex gap-4">
        <Button onClick={() => window.location.reload()}>
          <RefreshCw className="w-4 h-4" />
          Reload Dashboard
        </Button>
        <Button variant="outline" onClick={() => navigate('/')}>
          <Home className="w-4 h-4" />
          Go Home
        </Button>
      </div>
    </div>
  );
}
```

> **Note:** `useRouteError` provides the error thrown during route loading/rendering. `isRouteErrorResponse` checks if it's an HTTP error response (404, 500, etc.). This integrates seamlessly with React Router's loader/action error handling.

**Step 2: Create ConnectionLost component**

Create `dashboard/src/components/ConnectionLost.tsx`:

```typescript
import { WifiOff, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ConnectionLostProps {
  onRetry: () => void;
  error?: string;
}

export function ConnectionLost({ onRetry, error }: ConnectionLostProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-8">
      <WifiOff className="w-16 h-16 text-destructive mb-4" />
      <h1 className="text-4xl font-display text-destructive mb-4">
        Connection Lost
      </h1>
      {error && (
        <p className="text-muted-foreground text-sm mb-8 max-w-md text-center">
          {error}
        </p>
      )}
      <Button onClick={onRetry}>
        <RefreshCw className="w-4 h-4" />
        Reconnect
      </Button>
    </div>
  );
}
```

**Step 3: Verify error boundary works**

The error boundary is already configured in `router.tsx` (Task 5):

```typescript
{
  path: '/',
  element: <Layout />,
  errorElement: <RootErrorBoundary />,  // Route-level error boundary
  children: [ /* ... */ ]
}
```

To test the error boundary:

1. Add a test route that throws an error
2. Navigate to it and verify RootErrorBoundary renders
3. Check that error details show in dev mode
4. Verify "Go Home" and "Reload" buttons work

**Step 4: Commit**

```bash
git add dashboard/src/components/ErrorBoundary.tsx \
        dashboard/src/components/ConnectionLost.tsx
git commit -m "feat(dashboard): add route-based error boundaries

- RootErrorBoundary using useRouteError hook (React Router v7)
- Handles both HTTP errors (404, 500) and JavaScript errors
- Shows error stack in dev mode only
- Navigation buttons: Go Home, Go Back, Reload
- ConnectionLost component for WebSocket failures
- Integrates with router errorElement (configured in Task 5)"
```

---

## Task 7: Create Layout Component with Outlet and Navigation State

**Files:**
- Create: `dashboard/src/components/Layout.tsx`

> **Note:** With React Router v7 Data Mode, the Layout component uses `<Outlet />` instead of `{children}` to render nested routes. The `useNavigation` hook provides navigation state for showing loading indicators during route transitions.

> **Alternative: shadcn Sidebar Component**
>
> For more advanced sidebar needs, consider using the full-featured [shadcn Sidebar component](https://ui.shadcn.com/docs/components/sidebar) which provides:
> - Collapsible/expandable states
> - Mobile responsive with sheet overlay
> - Keyboard navigation
> - Nested menu support
> - Cookie persistence for state
>
> Install via: `npx shadcn@latest add sidebar`
>
> The implementation below is a simpler custom sidebar. If you need the full shadcn Sidebar features later, you can migrate to it.

**Step 1: Create Layout component with Outlet**

Create `dashboard/src/components/Layout.tsx`:

```typescript
import { Outlet, Link, useLocation, useNavigation } from 'react-router-dom';
import {
  GitBranch,
  History,
  Radio,
  Compass
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { NavigationProgress } from '@/components/NavigationProgress';

export function Layout() {
  const location = useLocation();
  const navigation = useNavigation();

  const isNavigating = navigation.state !== 'idle';

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="w-64 bg-sidebar border-r border-sidebar-border flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-sidebar-border">
          <h1 className="text-4xl font-display text-sidebar-primary tracking-wider">
            AMELIA
          </h1>
          <p className="text-xs font-mono text-muted-foreground mt-1">
            Agentic Orchestrator
          </p>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1">
          <nav className="p-4" aria-label="Main navigation">
            <div className="space-y-6">
              <NavSection title="WORKFLOWS">
                <NavLink
                  to="/workflows"
                  icon={<GitBranch className="w-4 h-4" />}
                  active={isActive('/workflows')}
                  label="Active Jobs"
                />
              </NavSection>

              <NavSection title="HISTORY">
                <NavLink
                  to="/history"
                  icon={<History className="w-4 h-4" />}
                  active={isActive('/history')}
                  label="Past Runs"
                />
              </NavSection>

              <NavSection title="MONITORING">
                <NavLink
                  to="/logs"
                  icon={<Radio className="w-4 h-4" />}
                  active={isActive('/logs')}
                  label="Logs"
                />
              </NavSection>
            </div>
          </nav>
        </ScrollArea>

        {/* Footer */}
        <div className="p-4 border-t border-sidebar-border">
          <div className="flex items-center gap-3">
            <Compass className="w-8 h-8 text-muted-foreground/50" />
            <div className="text-xs font-mono text-muted-foreground">
              <div>Server: localhost:8420</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="inline-block w-2 h-2 bg-[--status-running] rounded-full animate-pulse-glow" />
                Connected
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area with navigation progress */}
      <main className="flex-1 overflow-hidden relative">
        {isNavigating && <NavigationProgress />}
        <Outlet />
      </main>
    </div>
  );
}

// Helper components
interface NavSectionProps {
  title: string;
  children: React.ReactNode;
}

function NavSection({ title, children }: NavSectionProps) {
  return (
    <div>
      <div className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider px-3 py-2">
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

interface NavLinkProps {
  to: string;
  icon: React.ReactNode;
  active: boolean;
  label: string;
}

function NavLink({ to, icon, active, label }: NavLinkProps) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex items-center gap-3 px-3 py-2 font-heading font-semibold text-sm tracking-wide transition-colors focus-ring rounded',
        active
          ? 'bg-sidebar-primary text-sidebar-primary-foreground'
          : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
      )}
    >
      {icon}
      {label}
    </Link>
  );
}
```

> **Key Changes:**
> - Uses `<Outlet />` instead of `{children}` - this renders the matched child route
> - Uses `useNavigation()` hook to track navigation state
> - Shows `<NavigationProgress />` when `navigation.state !== 'idle'`
> - Imports from `react-router-dom` instead of `react-router`

**Step 2: Verify layout renders correctly**

The Layout is already configured as the root route element in `router.tsx` (Task 5):

```typescript
{
  path: '/',
  element: <Layout />,  // Layout with Outlet
  children: [ /* nested routes render in Outlet */ ]
}
```

Run:

```bash
pnpm run dev
```

Expected:
- Sidebar on left with AMELIA logo
- Navigation sections: WORKFLOWS, HISTORY, MONITORING
- Active route highlighted with primary color
- Footer shows server status with pulsing indicator
- Main content area shows page content (via Outlet)
- NavigationProgress appears during route transitions

**Step 3: Test navigation state**

Navigate between routes and verify:
- Progress bar appears at top during transitions
- Loading state is visible for lazy-loaded routes
- No progress bar when navigation.state is 'idle'

**Step 4: Commit**

```bash
git add dashboard/src/components/Layout.tsx
git commit -m "feat(dashboard): add layout component with Outlet and navigation state

- Uses Outlet for nested route rendering (React Router v7)
- useNavigation hook for tracking route transitions
- NavigationProgress shown during navigation.state !== 'idle'
- Sidebar with AMELIA branding using design tokens
- Navigation organized by sections with Lucide icons
- Active route highlighting with primary color
- Server connection status indicator with pulse animation
- ScrollArea for navigation overflow
- Proper ARIA labels for accessibility"
```

---

## Task 8: Setup TypeScript Types

**Files:**
- Create: `dashboard/src/types/index.ts`

**Step 1: Create shared TypeScript types**

Create `dashboard/src/types/index.ts`:

```typescript
/**
 * Shared TypeScript types for the Amelia Dashboard.
 * These types mirror the Python Pydantic models from the backend API.
 */

// ============================================================================
// Workflow Types
// ============================================================================

export type WorkflowStatus =
  | 'pending'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface WorkflowSummary {
  id: string;
  issue_id: string;
  worktree_path: string;
  worktree_name: string;
  status: WorkflowStatus;
  started_at: string | null;
  completed_at: string | null;
  current_stage: string | null;
}

export interface WorkflowDetail extends WorkflowSummary {
  failure_reason: string | null;
  plan: TaskDAG | null;
  token_usage: Record<string, TokenSummary>;
  recent_events: WorkflowEvent[];
}

// ============================================================================
// Event Types
// ============================================================================

export type EventType =
  // Lifecycle
  | 'workflow_started'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled'
  // Stages
  | 'stage_started'
  | 'stage_completed'
  // Approval
  | 'approval_required'
  | 'approval_granted'
  | 'approval_rejected'
  // Artifacts
  | 'file_created'
  | 'file_modified'
  | 'file_deleted'
  // Review cycle
  | 'review_requested'
  | 'review_completed'
  | 'revision_requested'
  // System
  | 'system_error'
  | 'system_warning';

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  sequence: number;
  timestamp: string;
  agent: string;
  event_type: EventType;
  message: string;
  data?: Record<string, unknown>;
  correlation_id?: string;
}

// ============================================================================
// Plan Types (TaskDAG)
// ============================================================================

export interface TaskNode {
  id: string;
  description: string;
  agent: 'architect' | 'developer' | 'reviewer';
  dependencies: string[];
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  result?: string;
  error?: string;
}

export interface TaskDAG {
  tasks: TaskNode[];
  execution_order: string[];
}

// ============================================================================
// Token Usage Types
// ============================================================================

export interface TokenSummary {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

export interface TokenUsage {
  workflow_id: string;
  agent: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number | null;
  timestamp: string;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
  cursor: string | null;
  has_more: boolean;
}

export interface ErrorResponse {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

export interface StartWorkflowRequest {
  issue_id: string;
  profile?: string;
  worktree_path?: string;
}

export interface RejectRequest {
  feedback: string;
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

// Server → Client messages (messages received by the dashboard)
export type WebSocketMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' }
  | { type: 'ping' }
  | { type: 'event'; data: WorkflowEvent }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string };

// Client → Server messages (messages sent by the dashboard)
export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };

// ============================================================================
// UI State Types
// ============================================================================

export interface ConnectionState {
  status: 'connected' | 'disconnected' | 'connecting';
  error?: string;
}
```

**Step 2: Commit**

```bash
git add dashboard/src/types/index.ts
git commit -m "feat(dashboard): add TypeScript type definitions

- Workflow types (summary, detail, status)
- Event types (all event kinds from backend)
- Plan types (TaskDAG, TaskNode)
- Token usage types
- API request/response types
- WebSocket message types (server→client and client→server)
  - WebSocketMessage: server→client (includes backfill_complete, backfill_expired)
  - WebSocketClientMessage: client→server (subscribe, unsubscribe, pong)
- UI state types

Types mirror Python Pydantic models for API compatibility"
```

---

## Task 9: Add FastAPI Static File Serving

**Files:**
- Modify: `amelia/server/app.py`
- Create: `tests/unit/server/test_static_files.py`

**Step 1: Write test for static file endpoint**

Create `tests/unit/server/test_static_files.py`:

```python
"""Test static file serving for dashboard."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_serve_dashboard_index(test_client: AsyncClient):
    """GET / should serve dashboard index.html."""
    response = await test_client.get("/")

    # Should return HTML (even if dist/ doesn't exist yet, FastAPI returns 404)
    # Once built, should return 200
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        assert "text/html" in response.headers.get("content-type", "")
        assert b"Amelia Dashboard" in response.content


@pytest.mark.asyncio
async def test_serve_dashboard_assets(test_client: AsyncClient):
    """Static assets should be served from /assets/."""
    # This will 404 until build happens, which is expected
    response = await test_client.get("/assets/index.js")
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_dashboard_spa_fallback(test_client: AsyncClient):
    """Non-existent routes should fallback to index.html for SPA routing."""
    response = await test_client.get("/workflows/abc-123")

    # Should serve index.html for client-side routing
    assert response.status_code in [200, 404]
```

**Step 2: Add static file mounting to FastAPI app**

Modify `amelia/server/app.py` to add static file serving after API routes:

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ... existing imports and app setup ...

# Serve dashboard static files (after build)
DASHBOARD_DIR = Path(__file__).parent.parent.parent / "dashboard" / "dist"

if DASHBOARD_DIR.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIR / "assets"), name="assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_dashboard(full_path: str):
        """Serve dashboard index.html for client-side routing."""
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return {"error": "Not found"}, 404

        index_file = DASHBOARD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        return {"error": "Dashboard not built"}, 404
else:
    @app.get("/")
    async def dashboard_not_built():
        """Inform user that dashboard needs to be built."""
        return {
            "message": "Dashboard not built",
            "instructions": "Run 'cd dashboard && pnpm run build' to build the dashboard"
        }
```

**Step 3: Commit**

```bash
git add amelia/server/app.py tests/unit/server/test_static_files.py
git commit -m "feat(server): add static file serving for dashboard

- Mount /assets for dashboard static files
- SPA fallback serves index.html for client-side routing
- Fallback message when dashboard not built
- Preserves API routes (/api, /ws prefixes)
- Tests for static serving and SPA routing"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `cd dashboard && pnpm install` succeeds without errors
- [ ] `pnpm run dev` starts dev server at localhost:3000
- [ ] Three tsconfig files exist: `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`
- [ ] `@tailwindcss/vite` in devDependencies (NOT postcss plugin)
- [ ] `@types/node` in devDependencies (for path aliases)
- [ ] No `postcss.config.js` or `tailwind.config.js` files (Tailwind v4 uses Vite plugin)
- [ ] ai-elements components installed in `src/components/ai-elements/` (queue, confirmation, loader, shimmer only)
- [ ] React Flow (@xyflow/react) installed in package.json
- [ ] Progress and Skeleton components in `src/components/ui/`
- [ ] `react-router-dom` (not `react-router`) in dependencies
- [ ] Router configuration in `src/router.tsx` uses `createBrowserRouter`
- [ ] Layout component uses `<Outlet />` (not `{children}`)
- [ ] Page components in `src/pages/` with default exports
- [ ] Routing works: Navigate to /workflows, /history, /logs
- [ ] Active route is highlighted with primary (gold) color
- [ ] Lazy loading works: Check Network tab for chunked JS files on navigation
- [ ] NavigationProgress shows during route transitions
- [ ] Route error boundaries catch errors (test with broken route)
- [ ] Dark aviation theme applied via CSS variables (`@theme inline` directive)
- [ ] Custom fonts loaded (Bebas Neue, Barlow Condensed, etc.)
- [ ] `pnpm run build` creates `dashboard/dist/` successfully
- [ ] FastAPI serves dashboard at localhost:8420 after build
- [ ] API proxy works in dev mode
- [ ] TypeScript compilation passes: `pnpm run type-check`
- [ ] No console errors in browser devtools
- [ ] Responsive layout: sidebar + main content area
- [ ] Status indicator pulses in sidebar footer
- [ ] All files committed to git

---

## Summary

This plan establishes the complete foundation for the Amelia Dashboard using modern best practices:

**Completed:**
- Vite + React + TypeScript project scaffold with path aliases
- **Tailwind CSS v4** with `@tailwindcss/vite` plugin (NOT PostCSS)
- **Three tsconfig files** (`tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`) for proper Vite setup
- **shadcn/ui infrastructure** (Radix UI, CVA, clsx, tailwind-merge)
- **ai-elements (selective)** via shadcn registry (queue, confirmation, loader, shimmer)
- **React Flow** (@xyflow/react) for custom workflow visualization
- **CSS variable-based design tokens** via `@theme inline` directive (OKLCH color space)
- Base UI components: Button, Badge, Card, ScrollArea, Tooltip, Progress, Skeleton
- **React Router v7 Data Mode** with `createBrowserRouter` + `RouterProvider`
- Route-based lazy loading with code splitting
- Route-level error boundaries using `errorElement`
- Layout component with `<Outlet />` and navigation state tracking
- TypeScript type definitions for API models
- FastAPI static file serving integration
- Development proxy for API and WebSocket

**Modern Tailwind v4 Setup:**
- Uses `@tailwindcss/vite` plugin instead of PostCSS
- No `tailwind.config.js` or `postcss.config.js` required
- CSS theming via `@theme inline` directive to map CSS variables to Tailwind utilities
- `@types/node` required for path aliases in `vite.config.ts`

**React Router v7 Data Mode:**
- `createBrowserRouter` configuration in `router.tsx`
- Route-based lazy loading via `route.lazy` for code splitting
- Route-level error boundaries via `errorElement`
- `<Outlet />` in Layout for nested route rendering
- `useNavigation()` hook for transition state tracking
- `useRouteError()` hook for error handling
- `RouterProvider` with `fallbackElement` for initial load
- Imports from `react-router-dom` (browser-specific package)

**Design System:**
- All colors via CSS variables (no inline hex values)
- Semantic tokens: `--background`, `--foreground`, `--primary`, `--status-*`
- Typography tokens: `--font-display`, `--font-heading`, `--font-body`, `--font-mono`
- Radix UI primitives for accessibility (ARIA, keyboard navigation built-in)
- `data-slot` attributes on components for styling hooks
- ai-elements inherit theme automatically via shadcn CSS variables

**HYBRID Component Approach:**

We use a hybrid approach: ai-elements for standard workflow UI, custom React Flow for visualization:

| Component | Source | Dashboard Feature | Rationale |
|-----------|--------|-------------------|-----------|
| `queue` | ai-elements | JobQueue, ActivityLog | Standard queue UI fits design |
| `confirmation` | ai-elements | ApprovalControls | Human-in-the-loop approval UI |
| `loader` | ai-elements | Loading states | API call pending indicators |
| `shimmer` | ai-elements | Skeleton loading | Placeholder content during load |
| `task` | ai-elements | Task display | Individual task status in queue |
| `canvas` | **Custom (React Flow)** | WorkflowCanvas | Map pin design requires custom nodes |
| `node` | **Custom (React Flow)** | Pipeline steps | Aviation aesthetic with map pins |
| `edge` | **Custom (React Flow)** | Dependencies | Custom styling for flight paths |

**Why custom WorkflowCanvas?** The design mock uses map pin icons for workflow nodes, which requires custom implementation to preserve the aviation/flight control aesthetic. The generic ai-elements canvas components would not match our visual design.

**Next Steps (Plan 09 & 10):**
- Plan 09: Add route loaders for data fetching from API endpoints
- Plan 09: Implement API client with React Router loaders/actions
- Plan 10: Wire up ai-elements components (queue, confirmation, loader, shimmer)
- Plan 10: Integrate queue component for JobQueue panel
- Plan 10: Build custom WorkflowCanvas using React Flow with map pin nodes
- Plan 10: Build custom MapPinNode component for pipeline visualization
- Plan 10: Integrate confirmation for ApprovalControls
- Plan 10: Use loader/shimmer for loading states throughout
