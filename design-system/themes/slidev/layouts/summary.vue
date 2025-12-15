<!--
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<!--
  SUMMARY LAYOUT
  Executive summary with recommendation callout box

  Props:
  - title (required): Slide title
  - recommendation: Text for highlighted recommendation box
-->

<script setup lang="ts">
defineProps<{
  title: string
  recommendation?: string
}>()
</script>

<template>
  <div class="slidev-layout summary">
    <!-- Header -->
    <div class="summary-header">
      <h1 class="summary-title">{{ title }}</h1>
    </div>

    <!-- Main Content -->
    <div class="summary-body">
      <slot />
    </div>

    <!-- Recommendation Callout -->
    <div v-if="recommendation" class="summary-recommendation">
      <div class="recommendation-label">Recommendation</div>
      <div class="recommendation-content">{{ recommendation }}</div>
    </div>
  </div>
</template>

<style scoped>
.summary {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 3rem;
  background-color: var(--background);
  color: var(--foreground);
}

.summary-header {
  margin-bottom: 2rem;
}

.summary-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-heading-bold);
  line-height: var(--line-height-4xl);
  color: var(--foreground);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: -0.02em;
}

.summary-body {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 2rem;
  font-family: var(--font-body);
  font-size: var(--font-size-lg);
  line-height: var(--line-height-lg);
}

.summary-recommendation {
  background-color: var(--card);
  border-left: 6px solid var(--primary);
  border-radius: 0.5rem;
  padding: 1.5rem 2rem;
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  margin-top: auto;
}

.recommendation-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-heading-semibold);
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.75rem;
}

.recommendation-content {
  font-family: var(--font-body);
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-body-semibold);
  line-height: var(--line-height-xl);
  color: var(--foreground);
}

/* Dark mode enhancements */
@media (prefers-color-scheme: dark) {
  .summary-recommendation {
    background-color: var(--card);
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.2);
  }
}

/* Light mode enhancements */
@media (prefers-color-scheme: light) {
  .summary-recommendation {
    background-color: var(--secondary);
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.03);
  }
}

.light .summary-recommendation {
  background-color: var(--secondary);
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.03);
}
</style>
