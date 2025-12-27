# Plan: Update Documentation for OpenRouter Driver Support

**Issue**: Follow-up to #131 (feat: Add OpenRouter agentic API driver support)
**Date**: 2025-12-22
**Status**: Pending (blocked on #131 completion)

## Summary

Update VitePress documentation to reflect the new `api:openrouter` driver type and agentic execution capabilities added in issue #131.

## Tasks

### Task 1: Update Data Model Reference

**File**: `docs/site/architecture/data-model.md`

**Changes**:
- Line 9: Add `"api:openrouter"` to `DriverType` literal definition

**Before**:
```
| `DriverType` | `"cli:claude" \| "api:openai" \| "cli" \| "api"` | LLM driver type. |
```

**After**:
```
| `DriverType` | `"cli:claude" \| "api:openai" \| "api:openrouter" \| "cli" \| "api"` | LLM driver type. |
```

---

### Task 2: Update Configuration Guide

**File**: `docs/site/guide/configuration.md`

**Changes**:

1. **Driver table (lines 70-76)**: Add `api:openrouter` row

   | Value | Description | Requirements | Notes |
   |-------|-------------|--------------|-------|
   | `api:openrouter` | OpenRouter API calls | `OPENROUTER_API_KEY` env var | Multi-model routing, agentic execution |

2. **Environment variables section (after line 190)**: Add OpenRouter section

   ```markdown
   ### OpenRouter API Driver

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `OPENROUTER_API_KEY` | Yes | Your OpenRouter API key |
   ```

3. **Validation section (line 214)**: Update valid driver list

   Change from:
   > Driver values must be one of: `api`, `api:openai`, `cli`, `cli:claude`

   To:
   > Driver values must be one of: `api`, `api:openai`, `api:openrouter`, `cli`, `cli:claude`

4. **Troubleshooting section (lines 293-294)**: Update "Driver not recognized"

   Change from:
   > Valid driver values are: `api`, `api:openai`, `cli`, `cli:claude`

   To:
   > Valid driver values are: `api`, `api:openai`, `api:openrouter`, `cli`, `cli:claude`

---

### Task 3: Update Concepts Documentation

**File**: `docs/site/architecture/concepts.md`

**Changes**:

1. **Section title (line 139)**: Change "Why Two Drivers?" to "Driver Options"

2. **Driver table (lines 141-144)**: Add OpenRouter row and update descriptions

   | Driver | Use Case | Requirements |
   |--------|----------|--------------|
   | `api:openai` | Direct OpenAI API, structured outputs | `OPENAI_API_KEY` env var |
   | `api:openrouter` | Multi-model routing, agentic execution | `OPENROUTER_API_KEY` env var |
   | `cli:claude` | Enterprise-friendly, wraps authenticated CLI | `claude` CLI installed |

---

### Task 4: Update Architecture Overview

**File**: `docs/site/architecture/overview.md`

**Changes**:

1. **Mermaid diagram (lines 74-77)**: Add OpenRouter to Drivers subgraph

   ```mermaid
   subgraph Drivers["Drivers"]
       api[OpenAI API]
       openrouter[OpenRouter API]
       claude[Claude CLI]
   end
   ```

2. **File structure (lines 835-839)**: Add new files under `amelia/drivers/api/`

   ```
   ├── drivers/
   │   ├── api/
   │   │   ├── __init__.py
   │   │   ├── openai.py         # OpenAI/OpenRouter via pydantic-ai
   │   │   ├── events.py         # Stream event types for agentic execution
   │   │   └── tools.py          # Agentic tool definitions
   ```

3. **Component table (line 125)**: Update Drivers description

   Change from:
   > LLM abstraction supporting API and CLI backends

   To:
   > LLM abstraction supporting API (OpenAI, OpenRouter) and CLI backends

---

## Verification

After making changes:

1. Run VitePress dev server to verify rendering:
   ```bash
   cd docs/site && pnpm dev
   ```

2. Check all internal links still work

3. Verify Mermaid diagrams render correctly

## Dependencies

- Issue #131 must be merged first (provides the actual implementation to document)
