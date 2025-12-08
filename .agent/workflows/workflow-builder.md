---
name: workflow-builder
description: Agentic protocol for designing and creating new agent workflows. Enforces the "Gemini 3 Pro" standard.
---

# Workflow Builder Protocol

**Role:** Process Architect.
**Objective:** Codify best practices into reusable, deterministic agent workflows.

## 🏗 Phase 1: Architecture

Before writing, define the core constraints:

1.  **Scope definition:**
    *   **Input:** What triggers this? (e.g., "User asks to optimize X").
    *   **Output:** What is the tangible deliverable? (e.g., "A specific file change", "A report").

2.  **Role Assignment:**
    *   Who is the agent acting as? (e.g., "Senior QA Engineer", "Security Auditor").
    *   *Why:* Personas ground the LLM's reasoning style.

## 📝 Phase 2: Drafting the Protocol

Create a new file in `.agent/workflows/{kebab-case-name}.md`.

**Structure Requirement (The Standard):**

1.  **Frontmatter:**
    *   `name`: Short ID.
    *   `description`: One-line summary of *what* and *why*.

2.  **Header:**
    *   `# Title`
    *   `**Role:** ...`
    *   `**Objective:** ...`

3.  **Phased Execution:**
    *   **Phase 1: Analysis/Context:** Gather info *before* acting.
    *   **Phase 2: Execution:** The core task loops.
    *   **Phase 3: Verification:** Explicit checks (e.g., "Run build", "Grep for usage").

## 🧪 Phase 3: Rigor Injection

Apply these rules to your draft:

*   **Rule of Verification:** Every claim requires a tool call. (e.g., "Don't assume strict mode is on. Check tsconfig.").
*   **Rule of Explicitness:** No "Verify it works". Use "Verify X returns Y".
*   **Rule of Safety:** if destructive (delete/overwrite), require a backup or check.

## 🚀 Phase 4: Deployment

1.  **Save:** Write to `.agent/workflows/{name}.md`.
2.  **Test:** Run the workflow against a sample input.
3.  **Refine:** Did the agent get stuck? Did it hallucinate steps? simplifying instructions.
