<!--
  GHOST LAYOUT
  Wireframe/planning mode for early-stage presentations

  Props:
  - title (required): Slide title
  - placeholder: Optional placeholder text for content area
  - notes: Optional notes/comments (displayed as sticky notes)
-->

<script setup lang="ts">
defineProps<{
  title: string
  placeholder?: string
  notes?: string
}>()
</script>

<template>
  <div class="slidev-layout ghost">
    <!-- Draft Watermark -->
    <div class="ghost-watermark">DRAFT</div>

    <!-- Header -->
    <div class="ghost-header">
      <h1 class="ghost-title">{{ title }}</h1>
    </div>

    <!-- Wireframe Content Area -->
    <div class="ghost-content">
      <div v-if="placeholder" class="ghost-placeholder">
        <div class="placeholder-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="3" y1="9" x2="21" y2="9"/>
            <line x1="9" y1="21" x2="9" y2="9"/>
          </svg>
        </div>
        <p class="placeholder-text">{{ placeholder }}</p>
      </div>
      <slot />
    </div>

    <!-- Sticky Note Comments -->
    <div v-if="notes" class="ghost-notes">
      <div class="notes-label">Notes:</div>
      <div class="notes-content">{{ notes }}</div>
    </div>
  </div>
</template>

<style scoped>
.ghost {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 3rem;
  background-color: var(--background);
  color: var(--foreground);
  overflow: hidden;
}

/* Draft watermark */
.ghost-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-45deg);
  font-family: var(--font-display);
  font-size: 8rem;
  font-weight: var(--font-weight-display-regular);
  color: var(--border);
  opacity: 0.15;
  pointer-events: none;
  z-index: 0;
  letter-spacing: 0.2em;
}

.ghost-header {
  position: relative;
  z-index: 1;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 2px dashed var(--border);
}

.ghost-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-heading-bold);
  line-height: var(--line-height-3xl);
  color: var(--muted-foreground);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: -0.01em;
}

.ghost-content {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 3px dashed var(--border);
  border-radius: 0.5rem;
  padding: 2rem;
  background-color: var(--card);
  background-image:
    repeating-linear-gradient(
      0deg,
      transparent,
      transparent 20px,
      var(--border) 20px,
      var(--border) 21px
    ),
    repeating-linear-gradient(
      90deg,
      transparent,
      transparent 20px,
      var(--border) 20px,
      var(--border) 21px
    );
  background-size: 100% 100%;
  opacity: 0.8;
}

.ghost-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.placeholder-icon {
  color: var(--muted-foreground);
  opacity: 0.5;
  margin-bottom: 1rem;
}

.placeholder-text {
  font-family: var(--font-mono);
  font-size: var(--font-size-lg);
  color: var(--muted-foreground);
  margin: 0;
  max-width: 600px;
}

.ghost-notes {
  position: relative;
  z-index: 1;
  margin-top: 2rem;
  padding: 1rem 1.5rem;
  background-color: var(--sticky-bg, oklch(85% 0.1 85));
  color: var(--sticky-color, oklch(20% 0.04 150));
  border-left: 4px solid var(--sticky-border, oklch(75% 0.14 85));
  border-radius: 0.25rem;
  box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.1);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  transform: rotate(-0.5deg);
}

.notes-label {
  font-weight: var(--font-weight-mono-medium);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
  color: var(--sticky-label, oklch(45% 0.18 25));
}

.notes-content {
  line-height: 1.6;
  white-space: pre-wrap;
}

/* Dark mode adjustments */
@media (prefers-color-scheme: dark) {
  .ghost-content {
    background-color: oklch(12% 0.02 150);
  }

  .ghost-watermark {
    opacity: 0.08;
  }
}

/* Light mode adjustments */
@media (prefers-color-scheme: light) {
  .ghost-content {
    background-color: oklch(98% 0.01 85);
  }

  .ghost-watermark {
    opacity: 0.1;
  }

  .ghost-notes {
    --sticky-bg: oklch(90% 0.08 75);
    --sticky-color: oklch(20% 0.04 150);
  }
}

.light .ghost-content {
  background-color: oklch(98% 0.01 85);
}

.light .ghost-watermark {
  opacity: 0.1;
}

.light .ghost-notes {
  --sticky-bg: oklch(90% 0.08 75);
  --sticky-color: oklch(20% 0.04 150);
}
</style>
