<!--
  QUOTE LAYOUT
  Extends Slidev's statement layout for quotes and key insights.
  Centers a large statement or quote with optional attribution.

  Usage:
  ---
  layout: quote
  class: dark  # or 'light'
  ---

  # Key insight or quote

  Attribution or source
-->

<template>
  <div class="slidev-layout quote">
    <slot />
  </div>
</template>

<style scoped>
.quote {
  /* Center content vertically and horizontally */
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 4rem 6rem;
  background-color: var(--background);
  color: var(--foreground);
}

/* Quote text (h1) - Display font for impact */
.quote :deep(h1) {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
  letter-spacing: 0.01em;
  color: var(--foreground);
  margin: 0;
  padding: 0 2rem;
  position: relative;
}

/* Optional decorative quotation marks */
.quote :deep(h1)::before {
  content: '"';
  font-size: 1.5em;
  color: var(--primary);
  opacity: 0.4;
  position: absolute;
  left: -0.5em;
  top: -0.2em;
}

.quote :deep(h1)::after {
  content: '"';
  font-size: 1.5em;
  color: var(--primary);
  opacity: 0.4;
  position: absolute;
  right: -0.5em;
  bottom: -0.2em;
}

/* Attribution or source (p) */
.quote :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-lg);
  line-height: var(--line-height-lg);
  color: var(--muted-foreground);
  margin-top: 2rem;
  margin-bottom: 0;
  font-style: italic;
}

/* Accent bar above quote */
.quote::before {
  content: '';
  display: block;
  width: 4rem;
  height: 4px;
  background-color: var(--accent);
  margin-bottom: 3rem;
}

/* Blockquote styling (alternative to h1) */
.quote :deep(blockquote) {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
  color: var(--foreground);
  border: none;
  margin: 0;
  padding: 0 2rem;
  position: relative;
}

.quote :deep(blockquote)::before {
  content: '"';
  font-size: 1.5em;
  color: var(--primary);
  opacity: 0.4;
  position: absolute;
  left: -0.5em;
  top: -0.2em;
}

.quote :deep(blockquote)::after {
  content: '"';
  font-size: 1.5em;
  color: var(--primary);
  opacity: 0.4;
  position: absolute;
  right: -0.5em;
  bottom: -0.2em;
}

</style>
