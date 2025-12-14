# Amelia Orchestrator Flow - Mermaid Example

Demonstrates the core orchestrator pattern with human-in-the-loop gate using Mermaid flowchart.

## Orchestrator Flow Diagram

```mermaid
%%{init: { "theme": "base", "themeVariables": { "primaryColor": "#1F332E", "primaryTextColor": "#EFF8E2", "primaryBorderColor": "#FFC857", "secondaryColor": "#4A5C54", "tertiaryColor": "#0D1A12", "lineColor": "#88A896", "fontFamily": "Source Sans 3" } } }%%
%% Note: For production use, consider referencing the design system's Mermaid theme config
%% from design-system/themes/mermaid/amelia-dark.md instead of repeating themeVariables inline
flowchart LR
    %% Nodes
    Issue([Issue])
    Architect[Architect]
    Approval{Human Approval}
    Developer[Developer]
    Reviewer[Reviewer]
    Done([Done])

    %% Main flow
    Issue -->|Fetch & Analyze| Architect
    Architect -->|Generate Plan| Approval

    %% Human-in-the-loop gate pattern
    Approval -->|Approved| Developer
    Approval -.->|Rejected| Issue

    %% Developer-Reviewer loop
    Developer -->|Execute Tasks| Reviewer
    Reviewer -->|Changes Approved| Done

    %% Feedback loop
    Reviewer -.->|Needs Revision| Developer

    %% Styling for emphasis
    class Approval gate
    class Issue,Done terminal

    classDef gate fill:#FFC857,stroke:#FFC857,color:#0D1A12,stroke-width:3px
    classDef terminal fill:#5B8A72,stroke:#FFC857,color:#EFF8E2,stroke-width:2px
```

## Pattern Explanation

This diagram shows the core Amelia orchestrator flow:

1. **Issue**: Entry point for the workflow
2. **Architect**: Analyzes the issue and generates an execution plan
3. **Human Approval** (Gate): Human-in-the-loop decision point
   - If approved, proceeds to Developer
   - If rejected, loops back to Issue for refinement
4. **Developer**: Executes tasks from the plan
5. **Reviewer**: Reviews the changes
   - If approved, marks as Done
   - If revision needed, loops back to Developer
6. **Done**: Terminal state indicating successful completion

The diamond shape for "Human Approval" emphasizes the gate pattern where human oversight is required before proceeding with automated execution.
