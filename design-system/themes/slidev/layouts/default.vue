<!--
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<!--
  DEFAULT LAYOUT
  Extends Slidev's default content layout with Amelia styling.
  Standard layout for most slides with heading + content.

  Usage:
  ---
  layout: default
  class: dark  # or 'light'
  ---

  # Slide Title
  Content goes here
-->

<template>
  <div class="slidev-layout default">
    <slot />
  </div>
</template>

<style scoped>
.default {
  /* Standard padding and layout */
  padding: 3rem 4rem;
  background-color: var(--background);
  color: var(--foreground);
  display: flex;
  flex-direction: column;
}

/* Slide title (h1) - Heading font */
.default :deep(h1) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
  color: var(--foreground);
  margin-top: 0;
  margin-bottom: 1.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--border);
}

/* Section headings (h2, h3) */
.default :deep(h2) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
  font-size: var(--font-size-2xl);
  line-height: var(--line-height-2xl);
  color: var(--primary);
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
}

.default :deep(h3) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
  font-size: var(--font-size-xl);
  line-height: var(--line-height-xl);
  color: var(--accent);
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
}

/* Body content */
.default :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--foreground);
  margin-bottom: 1rem;
}

/* Lists */
.default :deep(ul),
.default :deep(ol) {
  margin-left: 1.5rem;
  margin-bottom: 1rem;
}

.default :deep(li) {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--foreground);
  margin-bottom: 0.5rem;
}

.default :deep(li)::marker {
  color: var(--primary);
}

/* Light mode overrides */
.light .default {
  background-color: var(--background);
  color: var(--foreground);
}

.light .default :deep(h1) {
  color: var(--foreground);
  border-bottom-color: var(--border);
}

.light .default :deep(h2) {
  color: var(--primary);
}

.light .default :deep(h3) {
  color: var(--accent);
}

.light .default :deep(li)::marker {
  color: var(--primary);
}
</style>
