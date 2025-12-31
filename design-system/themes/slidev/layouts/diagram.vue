<!--
  DIAGRAM LAYOUT
  Extends Slidev's center layout for diagrams with Amelia styling.
  Centers content vertically and horizontally, ideal for large diagrams.

  Usage:
  ---
  layout: diagram
  class: dark  # or 'light'
  ---

  # Optional Title

  ```mermaid
  flowchart LR
    A --> B
  ```
-->

<template>
  <div class="slidev-layout diagram">
    <slot />
  </div>
</template>

<style scoped>
.diagram {
  /* Center content */
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 3rem 4rem;
  background-color: var(--background);
  color: var(--foreground);
}

/* Optional title - minimal styling to not compete with diagram */
.diagram :deep(h1) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
  font-size: var(--font-size-2xl);
  line-height: var(--line-height-2xl);
  color: var(--muted-foreground);
  text-align: center;
  margin-top: 0;
  margin-bottom: 2rem;
}

/* Diagram container - ensure diagrams scale properly */
.diagram :deep(.mermaid),
.diagram :deep(.d2),
.diagram :deep(svg),
.diagram :deep(img) {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
}

/* Caption or source note below diagram */
.diagram :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-sm);
  color: var(--muted-foreground);
  text-align: center;
  margin-top: 1.5rem;
  margin-bottom: 0;
}

/* Code blocks (for inline diagram code examples) */
.diagram :deep(pre) {
  max-width: 90%;
  background-color: var(--card);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  overflow-x: auto;
}

</style>
