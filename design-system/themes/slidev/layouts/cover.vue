<!--
  COVER LAYOUT
  Extends Slidev's default cover layout with Amelia styling.

  Usage:
  ---
  layout: cover
  class: dark  # or 'light'
  ---

  # Presentation Title
  Subtitle or tagline
-->

<template>
  <div class="slidev-layout cover">
    <slot />
  </div>
</template>

<style scoped>
.cover {
  /* Full viewport centering */
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  padding: 4rem;
  background-color: var(--background);
  color: var(--foreground);
}

/* Title (h1) - Display font */
.cover :deep(h1) {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
  font-size: var(--font-size-5xl);
  line-height: var(--line-height-5xl);
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--foreground);
  margin-bottom: 1rem;
}

/* Subtitle (p) - Body font */
.cover :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-xl);
  line-height: var(--line-height-xl);
  color: var(--muted-foreground);
  margin-top: 0;
}

</style>
