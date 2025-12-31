<script setup lang="ts">
/**
 * PyramidDiagram Component
 *
 * Visualizes the Pyramid Principle hierarchy with layered trapezoids.
 * Each layer represents a level in the information hierarchy, with the
 * top layer being the main message and lower layers providing supporting details.
 *
 * @example
 * ```vue
 * <PyramidDiagram :layers="[
 *   { label: 'Main Message', detail: 'Key recommendation' },
 *   { label: 'Supporting Point 1', detail: 'Evidence' },
 *   { label: 'Supporting Point 2', detail: 'Analysis' },
 * ]" />
 * ```
 */

interface Layer {
  /** Primary text for the layer */
  label: string;
  /** Optional secondary detail text */
  detail?: string;
}

interface Props {
  /** Array of pyramid layers, from top (most important) to bottom */
  layers: Layer[];
}

const props = defineProps<Props>();

/**
 * Calculate the width percentage for each layer based on its position
 * Top layer is narrowest, bottom layer is widest
 */
const getLayerWidth = (index: number): number => {
  const maxLayers = props.layers.length;
  // Single layer: use default width
  if (maxLayers === 1) {
    return 70;
  }
  // Top layer at 40%, bottom at 100%, linear interpolation
  return 40 + ((100 - 40) * index) / (maxLayers - 1);
};

/**
 * Calculate opacity for each layer to create depth effect.
 * Clamped to minimum 0.1 to ensure visibility for pyramids with many layers.
 */
const getLayerOpacity = (index: number): number => {
  return Math.max(0.1, 1 - index * 0.1);
};
</script>

<template>
  <div class="pyramid-diagram" role="img" :aria-label="`Pyramid diagram with ${layers.length} layers`">
    <div
      v-for="(layer, index) in layers"
      :key="index"
      class="pyramid-layer"
      :style="{
        width: `${getLayerWidth(index)}%`,
        opacity: getLayerOpacity(index),
      }"
    >
      <div class="pyramid-layer-content">
        <div class="pyramid-layer-label">{{ layer.label }}</div>
        <div v-if="layer.detail" class="pyramid-layer-detail">{{ layer.detail }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pyramid-diagram {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
}

.pyramid-layer {
  position: relative;
  background: var(--primary);
  color: var(--primary-foreground);
  padding: 1rem 1.5rem;
  text-align: center;
  clip-path: polygon(10% 0%, 90% 0%, 100% 100%, 0% 100%);
  transition: all 0.3s ease;
  min-height: 4rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pyramid-layer:hover {
  transform: translateY(-2px);
  filter: brightness(1.1);
}

.pyramid-layer:first-child {
  background: var(--accent);
  color: var(--accent-foreground);
}

.pyramid-layer:nth-child(even) {
  background: var(--secondary);
  color: var(--secondary-foreground);
}

.pyramid-layer-content {
  width: 100%;
}

.pyramid-layer-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading-semibold);
  line-height: var(--line-height-lg);
  margin-bottom: 0.25rem;
}

.pyramid-layer-detail {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-body-regular);
  line-height: var(--line-height-sm);
  opacity: 0.9;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .pyramid-layer {
    min-height: 3rem;
    padding: 0.75rem 1rem;
  }

  .pyramid-layer-label {
    font-size: var(--font-size-base);
  }

  .pyramid-layer-detail {
    font-size: var(--font-size-xs);
  }
}
</style>
