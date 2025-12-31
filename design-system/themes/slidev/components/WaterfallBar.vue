<script setup lang="ts">
/**
 * WaterfallBar Component
 *
 * A single segment of a waterfall (bridge) chart showing value changes.
 * Used to visualize sequential positive and negative contributions to a total.
 * Commonly used in financial analysis, budget variance, and change attribution.
 *
 * @example
 * ```vue
 * <WaterfallBar value="50" label="Q1 Revenue" type="start" />
 * <WaterfallBar value="15" label="Growth" type="increase" showConnector />
 * <WaterfallBar value="-10" label="Costs" type="decrease" showConnector />
 * <WaterfallBar value="55" label="Q2 Revenue" type="end" showConnector />
 * ```
 */

type BarType = 'start' | 'increase' | 'decrease' | 'end';

interface Props {
  /** Numeric value to display */
  value: number | string;
  /** Label for the bar */
  label: string;
  /** Type of bar segment */
  type: BarType;
  /** Whether to show connector line to previous bar */
  showConnector?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showConnector: false,
});

/**
 * Parse value as number
 */
const numericValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value;
  }
  const parsed = parseFloat(props.value);
  return isNaN(parsed) ? 0 : parsed;
});

/**
 * Get the bar color based on type
 */
const getBarColor = (type: BarType): string => {
  switch (type) {
    case 'start':
    case 'end':
      return 'var(--primary)';
    case 'increase':
      return 'var(--status-completed)';
    case 'decrease':
      return 'var(--destructive)';
  }
};

/**
 * Get the text color based on type
 */
const getTextColor = (type: BarType): string => {
  switch (type) {
    case 'start':
    case 'end':
      return 'var(--primary-foreground)';
    case 'increase':
      return 'var(--foreground)';
    case 'decrease':
      return 'var(--destructive-foreground)';
  }
};

/**
 * Format the display value
 */
const displayValue = computed(() => {
  const val = numericValue.value;
  if (props.type === 'increase' && val > 0) {
    return `+${val}`;
  }
  return val.toString();
});
</script>

<template>
  <div class="waterfall-bar-container">
    <div
      v-if="showConnector"
      class="waterfall-connector"
      aria-hidden="true"
    />
    <div
      class="waterfall-bar"
      :class="`waterfall-bar--${type}`"
      :style="{
        backgroundColor: getBarColor(type),
        color: getTextColor(type),
      }"
      role="img"
      :aria-label="`${label}: ${displayValue}`"
    >
      <div class="waterfall-bar-content">
        <div class="waterfall-bar-value">{{ displayValue }}</div>
        <div class="waterfall-bar-label">{{ label }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.waterfall-bar-container {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
}

.waterfall-connector {
  width: 2px;
  height: 1.5rem;
  background: var(--border);
  margin-bottom: 0.5rem;
  position: relative;
}

.waterfall-connector::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
}

.waterfall-bar {
  position: relative;
  min-width: 100px;
  min-height: 80px;
  padding: 1rem;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.waterfall-bar:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.waterfall-bar--start,
.waterfall-bar--end {
  border: 3px solid currentColor;
  font-weight: var(--font-weight-heading-bold);
}

.waterfall-bar-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  text-align: center;
}

.waterfall-bar-value {
  font-family: var(--font-display);
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-display-regular);
  line-height: 1;
  letter-spacing: 0.02em;
}

.waterfall-bar-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-heading-medium);
  line-height: var(--line-height-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  max-width: 100%;
  word-wrap: break-word;
}

/* Type-specific animations */
.waterfall-bar--increase {
  animation: slideUp 0.5s ease-out;
}

.waterfall-bar--decrease {
  animation: slideDown 0.5s ease-out;
}

@keyframes slideUp {
  from {
    transform: translateY(10px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes slideDown {
  from {
    transform: translateY(-10px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .waterfall-bar {
    min-width: 80px;
    min-height: 60px;
    padding: 0.75rem;
  }

  .waterfall-bar-value {
    font-size: var(--font-size-xl);
  }

  .waterfall-bar-label {
    font-size: var(--font-size-xs);
  }
}

/* Print styles */
@media print {
  .waterfall-bar {
    break-inside: avoid;
  }

  .waterfall-connector {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
</style>
