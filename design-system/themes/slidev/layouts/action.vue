<!--
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<!--
  ACTION LAYOUT
  Standard action-title slide with title, subtitle, and source footer

  Props:
  - title (required): Main slide title
  - subtitle: Optional subtitle text
  - source: Optional source citation for footer
-->

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  source?: string
}>()
</script>

<template>
  <div class="slidev-layout action">
    <!-- Header Zone -->
    <div class="action-header">
      <h1 class="action-title">{{ title }}</h1>
      <p v-if="subtitle" class="action-subtitle">{{ subtitle }}</p>
    </div>

    <!-- Body Zone -->
    <div class="action-body">
      <slot />
    </div>

    <!-- Footer Zone -->
    <div v-if="source" class="action-footer">
      <span class="action-source">{{ source }}</span>
    </div>
  </div>
</template>

<style scoped>
.action {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 3rem;
  background-color: var(--background);
  color: var(--foreground);
}

.action-header {
  margin-bottom: 2rem;
  border-bottom: 3px solid var(--primary);
  padding-bottom: 1rem;
}

.action-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-heading-bold);
  line-height: var(--line-height-4xl);
  color: var(--primary);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: -0.02em;
}

.action-subtitle {
  font-family: var(--font-body);
  font-size: var(--font-size-xl);
  line-height: var(--line-height-xl);
  color: var(--muted-foreground);
  margin: 0.5rem 0 0 0;
  font-weight: var(--font-weight-body-regular);
}

.action-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow-y: auto;
  padding: 1rem 0;
}

.action-footer {
  margin-top: auto;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.action-source {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  font-style: italic;
}
</style>
