<script setup lang="ts">
/**
 * HarveyBall Component
 *
 * A qualitative indicator using circular SVG graphics to show completion,
 * progress, or level of achievement. Named after Harvey Poppel, who created
 * these symbols for quick visual assessment in consulting reports.
 *
 * @example
 * ```vue
 * <HarveyBall fill="three-quarter" size="lg" />
 * ```
 */

type FillLevel = 'empty' | 'quarter' | 'half' | 'three-quarter' | 'full';
type Size = 'sm' | 'md' | 'lg';

interface Props {
  /** Fill level of the Harvey Ball */
  fill: FillLevel;
  /** Size variant */
  size?: Size;
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
});

/**
 * Size mappings in pixels
 */
const sizeMap: Record<Size, number> = {
  sm: 32,
  md: 48,
  lg: 64,
};

/**
 * Calculate the fill percentage based on fill level
 */
const fillPercentage: Record<FillLevel, number> = {
  empty: 0,
  quarter: 25,
  half: 50,
  'three-quarter': 75,
  full: 100,
};

/**
 * Calculate the arc path for the filled portion
 */
const getArcPath = (percentage: number, radius: number): string => {
  if (percentage === 0) return '';
  if (percentage === 100) {
    // Full circle
    return `M ${radius},0 A ${radius},${radius} 0 1,1 ${radius},${2 * radius} A ${radius},${radius} 0 1,1 ${radius},0`;
  }

  const angle = (percentage / 100) * 2 * Math.PI;
  const x = radius + radius * Math.sin(angle);
  const y = radius - radius * Math.cos(angle);
  const largeArcFlag = percentage > 50 ? 1 : 0;

  return `M ${radius},${radius} L ${radius},0 A ${radius},${radius} 0 ${largeArcFlag},1 ${x},${y} Z`;
};

const diameter = sizeMap[props.size];
const radius = diameter / 2;
const strokeWidth = 2;
const fillPath = getArcPath(fillPercentage[props.fill], radius - strokeWidth);
</script>

<template>
  <svg
    class="harvey-ball"
    :class="`harvey-ball--${size}`"
    :width="diameter"
    :height="diameter"
    :viewBox="`0 0 ${diameter} ${diameter}`"
    role="img"
    :aria-label="`${fill} filled indicator`"
  >
    <!-- Background circle (outline) -->
    <circle
      :cx="radius"
      :cy="radius"
      :r="radius - strokeWidth"
      fill="none"
      :stroke="'var(--border)'"
      :stroke-width="strokeWidth"
    />

    <!-- Filled portion (partial fills only; full handled by circle below) -->
    <path
      v-if="fillPath && fill !== 'full'"
      :d="fillPath"
      :fill="'var(--primary)'"
      class="harvey-ball-fill"
    />

    <!-- Full circle fill for 100% -->
    <circle
      v-if="fill === 'full'"
      :cx="radius"
      :cy="radius"
      :r="radius - strokeWidth"
      :fill="'var(--primary)'"
      class="harvey-ball-fill"
    />
  </svg>
</template>

<style scoped>
.harvey-ball {
  display: inline-block;
  vertical-align: middle;
  transition: transform 0.2s ease;
}

.harvey-ball:hover {
  transform: scale(1.1);
}

.harvey-ball-fill {
  transition: fill 0.3s ease;
}

/* Size variants */
.harvey-ball--sm {
  width: 32px;
  height: 32px;
}

.harvey-ball--md {
  width: 48px;
  height: 48px;
}

.harvey-ball--lg {
  width: 64px;
  height: 64px;
}

/* Accessible focus styles */
.harvey-ball:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
  border-radius: 50%;
}
</style>
