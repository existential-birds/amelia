# Dashboard Setup Manual Testing Plan

**Branch:** `feat/dashboard-setup`
**Feature:** Initialize Amelia Dashboard with Vite + React + TypeScript, shadcn/ui components, and FastAPI static file serving

## Overview

This PR adds a complete dashboard frontend to Amelia, including:
- Vite + React + TypeScript project setup in `/dashboard`
- shadcn/ui component library with Radix UI primitives
- React Router v7 with lazy-loaded pages and error boundaries
- Custom AI-themed UI components (confirmation dialogs, queues, loaders)
- FastAPI integration for serving the built dashboard as static files
- SPA routing fallback for client-side navigation
- Dark theme with custom design tokens

Manual testing is needed to verify:
1. Dashboard builds correctly and displays properly
2. Client-side routing works when served by FastAPI
3. API routes remain accessible alongside the dashboard
4. Navigation and UI components render correctly

---

## Prerequisites

### Environment Setup

```bash
# 1. Navigate to project root
cd /Users/ka/github/amelia-langgraph-bridge

# 2. Install Python dependencies
uv sync

# 3. Install dashboard dependencies
cd dashboard && pnpm install

# 4. Build the dashboard
pnpm run build

# 5. Return to project root
cd ..

# 6. Verify build output exists
ls -la dashboard/dist/
```

### Testing Tools

- Browser with DevTools (Chrome/Firefox recommended)
- Terminal for running server commands
- curl or httpie for API testing

---

## Test Scenarios

### TC-01: Dashboard Build Process

**Objective:** Verify the dashboard builds without errors and produces correct output

**Steps:**
1. Navigate to dashboard directory
2. Run TypeScript type checking
3. Run the build command
4. Verify output structure

**Expected Result:**
- No TypeScript errors
- Build completes successfully
- `dist/` contains `index.html` and `assets/` directory
- Assets include JS, CSS, and sourcemap files

**Verification Commands:**
```bash
cd dashboard
pnpm run type-check
pnpm run build
ls -la dist/
ls -la dist/assets/
```

---

### TC-02: FastAPI Serves Dashboard at Root

**Objective:** Verify the built dashboard is served correctly at `/`

**Steps:**
1. Ensure dashboard is built (`dashboard/dist/` exists)
2. Start the Amelia server
3. Open browser to `http://localhost:8420/`
4. Verify the dashboard loads

**Expected Result:**
- Browser displays the Amelia Dashboard
- Page title is "Amelia Dashboard"
- Sidebar with "AMELIA" branding visible
- Navigation links present (Active Jobs, Past Runs, Logs)

**Verification Commands:**
```bash
# Start the server
uv run uvicorn amelia.server.main:app --host 0.0.0.0 --port 8420

# In another terminal:
curl -s http://localhost:8420/ | head -20
# Should contain "Amelia Dashboard" in HTML

# Or check content-type:
curl -I http://localhost:8420/
# Should show: content-type: text/html; charset=utf-8
```

---

### TC-03: SPA Client-Side Routing

**Objective:** Verify client-side routes work when served by FastAPI

**Steps:**
1. With server running, navigate to `http://localhost:8420/workflows`
2. Verify page loads (not 404)
3. Navigate to `http://localhost:8420/history`
4. Navigate to `http://localhost:8420/logs`
5. Navigate to `http://localhost:8420/workflows/test-123`
6. Try refreshing the browser on each route

**Expected Result:**
- All routes return 200 and render the dashboard
- Each page shows appropriate content/placeholder
- Browser refresh maintains the current route
- Active navigation link is highlighted in sidebar

**Verification Commands:**
```bash
# Each should return 200 with HTML content
curl -I http://localhost:8420/workflows
curl -I http://localhost:8420/history
curl -I http://localhost:8420/logs
curl -I http://localhost:8420/workflows/some-id
```

---

### TC-04: API Routes Remain Accessible

**Objective:** Verify API endpoints work alongside the dashboard

**Steps:**
1. Test health check endpoint
2. Test API documentation
3. Test a workflow API endpoint

**Expected Result:**
- `/api/health/live` returns JSON `{"status": "alive"}`
- `/api/docs` serves Swagger UI
- API routes return JSON, not HTML

**Verification Commands:**
```bash
# Health check
curl http://localhost:8420/api/health/live
# Expected: {"status":"alive"}

# Check API docs accessible
curl -I http://localhost:8420/api/docs
# Expected: 200 OK

# Unknown API route returns 404 JSON, not dashboard HTML
curl http://localhost:8420/api/nonexistent
# Expected: 404 JSON error, NOT HTML
```

---

### TC-05: Unknown API Routes Return 404

**Objective:** Verify unknown `/api/` routes don't fall through to SPA

**Steps:**
1. Request a non-existent API endpoint
2. Check response is JSON 404, not HTML

**Expected Result:**
- Response status is 404
- Response body is JSON error, not index.html

**Verification Commands:**
```bash
curl -w "\n%{http_code}\n" http://localhost:8420/api/does-not-exist
# Should return 404 JSON, not 200 HTML
```

---

### TC-06: Static Assets Served Correctly

**Objective:** Verify JS/CSS assets load properly

**Steps:**
1. Open dashboard in browser
2. Open DevTools Network tab
3. Refresh the page
4. Check all assets load with 200 status

**Expected Result:**
- All `.js` files load successfully
- All `.css` files load successfully
- No 404 errors in Network tab
- Assets served from `/assets/` path

**Verification Commands:**
```bash
# List built assets
ls dashboard/dist/assets/

# Check one asset is accessible (filename will vary)
curl -I http://localhost:8420/assets/index-*.js
```

---

### TC-07: Dashboard Not Built Fallback

**Objective:** Verify helpful message when dashboard is not built

**Steps:**
1. Stop the server
2. Remove or rename `dashboard/dist/`
3. Start the server
4. Request root URL

**Expected Result:**
- Response is JSON with helpful message
- Message includes build instructions
- API routes still work normally

**Verification Commands:**
```bash
# Remove built dashboard
mv dashboard/dist dashboard/dist.bak

# Restart server and test
curl http://localhost:8420/
# Expected: {"message":"Dashboard not built","instructions":"Run 'cd dashboard && pnpm run build' to build the dashboard"}

# Restore
mv dashboard/dist.bak dashboard/dist
```

---

### TC-08: Navigation UI Components

**Objective:** Verify sidebar navigation works correctly

**Steps:**
1. Open dashboard in browser
2. Click "Active Jobs" link
3. Verify URL changes to `/workflows`
4. Click "Past Runs" link
5. Click "Logs" link
6. Verify active state highlighting changes

**Expected Result:**
- Clicking navigation links updates URL
- Active link is visually highlighted
- Page content changes appropriately
- Browser back/forward buttons work

---

### TC-09: Error Boundary Display

**Objective:** Verify error boundary handles routing errors

**Steps:**
1. Manually trigger an error (modify a page component temporarily)
2. Navigate to that page
3. Verify error boundary catches and displays error

**Expected Result:**
- Error boundary displays friendly error message
- "Go Home" and "Go Back" buttons present
- In development mode, error stack trace shown

---

### TC-10: Development Server Proxy

**Objective:** Verify Vite dev server proxies API requests correctly

**Steps:**
1. Start the FastAPI server on port 8420
2. In another terminal, start dashboard dev server
3. Open `http://localhost:3000`
4. Verify API calls work through proxy

**Expected Result:**
- Dashboard loads at `http://localhost:3000`
- API requests to `/api/*` proxied to FastAPI
- Hot reloading works for frontend changes

**Verification Commands:**
```bash
# Terminal 1: Start FastAPI
uv run uvicorn amelia.server.main:app --port 8420

# Terminal 2: Start dashboard dev server
cd dashboard && pnpm run dev

# Test proxy works (from dev server port)
curl http://localhost:3000/api/health/live
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the servers (Ctrl+C in each terminal)

# Optional: Remove build artifacts
rm -rf dashboard/dist

# Rebuild if needed for future tests
cd dashboard && pnpm run build
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | Dashboard Build Process | [ ] Pass / [ ] Fail | |
| TC-02 | FastAPI Serves Dashboard at Root | [ ] Pass / [ ] Fail | |
| TC-03 | SPA Client-Side Routing | [ ] Pass / [ ] Fail | |
| TC-04 | API Routes Remain Accessible | [ ] Pass / [ ] Fail | |
| TC-05 | Unknown API Routes Return 404 | [ ] Pass / [ ] Fail | |
| TC-06 | Static Assets Served Correctly | [ ] Pass / [ ] Fail | |
| TC-07 | Dashboard Not Built Fallback | [ ] Pass / [ ] Fail | |
| TC-08 | Navigation UI Components | [ ] Pass / [ ] Fail | |
| TC-09 | Error Boundary Display | [ ] Pass / [ ] Fail | |
| TC-10 | Development Server Proxy | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Start with TC-01** - Build must succeed before other tests
2. **Keep server running** - TC-02 through TC-06 require FastAPI running
3. **Document asset filenames** - JS/CSS files have hashed names, note actual names
4. **Capture screenshots** - If using playwright/browser automation
5. **Test TC-07 last** - Requires removing build artifacts

### Programmatic Testing Example:

```python
import httpx

async def test_dashboard_routes():
    async with httpx.AsyncClient(base_url="http://localhost:8420") as client:
        # TC-02: Root serves HTML
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

        # TC-03: SPA routes
        for path in ["/workflows", "/history", "/logs"]:
            r = await client.get(path)
            assert r.status_code == 200
            assert "text/html" in r.headers.get("content-type", "")

        # TC-04: API routes
        r = await client.get("/api/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "alive"}
```

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **Dashboard Infrastructure** (`dashboard/`):
   - Vite + React + TypeScript project setup
   - pnpm package management with lockfile
   - Build output to `dashboard/dist/`

2. **FastAPI Static Serving** (`amelia/server/main.py`):
   - Static file mounting for `/assets`
   - SPA fallback route for client-side routing
   - Conditional behavior when dashboard not built

3. **UI Components** (`dashboard/src/components/`):
   - Layout with sidebar navigation
   - Error boundaries for route errors
   - shadcn/ui base components (Button, Card, etc.)
   - AI-themed components (confirmation, queue, loader)

4. **Routing** (`dashboard/src/router.tsx`):
   - React Router v7 configuration
   - Lazy-loaded pages
   - Redirect handling for root and unknown paths
