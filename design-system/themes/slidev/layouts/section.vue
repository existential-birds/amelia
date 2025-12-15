<!--
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<!--
  SECTION LAYOUT
  Extends Slidev's section/divider layout with Amelia styling.
  Used for section breaks and agenda dividers.

  Usage:
  ---
  layout: section
  class: dark  # or 'light'
  ---

  # Section Title
-->

<template>
  <div class="slidev-layout section">
    <slot />
  </div>
</template>

<style scoped>
.section {
  /* Center content both vertically and horizontally */
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 4rem;
  background-color: var(--background);
  color: var(--foreground);
}

/* Section title (h1) - Display font */
.section :deep(h1) {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
  font-size: var(--font-size-5xl);
  line-height: var(--line-height-5xl);
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--primary);
  margin: 0;
  position: relative;
}

/* Decorative underline */
.section :deep(h1)::after {
  content: '';
  display: block;
  width: 6rem;
  height: 4px;
  background-color: var(--accent);
  margin: 1.5rem auto 0;
}

/* Optional subtitle */
.section :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-lg);
  line-height: var(--line-height-lg);
  color: var(--muted-foreground);
  margin-top: 2rem;
}

/* Light mode overrides */
.light .section {
  background-color: var(--background);
  color: var(--foreground);
}

.light .section :deep(h1) {
  color: var(--primary);
}

.light .section :deep(h1)::after {
  background-color: var(--accent);
}

.light .section :deep(p) {
  color: var(--muted-foreground);
}
</style>
