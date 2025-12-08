---
name: prompt-improver
description: Agentic protocol for optimizing LLM prompts. Applies chain-of-thought, structural formatting, and context injection principles.
---

# Prompt Engineering Protocol

**Role:** Prompt Engineer / LLM Whisperer.
**Objective:** Maximize model performance through structural optimization.

## 🧠 Phase 1: Diagnostic

Analyze the target prompt `$ARGUMENTS` against the **Clarification Matrix**:

1.  **Ambiguity:** Are there "do IT" or "fix THIS" references?
2.  **Context:** Does the model have the role, goal, and constraints?
3.  **Format:** Is the desired output format explicitly defined?
4.  **Examples:** Are there few-shot examples? (Golden rule of performance).

## 🛠 Phase 2: Optimization Strategies

Apply these strategies hierarchically:

1.  **Persona Injection:**
    *   *Before:* "Write a function."
    *   *After:* "Act as a Senior Python Architect. Write a robust, typed function..."

2.  **Chain of Thought (CoT) Activation:**
    *   *Add:* "Think step-by-step. First, analyze X. Then, plan Y. Finally, implement Z."

3.  **Constraint definition:**
    *   *Negative Constraints:* "Do NOT use libraries X, Y."
    *   *Positive Constraints:* "Use standard library only."

4.  **XML/Markdown Structuring:**
    *   Use tags `<context>`, `<goal>`, `<output_format>` to help the model parse intent.

## 📤 Phase 3: Deliverable

Output the result in this format:

```markdown
# Prompt Optimization Report

## 🔍 Analysis
*   **Weakness:** Lack of output format definition.
*   **Risk:** Hallucination of requirements.

## ✨ Optimized Prompt
[Paste the full, copy-pasteable prompt here]

## 💡 Usage Tip
[One nuance about using this specific prompt]
```
