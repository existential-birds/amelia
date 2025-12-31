<!--
  SCQA LAYOUT
  SCQA framework (4-panel) for executive narratives
  Displays Situation, Complication, Question, and Answer in a 2x2 grid

  Usage:
  Use named slots for each quadrant:
  - ::situation::
  - ::complication::
  - ::question::
  - ::answer::
-->

<script setup lang="ts">
// No props - uses named slots
</script>

<template>
  <div class="slidev-layout scqa">
    <!-- Situation (Top Left) -->
    <div class="scqa-panel scqa-situation">
      <div class="scqa-label">Situation</div>
      <div class="scqa-content">
        <slot name="situation">
          <p class="scqa-placeholder">Add situation content...</p>
        </slot>
      </div>
    </div>

    <!-- Complication (Top Right) -->
    <div class="scqa-panel scqa-complication">
      <div class="scqa-label">Complication</div>
      <div class="scqa-content">
        <slot name="complication">
          <p class="scqa-placeholder">Add complication content...</p>
        </slot>
      </div>
    </div>

    <!-- Question (Bottom Left) -->
    <div class="scqa-panel scqa-question">
      <div class="scqa-label">Question</div>
      <div class="scqa-content">
        <slot name="question">
          <p class="scqa-placeholder">Add question content...</p>
        </slot>
      </div>
    </div>

    <!-- Answer (Bottom Right) -->
    <div class="scqa-panel scqa-answer">
      <div class="scqa-label">Answer</div>
      <div class="scqa-content">
        <slot name="answer">
          <p class="scqa-placeholder">Add answer content...</p>
        </slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scqa {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 2rem;
  height: 100%;
  padding: 3rem;
  background-color: var(--background);
  color: var(--foreground);
}

.scqa-panel {
  display: flex;
  flex-direction: column;
  background-color: var(--card);
  border: 2px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  min-height: 0;
  overflow-y: auto;
  transition: border-color 0.2s ease;
}

.scqa-panel:hover {
  border-color: var(--primary);
}

.scqa-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading-semibold);
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--primary);
}

.scqa-content {
  flex: 1;
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
}

.scqa-placeholder {
  color: var(--muted-foreground);
  font-style: italic;
  margin: 0;
}

/* Specific panel styling */
.scqa-situation {
  grid-column: 1;
  grid-row: 1;
}

.scqa-complication {
  grid-column: 2;
  grid-row: 1;
}

.scqa-question {
  grid-column: 1;
  grid-row: 2;
}

.scqa-answer {
  grid-column: 2;
  grid-row: 2;
}

/* Highlight the answer panel */
.scqa-answer {
  background-color: var(--secondary);
  border-color: var(--accent);
  border-width: 3px;
}

.scqa-answer .scqa-label {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
</style>
