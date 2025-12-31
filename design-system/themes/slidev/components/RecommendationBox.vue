<script setup lang="ts">
/**
 * RecommendationBox Component
 *
 * A highlighted callout box with colored left border for drawing attention
 * to key recommendations, warnings, insights, or action items in presentations.
 * Follows professional consulting communication patterns.
 *
 * @example
 * ```vue
 * <RecommendationBox type="recommendation">
 *   <p>Implement automated testing to reduce deployment time by 40%</p>
 * </RecommendationBox>
 * ```
 */

type BoxType = 'recommendation' | 'warning' | 'insight' | 'action';

interface Props {
  /** Type of box, determines styling and icon */
  type: BoxType;
}

const props = defineProps<Props>();

/**
 * Configuration for each box type
 */
const typeConfig: Record<BoxType, { icon: string; label: string; color: string }> = {
  recommendation: {
    icon: '💡',
    label: 'Recommendation',
    color: 'var(--primary)',
  },
  warning: {
    icon: '⚠️',
    label: 'Warning',
    color: 'var(--destructive)',
  },
  insight: {
    icon: '🔍',
    label: 'Key Insight',
    color: 'var(--accent)',
  },
  action: {
    icon: '✓',
    label: 'Action Item',
    color: 'var(--status-completed)',
  },
};

const config = typeConfig[props.type];
</script>

<template>
  <div
    class="recommendation-box"
    :class="`recommendation-box--${props.type}`"
    :style="{
      borderLeftColor: config.color,
    }"
    role="note"
    :aria-label="`${config.label} callout`"
  >
    <div class="recommendation-header">
      <span class="recommendation-icon" aria-hidden="true">{{ config.icon }}</span>
      <h4 class="recommendation-label">{{ config.label }}</h4>
    </div>
    <div class="recommendation-content">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.recommendation-box {
  position: relative;
  background: var(--card);
  color: var(--card-foreground);
  border-left: 6px solid;
  border-radius: 0 4px 4px 0;
  padding: 1.5rem;
  margin: 1rem 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.recommendation-box:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateX(4px);
}

.recommendation-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.recommendation-icon {
  font-size: var(--font-size-xl);
  line-height: 1;
}

.recommendation-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading-bold);
  line-height: var(--line-height-lg);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.recommendation-content {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-body-regular);
  line-height: var(--line-height-base);
}

.recommendation-content :deep(p) {
  margin: 0 0 0.75rem 0;
}

.recommendation-content :deep(p:last-child) {
  margin-bottom: 0;
}

.recommendation-content :deep(ul),
.recommendation-content :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.recommendation-content :deep(li) {
  margin-bottom: 0.5rem;
}

.recommendation-content :deep(strong) {
  font-weight: var(--font-weight-body-semibold);
  color: var(--foreground);
}

.recommendation-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: var(--muted);
  padding: 0.125rem 0.25rem;
  border-radius: 2px;
}

/* Type-specific accent colors */
.recommendation-box--recommendation .recommendation-label {
  color: var(--primary);
}

.recommendation-box--warning .recommendation-label {
  color: var(--destructive);
}

.recommendation-box--insight .recommendation-label {
  color: var(--accent);
}

.recommendation-box--action .recommendation-label {
  color: var(--status-completed);
}

/* Light mode adjustments - system preference */
@media (prefers-color-scheme: light) {
  .recommendation-box {
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  }

  .recommendation-box:hover {
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  }
}

/* Light mode adjustments - explicit .light class */
.light .recommendation-box {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.light .recommendation-box:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .recommendation-box {
    padding: 1rem;
    border-left-width: 4px;
  }

  .recommendation-header {
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
  }

  .recommendation-icon {
    font-size: var(--font-size-lg);
  }

  .recommendation-label {
    font-size: var(--font-size-base);
  }

  .recommendation-content {
    font-size: var(--font-size-sm);
  }
}

/* Print styles */
@media print {
  .recommendation-box {
    break-inside: avoid;
    page-break-inside: avoid;
    box-shadow: none;
    border: 1px solid var(--border);
  }

  .recommendation-box:hover {
    transform: none;
  }
}
</style>
