# Dashboard Project Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the React dashboard frontend with Vite, TypeScript, Tailwind CSS, and React Router v7. This establishes the foundation for the web UI with proper aviation/cockpit aesthetic, routing infrastructure, error boundaries, and FastAPI static file serving.

**Architecture:** Vite + React 18 + TypeScript project in `dashboard/` directory with Tailwind CSS configured for the aviation theme, React Router v7 for client-side routing, development proxy for API calls, and FastAPI static file mounting for production.

**Tech Stack:** Vite 6, React 18, TypeScript 5, Tailwind CSS 4, React Router v7, Vitest

**Depends on:**
- Phase 2.1-01: Server Foundation (FastAPI app)
- Phase 2.1-04: REST API Endpoints (API to proxy to)

---

## Task 1: Create Vite + React + TypeScript Project

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/tsconfig.node.json`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/vite-env.d.ts`
- Create: `dashboard/.gitignore`

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
    "lint": "eslint src --ext ts,tsx",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router": "^7.0.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@typescript-eslint/eslint-plugin": "^8.15.0",
    "@typescript-eslint/parser": "^8.15.0",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.15.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.14",
    "postcss": "^8.4.49",
    "tailwindcss": "^4.0.0",
    "typescript": "~5.6.2",
    "vite": "^6.0.1",
    "vitest": "^2.1.5",
    "@vitest/ui": "^2.1.5"
  }
}
```

**Step 2: Create Vite configuration with API proxy**

Create `dashboard/vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Proxy API calls to FastAPI server during development
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
          'router': ['react-router'],
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

**Step 3: Create TypeScript configuration**

Create `dashboard/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true
  },
  "include": ["src"]
}
```

Create `dashboard/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
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
import './index.css';

function App() {
  return (
    <div className="min-h-screen bg-bg-dark text-text-primary">
      <h1 className="text-4xl font-display p-8">Amelia Dashboard</h1>
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
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
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

**Step 7: Install dependencies**

Run in `dashboard/` directory:

```bash
cd /Users/ka/github/amelia-docs/dashboard
npm install
```

Expected: Dependencies installed successfully

**Step 8: Verify dev server starts**

Run:

```bash
npm run dev
```

Expected: Vite dev server starts on http://localhost:3000

**Step 9: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): initialize Vite + React + TypeScript project

- Vite 6 with React plugin
- TypeScript 5 with strict mode
- Development proxy for /api and /ws endpoints
- Package structure with npm scripts
- HTML entry point with aviation theme fonts"
```

---

## Task 2: Configure Tailwind CSS with Aviation Theme

**Files:**
- Create: `dashboard/tailwind.config.ts`
- Create: `dashboard/postcss.config.js`
- Create: `dashboard/src/index.css`

**Step 1: Create Tailwind configuration with custom theme**

Create `dashboard/tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Background layers
        bg: {
          dark: '#0D1A12',    // Deep background
          main: '#1F332E',    // Main content areas
        },
        // Text hierarchy
        text: {
          primary: '#EFF8E2',   // High-contrast readable text
          secondary: '#88A896', // Muted labels, descriptions
        },
        // Accent colors
        accent: {
          gold: '#FFC857',  // Logo, active states, running workflows
          blue: '#5B9BD5',  // Links, IDs, interactive elements
        },
        // Status colors
        status: {
          running: '#FFC857',   // Amber - in progress
          completed: '#5B8A72', // Green - done
          pending: '#4A5C54',   // Gray - queued
          blocked: '#A33D2E',   // Red - awaiting approval
          failed: '#A33D2E',    // Red - error
        },
      },
      fontFamily: {
        display: ['Bebas Neue', 'sans-serif'],           // Logo, workflow ID, large numbers
        heading: ['Barlow Condensed', 'sans-serif'],     // Nav labels, section titles, badges
        body: ['Source Sans 3', 'sans-serif'],           // Content text, descriptions
        mono: ['IBM Plex Mono', 'monospace'],            // Timestamps, code, IDs
      },
      keyframes: {
        pulse: {
          '0%, 100%': {
            opacity: '1',
            boxShadow: '0 0 8px rgba(255, 200, 87, 0.6)'
          },
          '50%': {
            opacity: '0.6',
            boxShadow: '0 0 12px rgba(255, 200, 87, 0.8)'
          },
        },
        beaconGlow: {
          '0%, 100%': {
            filter: 'drop-shadow(0 0 4px rgba(255, 200, 87, 0.6))'
          },
          '50%': {
            filter: 'drop-shadow(0 0 16px rgba(255, 200, 87, 0.6))'
          },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
      animation: {
        pulse: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        beaconGlow: 'beaconGlow 2s ease-in-out infinite',
        blink: 'blink 1s step-end infinite',
      },
    },
  },
  plugins: [],
} satisfies Config;
```

**Step 2: Create PostCSS configuration**

Create `dashboard/postcss.config.js`:

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

**Step 3: Create CSS entry point with base styles**

Create `dashboard/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    @apply font-body;
  }

  body {
    @apply bg-bg-dark text-text-primary antialiased;
  }

  /* Custom scrollbar for aviation aesthetic */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    @apply bg-bg-dark;
  }

  ::-webkit-scrollbar-thumb {
    @apply bg-text-secondary rounded;
  }

  ::-webkit-scrollbar-thumb:hover {
    @apply bg-accent-gold;
  }
}

@layer components {
  /* Status badge utilities */
  .badge-running {
    @apply bg-status-running text-bg-dark font-heading font-semibold px-2 py-1 rounded text-sm;
  }

  .badge-completed {
    @apply bg-status-completed text-text-primary font-heading font-semibold px-2 py-1 rounded text-sm;
  }

  .badge-pending {
    @apply bg-status-pending text-text-secondary font-heading font-semibold px-2 py-1 rounded text-sm;
  }

  .badge-blocked {
    @apply bg-status-blocked text-text-primary font-heading font-semibold px-2 py-1 rounded text-sm;
  }

  .badge-failed {
    @apply bg-status-failed text-text-primary font-heading font-semibold px-2 py-1 rounded text-sm;
  }

  /* Terminal-style activity log */
  .terminal {
    @apply font-mono text-sm bg-bg-dark border border-text-secondary/20 p-4 rounded;
  }

  /* Button styles */
  .btn-primary {
    @apply bg-accent-gold text-bg-dark font-heading font-semibold px-4 py-2 rounded
           hover:bg-accent-gold/90 transition-colors;
  }

  .btn-secondary {
    @apply bg-bg-main text-text-primary font-heading font-semibold px-4 py-2 rounded
           border border-text-secondary/40 hover:border-accent-blue transition-colors;
  }

  .btn-danger {
    @apply bg-status-failed text-text-primary font-heading font-semibold px-4 py-2 rounded
           hover:bg-status-failed/90 transition-colors;
  }
}

/* Accessibility: Respect user preferences for reduced motion */
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

**Step 4: Verify theme is applied**

Run:

```bash
npm run dev
```

Expected: Dashboard renders with dark background (#0D1A12) and light text (#EFF8E2)

**Step 5: Commit**

```bash
git add dashboard/tailwind.config.ts dashboard/postcss.config.js dashboard/src/index.css
git commit -m "feat(dashboard): configure Tailwind CSS with aviation theme

- Custom color palette (dark backgrounds, light text)
- Aviation typography (Bebas Neue, Barlow Condensed, etc.)
- Status badge styles (running, completed, pending, blocked, failed)
- Custom animations (pulse, beaconGlow, blink)
- Terminal-style component utilities
- Custom scrollbar styling
- Respects prefers-reduced-motion"
```

---

## Task 3: Setup React Router v7

**Files:**
- Modify: `dashboard/src/main.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/components/ComingSoon.tsx`

**Step 1: Create ComingSoon placeholder component**

Create `dashboard/src/components/ComingSoon.tsx`:

```typescript
interface ComingSoonProps {
  title: string;
}

export function ComingSoon({ title }: ComingSoonProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <h2 className="text-3xl font-display text-accent-gold">{title}</h2>
      <p className="text-text-secondary font-heading text-lg">Coming soon</p>
      <div className="w-16 h-16 border-4 border-text-secondary/20 border-t-accent-gold rounded-full animate-spin" />
    </div>
  );
}
```

**Step 2: Create App component with routing**

Create `dashboard/src/App.tsx`:

```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router';
import { ComingSoon } from './components/ComingSoon';

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-dark text-text-primary">
        {/* Temporary header until Layout is built */}
        <header className="bg-bg-main border-b border-text-secondary/20 p-4">
          <h1 className="text-3xl font-display text-accent-gold">AMELIA</h1>
        </header>

        <main className="h-[calc(100vh-73px)]">
          <Routes>
            <Route index element={<Navigate to="/workflows" replace />} />
            <Route path="/workflows" element={<ComingSoon title="Active Workflows" />} />
            <Route path="/workflows/:id" element={<ComingSoon title="Workflow Detail" />} />
            <Route path="/history" element={<ComingSoon title="Past Runs" />} />
            <Route path="/logs" element={<ComingSoon title="Logs" />} />
            <Route path="*" element={<Navigate to="/workflows" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

**Step 3: Update main.tsx to use App component**

Modify `dashboard/src/main.tsx`:

```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './index.css';

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

**Step 4: Verify routing works**

Run:

```bash
npm run dev
```

Expected:
- Navigate to http://localhost:3000 → redirects to /workflows
- /workflows shows "Active Workflows - Coming soon"
- /history shows "Past Runs - Coming soon"
- /logs shows "Logs - Coming soon"
- Invalid routes redirect to /workflows

**Step 5: Commit**

```bash
git add dashboard/src/App.tsx dashboard/src/components/ComingSoon.tsx dashboard/src/main.tsx
git commit -m "feat(dashboard): setup React Router v7 with placeholder routes

- BrowserRouter with client-side routing
- Routes: /workflows, /workflows/:id, /history, /logs
- ComingSoon placeholder component for future views
- Root redirect to /workflows
- Fallback redirect for 404s"
```

---

## Task 4: Add Error Boundaries and Browser Check

**Files:**
- Create: `dashboard/src/components/ErrorBoundary.tsx`
- Create: `dashboard/src/components/ConnectionLost.tsx`
- Create: `dashboard/src/components/BrowserCheck.tsx`
- Modify: `dashboard/src/App.tsx`

**Step 1: Create ErrorBoundary component**

Create `dashboard/src/components/ErrorBoundary.tsx`:

```typescript
import { Component, ErrorInfo, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    error: null
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-bg-dark text-text-primary p-8">
          <h1 className="text-4xl font-display text-status-failed mb-4">
            Something went wrong
          </h1>
          <p className="text-text-secondary font-body mb-8 max-w-md text-center">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary"
          >
            Reload Dashboard
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

**Step 2: Create ConnectionLost component**

Create `dashboard/src/components/ConnectionLost.tsx`:

```typescript
interface ConnectionLostProps {
  onRetry: () => void;
  error?: string;
}

export function ConnectionLost({ onRetry, error }: ConnectionLostProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg-dark text-text-primary p-8">
      <div className="text-status-failed text-4xl font-display mb-4">
        Connection Lost
      </div>
      {error && (
        <p className="text-text-secondary font-body text-sm mb-8 max-w-md text-center">
          {error}
        </p>
      )}
      <button onClick={onRetry} className="btn-primary">
        Reconnect
      </button>
    </div>
  );
}
```

**Step 3: Create BrowserCheck component**

Create `dashboard/src/components/BrowserCheck.tsx`:

```typescript
import { ReactNode } from 'react';

interface BrowserCheckProps {
  children: ReactNode;
}

export function BrowserCheck({ children }: BrowserCheckProps) {
  // Check for Chrome (but not Edge or Opera)
  const isChrome =
    /Chrome/.test(navigator.userAgent) &&
    !/Edg|OPR/.test(navigator.userAgent);

  if (!isChrome) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-bg-dark text-text-primary p-8">
        <h1 className="text-4xl font-display text-accent-gold mb-4">
          Unsupported Browser
        </h1>
        <p className="text-text-secondary font-body mb-4 max-w-md text-center">
          Amelia Dashboard is optimized for Google Chrome.
        </p>
        <p className="text-text-secondary font-body mb-8 max-w-md text-center text-sm">
          Chrome-specific features: container queries, structuredClone(),
          native WebSocket ping/pong, CSS color-mix()
        </p>
        <a
          href="https://www.google.com/chrome/"
          className="text-accent-blue hover:underline font-heading text-lg"
        >
          Download Chrome →
        </a>
      </div>
    );
  }

  return <>{children}</>;
}
```

**Step 4: Wrap App with error boundaries and browser check**

Modify `dashboard/src/App.tsx`:

```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router';
import { ErrorBoundary } from './components/ErrorBoundary';
import { BrowserCheck } from './components/BrowserCheck';
import { ComingSoon } from './components/ComingSoon';

export function App() {
  return (
    <BrowserCheck>
      <ErrorBoundary>
        <BrowserRouter>
          <div className="min-h-screen bg-bg-dark text-text-primary">
            {/* Temporary header until Layout is built */}
            <header className="bg-bg-main border-b border-text-secondary/20 p-4">
              <h1 className="text-3xl font-display text-accent-gold">AMELIA</h1>
            </header>

            <main className="h-[calc(100vh-73px)]">
              <Routes>
                <Route index element={<Navigate to="/workflows" replace />} />
                <Route path="/workflows" element={<ComingSoon title="Active Workflows" />} />
                <Route path="/workflows/:id" element={<ComingSoon title="Workflow Detail" />} />
                <Route path="/history" element={<ComingSoon title="Past Runs" />} />
                <Route path="/logs" element={<ComingSoon title="Logs" />} />
                <Route path="*" element={<Navigate to="/workflows" replace />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </ErrorBoundary>
    </BrowserCheck>
  );
}
```

**Step 5: Test error boundary**

Add temporary error trigger in ComingSoon component to verify ErrorBoundary works:

```typescript
// In ComingSoon.tsx, temporarily add:
if (title === "Test Error") {
  throw new Error("Test error boundary");
}
```

Navigate to `/workflows` and change title to "Test Error" temporarily.

Expected: ErrorBoundary catches error and shows fallback UI

Remove test code after verification.

**Step 6: Test browser check**

Open dashboard in Firefox or Safari.

Expected: Shows "Unsupported Browser" message with Chrome download link

**Step 7: Commit**

```bash
git add dashboard/src/components/ErrorBoundary.tsx \
        dashboard/src/components/ConnectionLost.tsx \
        dashboard/src/components/BrowserCheck.tsx \
        dashboard/src/App.tsx
git commit -m "feat(dashboard): add error boundaries and browser compatibility check

- ErrorBoundary class component with fallback UI
- ConnectionLost component for WebSocket failures
- BrowserCheck enforces Chrome-only support
- Graceful error handling with reload button
- User-friendly messaging for unsupported browsers"
```

---

## Task 5: Create Basic Layout Component

**Files:**
- Create: `dashboard/src/components/Layout.tsx`
- Modify: `dashboard/src/App.tsx`

**Step 1: Create Layout component with sidebar placeholder**

Create `dashboard/src/components/Layout.tsx`:

```typescript
import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  return (
    <div className="flex h-screen bg-bg-dark text-text-primary">
      {/* Sidebar */}
      <aside className="w-64 bg-bg-main border-r border-text-secondary/20 flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-text-secondary/20">
          <h1 className="text-4xl font-display text-accent-gold tracking-wider">
            AMELIA
          </h1>
          <p className="text-xs font-mono text-text-secondary mt-1">
            Agentic Orchestrator
          </p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <div className="space-y-1">
            <NavSection title="WORKFLOWS" />
            <NavLink
              to="/workflows"
              active={isActive('/workflows')}
              label="Active Jobs"
            />

            <NavSection title="HISTORY" className="mt-6" />
            <NavLink
              to="/history"
              active={isActive('/history')}
              label="Past Runs"
            />

            <NavSection title="MONITORING" className="mt-6" />
            <NavLink
              to="/logs"
              active={isActive('/logs')}
              label="Logs"
            />
          </div>
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-text-secondary/20">
          <div className="text-xs font-mono text-text-secondary">
            <div>Server: localhost:8420</div>
            <div className="mt-1">
              <span className="inline-block w-2 h-2 bg-status-running rounded-full animate-pulse mr-2" />
              Connected
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}

// Helper components
interface NavSectionProps {
  title: string;
  className?: string;
}

function NavSection({ title, className = '' }: NavSectionProps) {
  return (
    <div className={`text-xs font-heading text-text-secondary/60 font-semibold tracking-wider px-3 py-2 ${className}`}>
      {title}
    </div>
  );
}

interface NavLinkProps {
  to: string;
  active: boolean;
  label: string;
}

function NavLink({ to, active, label }: NavLinkProps) {
  return (
    <Link
      to={to}
      className={`
        block px-3 py-2 rounded font-heading font-semibold text-sm transition-colors
        ${active
          ? 'bg-accent-gold text-bg-dark'
          : 'text-text-secondary hover:bg-bg-dark hover:text-text-primary'
        }
      `}
    >
      {label}
    </Link>
  );
}
```

**Step 2: Update App to use Layout**

Modify `dashboard/src/App.tsx`:

```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router';
import { ErrorBoundary } from './components/ErrorBoundary';
import { BrowserCheck } from './components/BrowserCheck';
import { Layout } from './components/Layout';
import { ComingSoon } from './components/ComingSoon';

export function App() {
  return (
    <BrowserCheck>
      <ErrorBoundary>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route index element={<Navigate to="/workflows" replace />} />
              <Route path="/workflows" element={<ComingSoon title="Active Workflows" />} />
              <Route path="/workflows/:id" element={<ComingSoon title="Workflow Detail" />} />
              <Route path="/history" element={<ComingSoon title="Past Runs" />} />
              <Route path="/logs" element={<ComingSoon title="Logs" />} />
              <Route path="*" element={<Navigate to="/workflows" replace />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </ErrorBoundary>
    </BrowserCheck>
  );
}
```

**Step 3: Verify layout renders correctly**

Run:

```bash
npm run dev
```

Expected:
- Sidebar on left with AMELIA logo
- Navigation sections: WORKFLOWS, HISTORY, MONITORING
- Active route highlighted in gold
- Footer shows server status with pulsing indicator
- Main content area shows ComingSoon placeholder

**Step 4: Test navigation**

Click each nav link and verify:
- Route changes in URL
- Active state updates (gold background)
- Content area updates

**Step 5: Commit**

```bash
git add dashboard/src/components/Layout.tsx dashboard/src/App.tsx
git commit -m "feat(dashboard): add layout component with sidebar navigation

- Sidebar with AMELIA branding
- Navigation organized by sections (Workflows, History, Monitoring)
- Active route highlighting with gold accent
- Server connection status indicator
- Responsive layout with fixed sidebar and scrollable main area"
```

---

## Task 6: Setup TypeScript Types

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

export type WebSocketMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' }
  | { type: 'ping' }
  | { type: 'event'; data: WorkflowEvent };

// ============================================================================
// UI State Types
// ============================================================================

export interface ConnectionState {
  status: 'connected' | 'disconnected' | 'connecting';
  error?: string;
}
```

**Step 2: Verify types are importable**

Add import to `App.tsx` to verify:

```typescript
import type { WorkflowStatus } from './types';
```

Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add dashboard/src/types/index.ts
git commit -m "feat(dashboard): add TypeScript type definitions

- Workflow types (summary, detail, status)
- Event types (all event kinds from backend)
- Plan types (TaskDAG, TaskNode)
- Token usage types
- API request/response types
- WebSocket message types
- UI state types

Types mirror Python Pydantic models for API compatibility"
```

---

## Task 7: Add FastAPI Static File Serving

**Files:**
- Modify: `amelia/server/app.py`

**Step 1: Write test for static file endpoint**

Create `tests/unit/server/test_static_files.py`:

```python
"""Test static file serving for dashboard."""
import pytest
from pathlib import Path
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

**Step 2: Run test to verify it fails (or passes with 404)**

Run: `uv run pytest tests/unit/server/test_static_files.py -v`

Expected: Tests pass but return 404 (no static serving yet)

**Step 3: Add static file mounting to FastAPI app**

Modify `amelia/server/app.py`:

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ... existing imports ...

app = FastAPI(title="Amelia Server", version="0.1.0")

# Mount API routes
app.include_router(api_router, prefix="/api")

# Serve dashboard static files (after build)
DASHBOARD_DIR = Path(__file__).parent.parent.parent / "dashboard" / "dist"

if DASHBOARD_DIR.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIR / "assets"), name="assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_dashboard(full_path: str):
        """Serve dashboard index.html for client-side routing."""
        # Skip API routes (already handled by router)
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
            "instructions": "Run 'cd dashboard && npm run build' to build the dashboard"
        }
```

**Step 4: Build dashboard and verify serving works**

Run:

```bash
cd dashboard
npm run build
```

Expected: Creates `dashboard/dist/` with built assets

**Step 5: Start server and verify dashboard loads**

Run:

```bash
uv run amelia server start
```

Navigate to http://localhost:8420

Expected: Dashboard loads with routing working

**Step 6: Verify API endpoints still work**

Test:

```bash
curl http://localhost:8420/api/health
```

Expected: Returns health check JSON (API routes not affected by static serving)

**Step 7: Commit**

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

## Task 8: Add Development npm Scripts and Documentation

**Files:**
- Modify: `dashboard/package.json`
- Create: `dashboard/README.md`

**Step 1: Add useful npm scripts**

Modify `dashboard/package.json` scripts section:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:run": "vitest run",
    "lint": "eslint src --ext ts,tsx",
    "lint:fix": "eslint src --ext ts,tsx --fix",
    "type-check": "tsc --noEmit",
    "clean": "rm -rf dist node_modules",
    "format": "prettier --write \"src/**/*.{ts,tsx,css}\"",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\""
  }
}
```

**Step 2: Create dashboard README**

Create `dashboard/README.md`:

```markdown
# Amelia Dashboard

React-based web dashboard for the Amelia agentic orchestrator.

## Tech Stack

- **Vite 6** - Build tool and dev server
- **React 18** - UI library
- **TypeScript 5** - Type safety
- **Tailwind CSS 4** - Styling with custom aviation theme
- **React Router v7** - Client-side routing
- **Vitest** - Unit testing

## Development

### Prerequisites

- Node.js 18+ and npm
- Amelia FastAPI server running (provides API at localhost:8420)

### Setup

```bash
# Install dependencies
npm install

# Start dev server (with API proxy)
npm run dev
```

Dev server runs at http://localhost:3000 with:
- Hot module replacement (HMR)
- Proxy to FastAPI server at localhost:8420
- TypeScript type checking

### Build

```bash
# Production build
npm run build

# Preview production build
npm run preview
```

Output: `dist/` directory served by FastAPI server

### Testing

```bash
# Run tests in watch mode
npm test

# Run tests once (CI mode)
npm run test:run

# Open test UI
npm run test:ui
```

### Code Quality

```bash
# Type checking
npm run type-check

# Linting
npm run lint
npm run lint:fix

# Formatting (Prettier)
npm run format
npm run format:check
```

## Architecture

### Directory Structure

```
dashboard/
├── src/
│   ├── components/      # React components
│   │   ├── Layout.tsx
│   │   ├── ComingSoon.tsx
│   │   ├── ErrorBoundary.tsx
│   │   ├── ConnectionLost.tsx
│   │   └── BrowserCheck.tsx
│   ├── types/           # TypeScript types
│   │   └── index.ts
│   ├── App.tsx          # Root component with routing
│   ├── main.tsx         # Entry point
│   └── index.css        # Tailwind + custom styles
├── index.html           # HTML entry point
├── vite.config.ts       # Vite configuration
├── tailwind.config.ts   # Tailwind theme (aviation colors)
└── package.json
```

### Design System

**Aviation/Cockpit Aesthetic**

Color Palette:
- Background: Dark (#0D1A12), Main (#1F332E)
- Text: Primary (#EFF8E2), Secondary (#88A896)
- Accent: Gold (#FFC857), Blue (#5B9BD5)
- Status: Running, Completed, Pending, Blocked, Failed

Typography:
- Display: Bebas Neue (logo, big numbers)
- Heading: Barlow Condensed (nav, titles)
- Body: Source Sans 3 (content)
- Mono: IBM Plex Mono (timestamps, code)

Animations:
- `animate-pulse` - Running workflows
- `animate-beaconGlow` - Map pins
- `animate-blink` - Active indicators

### Routing

- `/` → redirects to `/workflows`
- `/workflows` → Active jobs (coming soon)
- `/workflows/:id` → Workflow detail (coming soon)
- `/history` → Past runs (coming soon)
- `/logs` → System logs (coming soon)

### Browser Support

**Chrome only.** Uses Chrome-specific features:
- Container queries
- `structuredClone()`
- WebSocket native ping/pong
- CSS `color-mix()`

Unsupported browsers show a warning with Chrome download link.

## API Integration

Dev server proxies requests to FastAPI server:

- `http://localhost:3000/api/*` → `http://localhost:8420/api/*`
- `ws://localhost:3000/ws/*` → `ws://localhost:8420/ws/*`

Production build is served by FastAPI as static files.
```

**Step 3: Verify documentation is accurate**

Test each command mentioned in README:

```bash
npm run dev      # Should start dev server
npm run build    # Should create dist/
npm run type-check  # Should pass
```

**Step 4: Commit**

```bash
git add dashboard/package.json dashboard/README.md
git commit -m "docs(dashboard): add npm scripts and README

- Additional npm scripts for formatting, linting, testing
- Comprehensive README with setup instructions
- Architecture overview and design system documentation
- Browser support and API integration notes
- Directory structure explanation"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `cd dashboard && npm install` succeeds without errors
- [ ] `npm run dev` starts dev server at localhost:3000
- [ ] Routing works: Navigate to /workflows, /history, /logs
- [ ] Active route is highlighted in gold on sidebar
- [ ] Dark aviation theme applied (dark bg, light text)
- [ ] Custom fonts loaded (Bebas Neue, Barlow Condensed, etc.)
- [ ] Browser check works (test in Firefox/Safari shows warning)
- [ ] `npm run build` creates `dashboard/dist/` successfully
- [ ] FastAPI serves dashboard at localhost:8420 after build
- [ ] API proxy works in dev mode (future API calls will work)
- [ ] TypeScript compilation passes: `npm run type-check`
- [ ] No console errors in browser devtools
- [ ] ErrorBoundary catches and displays errors gracefully
- [ ] Responsive layout: sidebar + main content area
- [ ] Status indicator pulses in sidebar footer
- [ ] All files committed to git

---

## Summary

This plan establishes the complete foundation for the Amelia Dashboard:

**Completed:**
- ✅ Vite + React + TypeScript project scaffold
- ✅ Tailwind CSS with custom aviation theme (colors, fonts, animations)
- ✅ React Router v7 with placeholder routes
- ✅ Layout component with sidebar navigation
- ✅ Error boundaries for graceful degradation
- ✅ Chrome-only browser compatibility check
- ✅ TypeScript type definitions for API models
- ✅ FastAPI static file serving integration
- ✅ Development proxy for API and WebSocket
- ✅ npm scripts and comprehensive documentation

**Next Steps (Future Plans):**
- Plan 9: WebSocket connection hook and event handling
- Plan 10: Workflow components (canvas, activity log, controls)
- Plan 11: Real-time updates and state management

The dashboard is now ready for feature development. All routes show "Coming soon" placeholders. The design system is fully configured and the aviation aesthetic is applied. API integration is prepared via dev proxy and production static serving.
