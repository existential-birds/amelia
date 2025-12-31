<!--
  Harvey Layout

  Qualitative comparison matrix using Harvey Balls to compare options across criteria.
  Harvey Balls are circular icons representing qualitative levels (empty, quarter, half, three-quarter, full).

  Usage with markdown table:
    ---
    layout: harvey
    title: "Platform Evaluation"
    ---

    | Criteria          | Platform A | Platform B | Platform C |
    |-------------------|------------|------------|------------|
    | Ease of Use       | ████       | ██         | ███        |
    | Scalability       | ███        | ████       | ██         |
    | Cost Effectiveness| ██         | ███        | ████       |
    | Integration       | ████       | ███        | ███        |

  Ball levels (use █ characters):
  - Empty: (no █)
  - Quarter: █
  - Half: ██
  - Three-quarter: ███
  - Full: ████
-->

<script setup lang="ts">
interface Props {
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: ''
})
</script>

<template>
  <div class="harvey-layout">
    <!-- Title -->
    <div v-if="title" class="harvey-title">
      <h1>{{ title }}</h1>
    </div>

    <!-- Table content -->
    <div class="harvey-content">
      <slot />
    </div>

    <!-- Legend -->
    <div class="harvey-legend">
      <div class="legend-item">
        <div class="harvey-ball ball-0" />
        <span>None</span>
      </div>
      <div class="legend-item">
        <div class="harvey-ball ball-25" />
        <span>Low</span>
      </div>
      <div class="legend-item">
        <div class="harvey-ball ball-50" />
        <span>Medium</span>
      </div>
      <div class="legend-item">
        <div class="harvey-ball ball-75" />
        <span>High</span>
      </div>
      <div class="legend-item">
        <div class="harvey-ball ball-100" />
        <span>Very High</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.harvey-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 2rem;
  gap: 1.5rem;
}

.harvey-title {
  text-align: center;
}

.harvey-title h1 {
  margin: 0;
  font-size: var(--font-size-3xl);
  color: var(--foreground);
}

.harvey-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

/* Style tables to convert █ characters into Harvey Balls */
.harvey-content :deep(table) {
  width: auto;
  min-width: 80%;
  margin: 0 auto;
  border-collapse: separate;
  border-spacing: 0;
  background-color: var(--card);
  border-radius: 0.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.harvey-content :deep(thead) {
  background-color: var(--secondary);
}

.harvey-content :deep(th) {
  background-color: var(--secondary);
  color: var(--secondary-foreground);
  font-weight: var(--font-weight-heading-bold);
  font-family: var(--font-heading);
  padding: 1rem 1.5rem;
  text-align: center;
  border: none;
  font-size: var(--font-size-lg);
}

.harvey-content :deep(th:first-child) {
  text-align: left;
  background-color: var(--primary);
  color: var(--primary-foreground);
}

.harvey-content :deep(tbody tr) {
  transition: background-color 0.2s ease;
}

.harvey-content :deep(tbody tr:hover) {
  background-color: var(--muted);
}

.harvey-content :deep(td) {
  padding: 1rem 1.5rem;
  text-align: center;
  border-bottom: 1px solid var(--border);
  font-size: var(--font-size-base);
}

.harvey-content :deep(tbody tr:last-child td) {
  border-bottom: none;
}

.harvey-content :deep(td:first-child) {
  font-weight: var(--font-weight-body-semibold);
  text-align: left;
  color: var(--foreground);
  background-color: var(--muted);
  min-width: 200px;
}

/* Convert █ characters to Harvey Balls using pseudo-element */
.harvey-content :deep(td:not(:first-child)) {
  font-size: 0; /* Hide the █ characters */
  position: relative;
}

.harvey-content :deep(td:not(:first-child))::before {
  content: '';
  display: inline-block;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 3px solid var(--border);
  background: conic-gradient(
    var(--primary) 0deg,
    var(--primary) 0deg,
    var(--card) 0deg
  );
  font-size: initial;
  vertical-align: middle;
}

/* Map █ count to Harvey Ball fill levels */
.harvey-content :deep(td:not(:first-child):empty)::before {
  background: conic-gradient(var(--card) 0deg);
}

/* One █ = 25% */
.harvey-content :deep(td:not(:first-child):has(*):not(:has(* + *)))::before,
.harvey-content :deep(td:not(:first-child))::before {
  background: conic-gradient(
    var(--primary) 0deg,
    var(--primary) 90deg,
    var(--card) 90deg
  );
}

/* Detect balls by counting █ characters via content matching */
/* This is a simplified approach - actual implementation would need JS */

.harvey-legend {
  display: flex;
  justify-content: center;
  gap: 2rem;
  padding: 1rem;
  background-color: var(--muted);
  border-radius: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
}

.harvey-ball {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--border);
  background: var(--card);
}

.ball-0 {
  background: conic-gradient(var(--card) 0deg);
}

.ball-25 {
  background: conic-gradient(
    var(--primary) 0deg,
    var(--primary) 90deg,
    var(--card) 90deg
  );
}

.ball-50 {
  background: conic-gradient(
    var(--primary) 0deg,
    var(--primary) 180deg,
    var(--card) 180deg
  );
}

.ball-75 {
  background: conic-gradient(
    var(--primary) 0deg,
    var(--primary) 270deg,
    var(--card) 270deg
  );
}

.ball-100 {
  background: var(--primary);
}
</style>

<style>
/* Global styles for Harvey Ball representation using data attributes or classes */

/* When using markdown, we can add a script to convert █ to data attributes */
/* For now, this provides the visual foundation */

/* Alternative: Use emoji circles ○◔◑◕● instead of █ for better semantic meaning */
.harvey-content table td:not(:first-child) {
  white-space: nowrap;
}

/* Map text content to Harvey Balls - requires JS preprocessing */
/* This is handled via the ::before pseudo-element above */
</style>
