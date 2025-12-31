<!--
  Comparison Layout

  Side-by-side analysis with optional recommendation highlighting.
  The recommended option is highlighted with a primary border.

  Usage:
    ---
    layout: comparison
    title: "Build vs Buy Analysis"
    leftLabel: "Build In-House"
    rightLabel: "Buy SaaS"
    recommendation: "right"
    ---

    ::left::
    ## Pros
    - Full control
    - Custom features

    ## Cons
    - High upfront cost
    - Long timeline

    ::right::
    ## Pros
    - Fast deployment
    - Lower risk

    ## Cons
    - Vendor lock-in
    - Limited customization
-->

<script setup lang="ts">
interface Props {
  title?: string
  leftLabel?: string
  rightLabel?: string
  recommendation?: 'left' | 'right' | null
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  leftLabel: 'Option A',
  rightLabel: 'Option B',
  recommendation: null
})
</script>

<template>
  <div class="comparison-layout">
    <!-- Title -->
    <div v-if="title" class="comparison-title">
      <h1>{{ title }}</h1>
    </div>

    <!-- Comparison grid -->
    <div class="comparison-container">
      <!-- Left option -->
      <div
        class="comparison-option"
        :class="{ recommended: recommendation === 'left' }"
      >
        <div class="option-header">
          <h2>{{ leftLabel }}</h2>
          <span v-if="recommendation === 'left'" class="badge-recommended">
            Recommended
          </span>
        </div>
        <div class="option-content">
          <slot name="left" />
        </div>
      </div>

      <!-- Divider -->
      <div class="comparison-divider" />

      <!-- Right option -->
      <div
        class="comparison-option"
        :class="{ recommended: recommendation === 'right' }"
      >
        <div class="option-header">
          <h2>{{ rightLabel }}</h2>
          <span v-if="recommendation === 'right'" class="badge-recommended">
            Recommended
          </span>
        </div>
        <div class="option-content">
          <slot name="right" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.comparison-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 2rem;
  gap: 1.5rem;
}

.comparison-title {
  text-align: center;
}

.comparison-title h1 {
  margin: 0;
  font-size: var(--font-size-3xl);
  color: var(--foreground);
}

.comparison-container {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 2rem;
  align-items: stretch;
}

.comparison-option {
  background-color: var(--card);
  border: 2px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--foreground) 10%, transparent);
}

.comparison-option.recommended {
  border-color: var(--primary);
  border-width: 3px;
  background: linear-gradient(135deg, var(--card) 0%, var(--muted) 100%);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 20%, transparent);
}

.option-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--border);
}

.comparison-option.recommended .option-header {
  border-bottom-color: var(--primary);
}

.option-header h2 {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
}

.badge-recommended {
  display: inline-block;
  background-color: var(--primary);
  color: var(--primary-foreground);
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-body-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.option-content {
  flex: 1;
  overflow-y: auto;
}

.option-content :deep(h2),
.option-content :deep(h3),
.option-content :deep(h4) {
  margin-top: 1rem;
  margin-bottom: 0.5rem;
  font-size: var(--font-size-lg);
}

.option-content :deep(ul),
.option-content :deep(ol) {
  margin-left: 1.25rem;
  margin-bottom: 1rem;
}

.option-content :deep(li) {
  margin-bottom: 0.5rem;
}

.option-content :deep(p) {
  margin-bottom: 0.75rem;
}

.comparison-divider {
  width: 2px;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    var(--border) 10%,
    var(--border) 90%,
    transparent 100%
  );
}

/* Hover effect for non-recommended options */
.comparison-option:not(.recommended):hover {
  border-color: var(--accent);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--foreground) 15%, transparent);
  transform: translateY(-2px);
}
</style>
