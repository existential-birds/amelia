<!--
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<script setup lang="ts">
/**
 * SCQABlock Component
 *
 * Represents a single quadrant of the SCQA (Situation-Complication-Question-Answer)
 * framework used in structured business communication. Each block is color-coded
 * to distinguish between the four stages of the narrative.
 *
 * @example
 * ```vue
 * <SCQABlock type="situation" title="Current State">
 *   <p>We have 5 manual processes consuming 20 hours/week</p>
 * </SCQABlock>
 * ```
 */

type SCQAType = 'situation' | 'complication' | 'question' | 'answer';

interface Props {
  /** Type of SCQA block, determines color and icon */
  type: SCQAType;
  /** Title text for the block */
  title: string;
}

const props = defineProps<Props>();

/**
 * Color mappings for each SCQA type
 */
const typeColors: Record<SCQAType, { bg: string; border: string; icon: string }> = {
  situation: {
    bg: 'var(--secondary)',
    border: 'var(--muted-foreground)',
    icon: '📍',
  },
  complication: {
    bg: 'var(--destructive)',
    border: 'var(--destructive)',
    icon: '⚠️',
  },
  question: {
    bg: 'var(--accent)',
    border: 'var(--accent)',
    icon: '❓',
  },
  answer: {
    bg: 'var(--status-completed)',
    border: 'var(--status-completed)',
    icon: '✓',
  },
};

/**
 * Display labels for each type
 */
const typeLabels: Record<SCQAType, string> = {
  situation: 'Situation',
  complication: 'Complication',
  question: 'Question',
  answer: 'Answer',
};
</script>

<template>
  <div
    class="scqa-block"
    :class="`scqa-block--${type}`"
    :style="{
      backgroundColor: typeColors[type].bg,
      borderColor: typeColors[type].border,
    }"
    role="article"
    :aria-label="`${typeLabels[type]} section`"
  >
    <div class="scqa-block-header">
      <span class="scqa-block-icon" aria-hidden="true">{{ typeColors[type].icon }}</span>
      <h3 class="scqa-block-type">{{ typeLabels[type] }}</h3>
    </div>
    <h4 class="scqa-block-title">{{ title }}</h4>
    <div class="scqa-block-content">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.scqa-block {
  position: relative;
  padding: 1.5rem;
  border-left: 4px solid;
  border-radius: 4px;
  transition: all 0.3s ease;
  background-clip: padding-box;
}

.scqa-block:hover {
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.scqa-block-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.scqa-block-icon {
  font-size: var(--font-size-lg);
  line-height: 1;
}

.scqa-block-type {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-heading-bold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
  opacity: 0.9;
}

.scqa-block-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-heading-semibold);
  line-height: var(--line-height-xl);
  margin: 0 0 1rem 0;
}

.scqa-block-content {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
}

.scqa-block-content :deep(p) {
  margin: 0 0 0.75rem 0;
}

.scqa-block-content :deep(p:last-child) {
  margin-bottom: 0;
}

.scqa-block-content :deep(ul),
.scqa-block-content :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.scqa-block-content :deep(li) {
  margin-bottom: 0.25rem;
}

/* Type-specific styling */
.scqa-block--situation {
  color: var(--secondary-foreground);
}

.scqa-block--complication {
  color: var(--destructive-foreground);
}

.scqa-block--question {
  color: var(--accent-foreground);
}

.scqa-block--answer {
  color: var(--foreground);
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .scqa-block {
    padding: 1rem;
  }

  .scqa-block-title {
    font-size: var(--font-size-lg);
  }

  .scqa-block-content {
    font-size: var(--font-size-sm);
  }
}
</style>
