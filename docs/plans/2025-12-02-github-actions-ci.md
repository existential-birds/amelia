# GitHub Actions CI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add GitHub Actions CI workflow to run linting, type checking, and tests on push/PR.

**Architecture:** Single sequential job running lint → type check → tests. Uses official `astral-sh/setup-uv` action with caching for fast dependency installation. Excludes e2e tests per project requirements.

**Tech Stack:** GitHub Actions, uv, ruff, mypy, pytest

---

## Task 1: Create GitHub Actions Workflow Directory

**Files:**
- Create: `.github/workflows/` (directory)

**Step 1: Create the directory structure**

```bash
mkdir -p .github/workflows
```

**Step 2: Verify directory exists**

Run: `ls -la .github/`
Expected: `workflows` directory listed

**Step 3: Commit**

```bash
git add .github
git commit -m "chore: create .github/workflows directory"
```

---

## Task 2: Create CI Workflow File

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create the workflow file**

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  check:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Lint with ruff
        run: uv run ruff check amelia tests

      - name: Type check with mypy
        run: uv run mypy amelia

      - name: Run tests
        run: uv run pytest tests/unit tests/integration -v
```

**Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No output (valid YAML)

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for linting, type checking, and tests"
```

---

## Task 3: Verify CI Locally (Optional Dry Run)

**Files:**
- None (verification only)

**Step 1: Run the same commands locally to ensure they pass**

```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest tests/unit tests/integration -v
```

Expected: All commands pass (exit code 0)

**Step 2: Verify git status**

Run: `git status`
Expected: Clean working tree or only the new CI files

---

## Task 4: Push and Verify CI Runs

**Files:**
- None (verification only)

**Step 1: Push changes**

```bash
git push origin HEAD
```

**Step 2: Verify CI workflow triggered**

- Go to GitHub repository → Actions tab
- Confirm workflow is running or completed successfully

---

## Summary

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `mkdir -p .github/workflows` | Create directory structure |
| 2 | Create `ci.yml` | Define CI workflow |
| 3 | Local verification | Ensure commands pass |
| 4 | Push to GitHub | Trigger CI |

**Total files created:** 1 (`.github/workflows/ci.yml`)

**CI triggers:**
- Push to `main` or `master` branch
- Pull requests targeting `main` or `master`

**CI steps:**
1. Checkout code
2. Set up uv with caching
3. Set up Python 3.12
4. Install dependencies (`uv sync`)
5. Lint (`uv run ruff check`)
6. Type check (`uv run mypy`)
7. Run unit + integration tests (`uv run pytest`)
