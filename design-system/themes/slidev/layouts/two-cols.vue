<!--
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at https://mozilla.org/MPL/2.0/.
-->

<!--
  TWO-COLS LAYOUT
  Extends Slidev's two-column layout with Amelia styling.

  Usage:
  ---
  layout: two-cols
  class: dark  # or 'light'
  ---

  # Slide Title

  ::left::
  Left column content

  ::right::
  Right column content
-->

<template>
  <div class="slidev-layout two-cols">
    <slot />
  </div>
</template>

<style scoped>
.two-cols {
  /* Standard padding */
  padding: 3rem 4rem;
  background-color: var(--background);
  color: var(--foreground);
  display: flex;
  flex-direction: column;
}

/* Title styling */
.two-cols :deep(h1) {
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

/* Column container */
.two-cols :deep(.grid-cols-2) {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  flex: 1;
}

/* Individual columns */
.two-cols :deep(.col-left),
.two-cols :deep(.col-right) {
  display: flex;
  flex-direction: column;
}

/* Column headings */
.two-cols :deep(h2) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
  font-size: var(--font-size-2xl);
  line-height: var(--line-height-2xl);
  color: var(--primary);
  margin-top: 0;
  margin-bottom: 1rem;
}

.two-cols :deep(h3) {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
  font-size: var(--font-size-xl);
  line-height: var(--line-height-xl);
  color: var(--accent);
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

/* Body text in columns */
.two-cols :deep(p) {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--foreground);
  margin-bottom: 1rem;
}

/* Lists in columns */
.two-cols :deep(ul),
.two-cols :deep(ol) {
  margin-left: 1.5rem;
  margin-bottom: 1rem;
}

.two-cols :deep(li) {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--foreground);
  margin-bottom: 0.5rem;
}

.two-cols :deep(li)::marker {
  color: var(--primary);
}

/* Visual divider between columns */
.two-cols :deep(.col-left) {
  padding-right: 1rem;
  border-right: 1px solid var(--border);
}

.two-cols :deep(.col-right) {
  padding-left: 1rem;
}

/* Light mode overrides */
.light .two-cols {
  background-color: var(--background);
  color: var(--foreground);
}

.light .two-cols :deep(h1) {
  color: var(--foreground);
  border-bottom-color: var(--border);
}

.light .two-cols :deep(h2) {
  color: var(--primary);
}

.light .two-cols :deep(h3) {
  color: var(--accent);
}

.light .two-cols :deep(.col-left) {
  border-right-color: var(--border);
}

.light .two-cols :deep(li)::marker {
  color: var(--primary);
}
</style>
