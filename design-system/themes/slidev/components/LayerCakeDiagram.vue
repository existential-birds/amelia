<script setup lang="ts">
/**
 * LayerCakeDiagram Component
 *
 * Visualizes system architecture, stack layers, or hierarchical structures
 * using stacked horizontal bands. Commonly used to show technology stacks,
 * architectural layers, or organizational hierarchies.
 *
 * @example
 * ```vue
 * <LayerCakeDiagram :layers="[
 *   { label: 'Presentation', sublabel: 'React, Vue', highlight: true },
 *   { label: 'Business Logic', sublabel: 'Python, FastAPI' },
 *   { label: 'Data Layer', sublabel: 'PostgreSQL, Redis' },
 * ]" />
 * ```
 */

interface Layer {
  /** Primary label for the layer */
  label: string;
  /** Optional secondary label (e.g., technologies, details) */
  sublabel?: string;
  /** Whether this layer should be highlighted */
  highlight?: boolean;
}

interface Props {
  /** Array of layers from top to bottom */
  layers: Layer[];
}

const props = defineProps<Props>();
</script>

<template>
  <div class="layer-cake" role="img" :aria-label="`Architecture diagram with ${layers.length} layers`">
    <div
      v-for="(layer, index) in layers"
      :key="index"
      class="layer-cake-item"
      :class="{ 'layer-cake-item--highlighted': layer.highlight }"
    >
      <div class="layer-cake-content">
        <div class="layer-cake-label">{{ layer.label }}</div>
        <div v-if="layer.sublabel" class="layer-cake-sublabel">{{ layer.sublabel }}</div>
      </div>
      <div v-if="index < layers.length - 1" class="layer-cake-connector" />
    </div>
  </div>
</template>

<style scoped>
.layer-cake {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 600px;
  margin: 0 auto;
  padding: 1rem;
}

.layer-cake-item {
  position: relative;
  background: var(--secondary);
  color: var(--secondary-foreground);
  border: 2px solid var(--border);
  border-radius: 8px;
  transition: all 0.3s ease;
  min-height: 4rem;
}

.layer-cake-item:hover {
  background: var(--muted);
  transform: translateX(8px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.layer-cake-item--highlighted {
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--ring);
}

.layer-cake-item--highlighted:hover {
  background: var(--primary);
  filter: brightness(1.1);
}

.layer-cake-content {
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  min-height: 4rem;
}

.layer-cake-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading-semibold);
  line-height: var(--line-height-lg);
  margin-bottom: 0.25rem;
}

.layer-cake-sublabel {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-body-regular);
  line-height: var(--line-height-sm);
  opacity: 0.85;
}

.layer-cake-connector {
  position: absolute;
  left: 50%;
  bottom: -1.5rem;
  transform: translateX(-50%);
  width: 2px;
  height: 1.5rem;
  background: var(--border);
  z-index: -1;
}

.layer-cake-item:not(:last-child) {
  margin-bottom: 1.5rem;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .layer-cake {
    max-width: 100%;
    padding: 0.5rem;
  }

  .layer-cake-content {
    padding: 0.75rem 1rem;
    min-height: 3rem;
  }

  .layer-cake-label {
    font-size: var(--font-size-base);
  }

  .layer-cake-sublabel {
    font-size: var(--font-size-xs);
  }

  .layer-cake-connector {
    height: 1rem;
    bottom: -1rem;
  }

  .layer-cake-item:not(:last-child) {
    margin-bottom: 1rem;
  }
}

/* Print styles */
@media print {
  .layer-cake-item {
    break-inside: avoid;
  }
}
</style>
