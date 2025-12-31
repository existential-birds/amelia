<!--
  DATA LAYOUT
  Full-bleed chart slide optimized for data visualization

  Props:
  - title (required): Slide title
  - chartTitle: Optional chart-specific title
  - source: Optional source citation for footer
-->

<script setup lang="ts">
defineProps<{
  title: string
  chartTitle?: string
  source?: string
}>()
</script>

<template>
  <div class="slidev-layout data">
    <!-- Compact Header -->
    <div class="data-header">
      <h1 class="data-title">{{ title }}</h1>
      <h2 v-if="chartTitle" class="data-chart-title">{{ chartTitle }}</h2>
    </div>

    <!-- Chart Zone (90% of body) -->
    <div class="data-chart">
      <slot />
    </div>

    <!-- Compact Footer -->
    <div v-if="source" class="data-footer">
      <span class="data-source">Source: {{ source }}</span>
    </div>
  </div>
</template>

<style scoped>
.data {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 2rem;
  background-color: var(--background);
  color: var(--foreground);
}

.data-header {
  flex-shrink: 0;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid var(--primary);
}

.data-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-heading-bold);
  line-height: var(--line-height-2xl);
  color: var(--primary);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: -0.01em;
}

.data-chart-title {
  font-family: var(--font-body);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-body-semibold);
  line-height: var(--line-height-lg);
  color: var(--foreground);
  margin: 0.5rem 0 0 0;
}

.data-chart {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  overflow: hidden;
  background-color: var(--card);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.5rem;
}

/* Make chart content fill available space */
.data-chart :deep(> *) {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
}

.data-footer {
  flex-shrink: 0;
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.data-source {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  font-style: italic;
}

</style>
