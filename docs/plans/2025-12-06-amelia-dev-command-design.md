# Design: `amelia dev` Command

## Overview

A unified development command that starts both the Python API server and the React dashboard with a single command, providing a polished developer experience with vivid, color-coded log output.

## Behavior by Context

| Context | Server | Dashboard | Hot Reload |
|---------|--------|-----------|------------|
| **Amelia repo** | uvicorn | Vite dev server | Yes |
| **Other repo** | uvicorn | Bundled static files | No |

### Detection Logic

Check if current working directory contains all of:
- `amelia/` directory (Python package)
- `dashboard/package.json`
- `.git/` directory

All three present = **dev mode**. Otherwise = **user mode**.

## Visual Design

### Color Palette

All log output uses the Amelia brand palette:

| Color | Hex | Usage |
|-------|-----|-------|
| NAVY | `#0a2463` | `[server]` prefix |
| GOLD | `#ffc857` | `[dashboard]` prefix |
| CREAM | `#eff8e2` | Primary log text |
| MOSS | `#88976b` | Timestamps, secondary info |
| RUST | `#a0311c` | Errors, warnings |
| GRAY | `#6d726a` | Muted/debug output |

### Log Output Example

```
[server]    Starting uvicorn on http://localhost:8000
[dashboard] Starting vite on http://localhost:5173
[server]    Application startup complete
[dashboard] VITE ready in 1.2s
[server]    GET /api/health 200 OK
```

No emojis - pure color-driven visual hierarchy.

## Implementation

### New Files

**`amelia/server/dev.py`** - Dev command implementation

```python
dev_app = typer.Typer()

@dev_app.callback(invoke_without_command=True)
def dev():
    1. Detect mode (amelia repo vs other)
    2. If dev mode:
       - Check pnpm/node availability
       - Auto-install if node_modules missing
       - Start Vite subprocess
    3. Start uvicorn (in-process or subprocess)
    4. Stream both outputs with colored prefixes
    5. Handle signals (SIGINT, SIGTERM)
    6. On exit/crash, cleanup both processes
```

### Process Management

- **Vite**: `asyncio.subprocess` for non-blocking stdout/stderr streaming
- **Uvicorn**: Run via `uvicorn.run()` in thread or subprocess
- **Log streaming**: Read lines async, apply color prefix, write to Rich console

### Bundling the Dashboard

**Build process:**
1. `cd dashboard && pnpm build` outputs to `dashboard/dist/`
2. Copy to `amelia/server/static/`
3. Include in wheel via `pyproject.toml`

**`pyproject.toml` changes:**
```toml
[tool.hatch.build.targets.wheel]
packages = ["amelia"]
artifacts = ["amelia/server/static/*"]
```

**Server change:** Mount `StaticFiles` at `/` pointing to bundled assets.

## CLI Interface

```
amelia dev [OPTIONS]

Options:
  -p, --port INT      Server port (default: 8000)
  --no-dashboard      Server only, skip dashboard
  --bind-all          Bind to 0.0.0.0 (network access)
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `pnpm` not installed (dev mode) | Error: "pnpm required for dev mode. Install: npm i -g pnpm" |
| `node_modules` missing | Auto-run `pnpm install`, show progress |
| Vite fails to start | Show error in RUST color, exit both processes |
| Server fails to start | Show error in RUST color, kill Vite, exit |
| Port already in use | Clear message with port number, suggest `--port` |
| Ctrl+C | Graceful shutdown, kill both, exit 0 |

### Process Failure Policy

**Exit both immediately** - If either process dies, kill the other and exit with error code. In dev mode, a clean slate on failure is better than debugging partial states.

## Auto-Install (Dev Mode Only)

When `dashboard/node_modules/` is missing:
1. Detect missing dependencies
2. Print: `[dashboard] Installing dependencies...`
3. Run `pnpm install` with output streamed
4. On success, continue to start Vite
5. On failure, exit with clear error

## Future Considerations

- `--open` flag to auto-open browser
- Dashboard port configuration (`--dashboard-port`)
- Verbose mode for debugging process management
