# Unified Database Configuration E2E Testing Plan

**Branch:** `feat/unify-config-database-307`
**Feature:** Database-backed profiles and server settings with dashboard UI

## Overview

This PR migrates profile and server settings from `settings.amelia.yaml` to SQLite database storage, adding:

1. **CLI configuration commands** (`amelia config profile`, `amelia config server`)
2. **Settings API endpoints** (`/api/settings`, `/api/profiles`)
3. **Dashboard settings pages** (Profiles management, Server configuration)
4. **First-run interactive profile setup**

The test plan validates the complete user journey through both CLI and dashboard interfaces.

---

## Prerequisites

### Environment Setup

```bash
# 1. Navigate to test repository
cd /Users/ka/github/existential-birds/test_repo_c

# 2. Install Python dependencies (from amelia repo)
cd /Users/ka/github/existential-birds/amelia
uv sync

# 3. Start the backend server with fresh database
export AMELIA_DATABASE_PATH=/tmp/amelia-test-e2e.db
rm -f /tmp/amelia-test-e2e.db  # Ensure clean state
uv run amelia server --reload &

# Server runs on http://localhost:8420
# Dashboard is served at same port
```

### Testing Tools

- **Chrome DevTools MCP**: For browser automation of dashboard testing
- **LLM Driver**: `qwen/qwen3-coder-flash` configured via profiles
- **Test Repository**: `/Users/ka/github/existential-birds/test_repo_c`

---

## Test Scenarios

### TC-01: CLI Profile Creation with Interactive First-Run

**Objective:** Verify first-run interactive setup creates a valid profile

**Steps:**
1. Ensure no profiles exist in the database
2. Run `amelia config profile list` to confirm empty state
3. Run `amelia config profile create` without arguments to trigger interactive mode
4. Enter profile details when prompted:
   - Name: `test-qwen`
   - Driver: `api:openrouter`
   - Model: `qwen/qwen3-coder-flash`
   - Tracker: `noop`
   - Working directory: `/Users/ka/github/existential-birds/test_repo_c`

**Expected Result:**
- Interactive prompts appear for required fields
- Profile is created and visible in `amelia config profile list`
- Profile shows correct values in `amelia config profile show test-qwen`

**Verification Commands:**
```bash
cd /Users/ka/github/existential-birds/amelia
export AMELIA_DATABASE_PATH=/tmp/amelia-test-e2e.db

# Verify empty state
uv run amelia config profile list

# Create profile with full options (non-interactive for automation)
uv run amelia config profile create test-qwen \
  --driver api:openrouter \
  --model qwen/qwen3-coder-flash \
  --tracker noop \
  --working-dir /Users/ka/github/existential-birds/test_repo_c \
  --activate

# Verify creation
uv run amelia config profile list
uv run amelia config profile show test-qwen
```

---

### TC-02: CLI Server Settings Management

**Objective:** Verify server settings can be viewed and modified via CLI

**Steps:**
1. View current server settings with `amelia config server show`
2. Update `max_concurrent` setting to 10
3. Update `log_retention_days` setting to 14
4. Verify changes persist

**Expected Result:**
- Server settings display with default values initially
- Updates are applied and visible in subsequent `show` commands
- Settings persist across CLI invocations

**Verification Commands:**
```bash
cd /Users/ka/github/existential-birds/amelia
export AMELIA_DATABASE_PATH=/tmp/amelia-test-e2e.db

# View current settings
uv run amelia config server show

# Update settings
uv run amelia config server set max_concurrent 10
uv run amelia config server set log_retention_days 14

# Verify updates
uv run amelia config server show
```

---

### TC-03: Dashboard Navigation to Settings

**Objective:** Verify settings pages are accessible via dashboard navigation

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420`
2. Click on "Settings" in the sidebar navigation
3. Verify redirect to `/settings/profiles`
4. Click on "Server" tab
5. Verify navigation to `/settings/server`

**Expected Result:**
- Settings link visible in sidebar
- Tab navigation works between Profiles and Server pages
- URLs update correctly (`/settings/profiles`, `/settings/server`)
- Page content loads without errors

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to dashboard
await page.goto('http://localhost:8420');

// Find and click Settings link in sidebar
await page.click('a[href="/settings"]');

// Verify URL changed to profiles page
await page.waitForURL('**/settings/profiles');

// Click Server tab
await page.click('a[href="/settings/server"]');

// Verify URL changed to server page
await page.waitForURL('**/settings/server');
```

---

### TC-04: Dashboard Profile List Display

**Objective:** Verify profile cards display correctly in the dashboard

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Verify profile card for `test-qwen` is displayed
3. Verify card shows correct driver, model, and active status
4. Verify driver type badge (API/CLI) displays correctly

**Expected Result:**
- Profile card shows profile name `test-qwen`
- Driver shows `api:openrouter`
- Model shows `qwen/qwen3-coder-flash`
- Active indicator is visible (if activated)
- Driver type badge shows "API" with appropriate color

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to profiles page
await page.goto('http://localhost:8420/settings/profiles');

// Wait for profile cards to load
await page.waitForSelector('[data-testid="profile-card"]');

// Verify profile content
const profileCard = await page.locator('text=test-qwen');
expect(await profileCard.isVisible()).toBe(true);

// Verify driver and model are shown
expect(await page.locator('text=api:openrouter').isVisible()).toBe(true);
expect(await page.locator('text=qwen/qwen3-coder-flash').isVisible()).toBe(true);
```

---

### TC-05: Dashboard Profile Creation Modal

**Objective:** Verify profile can be created through dashboard modal

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Click "Create Profile" button
3. Fill in profile form:
   - Name: `test-cli-profile`
   - Driver: `cli:claude`
   - Model: `claude-sonnet-4-20250514`
   - Validator Model: `claude-sonnet-4-20250514`
   - Tracker: `github`
   - Working Directory: `/Users/ka/github/existential-birds/test_repo_c`
4. Click "Save" button
5. Verify new profile appears in the list

**Expected Result:**
- Modal opens with empty form
- Form validates required fields
- Profile is created on save
- Modal closes and profile list refreshes
- New profile card appears in the grid

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate and open modal
await page.goto('http://localhost:8420/settings/profiles');
await page.click('button:has-text("Create Profile")');

// Wait for modal to open
await page.waitForSelector('[role="dialog"]');

// Fill form fields
await page.fill('input[name="id"]', 'test-cli-profile');
await page.fill('input[name="driver"]', 'cli:claude');
await page.fill('input[name="model"]', 'claude-sonnet-4-20250514');
await page.fill('input[name="validator_model"]', 'claude-sonnet-4-20250514');
await page.selectOption('select[name="tracker"]', 'github');
await page.fill('input[name="working_dir"]', '/Users/ka/github/existential-birds/test_repo_c');

// Submit
await page.click('button:has-text("Save")');

// Verify profile appears
await page.waitForSelector('text=test-cli-profile');
```

---

### TC-06: Dashboard Profile Edit Modal

**Objective:** Verify existing profile can be edited through dashboard

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Find the `test-qwen` profile card
3. Click the edit button (pencil icon)
4. Modify the model to `qwen/qwen3-32b`
5. Click "Save" button
6. Verify profile card shows updated model

**Expected Result:**
- Edit modal opens with pre-filled values
- Changes can be made to editable fields
- Profile ID field is disabled (not editable)
- Save updates the profile and refreshes the list

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to profiles
await page.goto('http://localhost:8420/settings/profiles');

// Find and click edit button on test-qwen card
await page.locator('[data-testid="profile-card"]:has-text("test-qwen") button[aria-label="Edit"]').click();

// Wait for modal with pre-filled data
await page.waitForSelector('[role="dialog"]');
expect(await page.inputValue('input[name="id"]')).toBe('test-qwen');

// Update model
await page.fill('input[name="model"]', 'qwen/qwen3-32b');

// Save and verify
await page.click('button:has-text("Save")');
await page.waitForSelector('text=qwen/qwen3-32b');
```

---

### TC-07: Dashboard Profile Filter and Search

**Objective:** Verify profile filtering by driver type and search

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Ensure both `test-qwen` (API) and `test-cli-profile` (CLI) exist
3. Click "API" filter toggle
4. Verify only API profiles are shown
5. Click "CLI" filter toggle
6. Verify only CLI profiles are shown
7. Click "All" filter toggle
8. Type "qwen" in search box
9. Verify only matching profiles are shown

**Expected Result:**
- Filter toggles correctly show/hide profiles by driver type
- Search filters profiles by name substring (case-insensitive)
- Filters and search can be combined
- Empty state message shows when no matches

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to profiles
await page.goto('http://localhost:8420/settings/profiles');

// Click API filter
await page.click('button:has-text("API")');
await page.waitForTimeout(300); // Allow filter to apply

// Verify CLI profile is hidden
expect(await page.locator('text=test-cli-profile').isVisible()).toBe(false);
expect(await page.locator('text=test-qwen').isVisible()).toBe(true);

// Click CLI filter
await page.click('button:has-text("CLI")');
await page.waitForTimeout(300);

// Verify API profile is hidden
expect(await page.locator('text=test-qwen').isVisible()).toBe(false);
expect(await page.locator('text=test-cli-profile').isVisible()).toBe(true);

// Test search
await page.click('button:has-text("All")');
await page.fill('input[placeholder*="Search"]', 'qwen');
await page.waitForTimeout(300);

expect(await page.locator('text=test-qwen').isVisible()).toBe(true);
expect(await page.locator('text=test-cli-profile').isVisible()).toBe(false);
```

---

### TC-08: Dashboard Profile Activation

**Objective:** Verify profile can be activated via dashboard

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Find a non-active profile card
3. Click the "Activate" button
4. Verify activation success toast
5. Verify profile card shows active indicator
6. Verify previously active profile is now inactive

**Expected Result:**
- Activate button visible on non-active profiles
- Clicking activate shows success toast
- Active profile card displays active badge/indicator
- Only one profile can be active at a time

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to profiles
await page.goto('http://localhost:8420/settings/profiles');

// Click activate on a different profile
await page.locator('[data-testid="profile-card"]:has-text("test-cli-profile") button:has-text("Activate")').click();

// Wait for toast notification
await page.waitForSelector('text=now active');

// Verify active indicator moved
const cliCard = page.locator('[data-testid="profile-card"]:has-text("test-cli-profile")');
expect(await cliCard.locator('text=Active').isVisible()).toBe(true);
```

---

### TC-09: Dashboard Server Settings Form

**Objective:** Verify server settings can be viewed and modified in dashboard

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/server`
2. Verify settings form displays current values
3. Modify `max_concurrent` to 15
4. Modify `stream_tool_results` toggle to enabled
5. Click "Save" button
6. Verify success toast
7. Refresh page and verify values persist

**Expected Result:**
- Form displays all server settings with current values
- Number inputs allow valid ranges
- Toggle switches work for boolean settings
- Save persists changes to database
- Changes survive page refresh

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to server settings
await page.goto('http://localhost:8420/settings/server');

// Wait for form to load
await page.waitForSelector('form');

// Verify current values loaded (from TC-02)
expect(await page.inputValue('input[name="max_concurrent"]')).toBe('10');

// Update values
await page.fill('input[name="max_concurrent"]', '15');
await page.click('button[role="switch"][name="stream_tool_results"]'); // Toggle

// Save
await page.click('button:has-text("Save")');

// Verify success toast
await page.waitForSelector('text=Settings saved');

// Refresh and verify persistence
await page.reload();
expect(await page.inputValue('input[name="max_concurrent"]')).toBe('15');
```

---

### TC-10: Dashboard Profile Deletion

**Objective:** Verify profile can be deleted with confirmation

**Browser Automation Steps:**
1. Navigate to `http://localhost:8420/settings/profiles`
2. Find the `test-cli-profile` card
3. Click the delete button (trash icon)
4. Accept the confirmation dialog
5. Verify profile is removed from list
6. Verify deletion via CLI

**Expected Result:**
- Delete button visible on profile cards
- Confirmation dialog appears before deletion
- Profile is removed from list after confirmation
- CLI confirms profile no longer exists

**Verification (Chrome DevTools MCP):**
```javascript
// Navigate to profiles
await page.goto('http://localhost:8420/settings/profiles');

// Set up dialog handler for confirm
page.on('dialog', dialog => dialog.accept());

// Click delete on test-cli-profile
await page.locator('[data-testid="profile-card"]:has-text("test-cli-profile") button[aria-label="Delete"]').click();

// Wait for profile to be removed
await page.waitForSelector('text=test-cli-profile', { state: 'hidden' });

// Verify via CLI (separate terminal)
// uv run amelia config profile show test-cli-profile  # Should show "not found"
```

---

### TC-11: API Endpoint Direct Testing

**Objective:** Verify API endpoints work correctly for programmatic access

**Steps:**
1. GET `/api/profiles` - list all profiles
2. POST `/api/profiles` - create a new profile
3. GET `/api/profiles/{id}` - get specific profile
4. PUT `/api/profiles/{id}` - update profile
5. DELETE `/api/profiles/{id}` - delete profile
6. GET `/api/settings` - get server settings
7. PUT `/api/settings` - update server settings

**Verification Commands:**
```bash
# List profiles
curl http://localhost:8420/api/profiles

# Create profile
curl -X POST http://localhost:8420/api/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "id": "api-test",
    "driver": "api:openrouter",
    "model": "qwen/qwen3-coder-flash",
    "validator_model": "qwen/qwen3-coder-flash",
    "tracker": "noop",
    "working_dir": "/tmp"
  }'

# Get profile
curl http://localhost:8420/api/profiles/api-test

# Update profile
curl -X PUT http://localhost:8420/api/profiles/api-test \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen/qwen3-32b"}'

# Delete profile
curl -X DELETE http://localhost:8420/api/profiles/api-test

# Get server settings
curl http://localhost:8420/api/settings

# Update server settings
curl -X PUT http://localhost:8420/api/settings \
  -H "Content-Type: application/json" \
  -d '{"max_concurrent": 20}'
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server
pkill -f "amelia server"

# Remove test database
rm -f /tmp/amelia-test-e2e.db

# Reset any environment variables
unset AMELIA_DATABASE_PATH
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | CLI Profile Creation | [ ] Pass / [ ] Fail | |
| TC-02 | CLI Server Settings | [ ] Pass / [ ] Fail | |
| TC-03 | Dashboard Navigation | [ ] Pass / [ ] Fail | |
| TC-04 | Profile List Display | [ ] Pass / [ ] Fail | |
| TC-05 | Profile Creation Modal | [ ] Pass / [ ] Fail | |
| TC-06 | Profile Edit Modal | [ ] Pass / [ ] Fail | |
| TC-07 | Profile Filter/Search | [ ] Pass / [ ] Fail | |
| TC-08 | Profile Activation | [ ] Pass / [ ] Fail | |
| TC-09 | Server Settings Form | [ ] Pass / [ ] Fail | |
| TC-10 | Profile Deletion | [ ] Pass / [ ] Fail | |
| TC-11 | API Direct Testing | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan with Chrome DevTools MCP:

1. **Start server first** - Run the backend server setup commands before any browser tests
2. **Execute CLI tests (TC-01, TC-02)** - These create initial data for dashboard tests
3. **Execute browser tests sequentially** - TC-03 through TC-10 depend on accumulated state
4. **Use Chrome DevTools MCP** - For browser automation steps
5. **Capture screenshots** - On failures, capture page state for debugging
6. **Use `qwen/qwen3-coder-flash`** - This model is configured in TC-01 profile

### Chrome DevTools MCP Setup:

```javascript
// Initialize browser session
const browser = await puppeteer.launch({ headless: false });
const page = await browser.newPage();

// Set viewport for consistent testing
await page.setViewport({ width: 1280, height: 800 });

// Add delay helper for visual testing
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
```

### Error Handling:

- If a test fails, capture the current URL and page HTML
- Log network errors from DevTools
- Continue to next test unless it depends on failed test state

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **Database Schema** (`amelia/server/database/`):
   - New `server_settings` table stores configuration
   - New `profiles` table replaces YAML profiles
   - Migration from env vars to database defaults

2. **CLI Commands** (`amelia/cli/config.py`):
   - `amelia config profile list|show|create|update|delete|activate`
   - `amelia config server show|set`
   - Interactive first-run profile setup

3. **API Endpoints** (`amelia/server/routes/settings.py`):
   - `GET/PUT /api/settings` for server configuration
   - `GET/POST/PUT/DELETE /api/profiles` for profile CRUD
   - `POST /api/profiles/{id}/activate` for activation

4. **Dashboard Pages** (`dashboard/src/pages/`):
   - `SettingsProfilesPage.tsx` - Profile management UI
   - `SettingsServerPage.tsx` - Server configuration UI
   - `ProfileCard.tsx` - Individual profile display
   - `ProfileEditModal.tsx` - Create/edit profile form
   - `ServerSettingsForm.tsx` - Server settings form
