<!--
  Takeaway Layout

  Large, centered text for key insights and takeaways.
  Features a horizontal emphasis line in primary color.

  Usage:
    ---
    layout: takeaway
    ---

    # Data-driven insights reduce decision time by 60%

  Or with default slot:
    ---
    layout: takeaway
    ---

    The most successful teams ship small, iterate fast
-->

<template>
  <div class="takeaway-layout">
    <div class="takeaway-container">
      <!-- Decorative top line -->
      <div class="emphasis-line emphasis-top" />

      <!-- Main content -->
      <div class="takeaway-content">
        <slot>
          <h1>Key Takeaway</h1>
        </slot>
      </div>

      <!-- Decorative bottom line -->
      <div class="emphasis-line emphasis-bottom" />
    </div>
  </div>
</template>

<style scoped>
.takeaway-layout {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4rem;
}

.takeaway-container {
  max-width: 900px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rem;
}

.emphasis-line {
  width: 120px;
  height: 4px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--primary) 50%,
    transparent 100%
  );
  border-radius: 2px;
}

.emphasis-top {
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--primary) 100%
  );
}

.emphasis-bottom {
  background: linear-gradient(
    90deg,
    var(--primary) 0%,
    transparent 100%
  );
}

.takeaway-content {
  text-align: center;
  padding: 2rem 0;
}

/* Typography - make text large and impactful */
.takeaway-content :deep(h1) {
  font-size: var(--font-size-5xl);
  line-height: var(--line-height-5xl);
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
  color: var(--foreground);
  margin: 0;
  letter-spacing: -0.02em;
}

.takeaway-content :deep(h2) {
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
  color: var(--foreground);
  margin: 0;
}

.takeaway-content :deep(h3) {
  font-size: var(--font-size-3xl);
  line-height: var(--line-height-3xl);
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
  color: var(--foreground);
  margin: 0;
}

.takeaway-content :deep(p) {
  font-size: var(--font-size-2xl);
  line-height: var(--line-height-2xl);
  font-family: var(--font-body);
  font-weight: var(--font-weight-body-semibold);
  color: var(--foreground);
  margin: 0;
  max-width: 800px;
}

/* Highlight key words with primary color */
.takeaway-content :deep(strong),
.takeaway-content :deep(b) {
  color: var(--primary);
  font-weight: var(--font-weight-heading-bold);
}

.takeaway-content :deep(em),
.takeaway-content :deep(i) {
  color: var(--accent);
  font-style: italic;
}

/* Code in takeaway */
.takeaway-content :deep(code) {
  font-size: 0.9em;
  background-color: var(--muted);
  color: var(--primary);
  padding: 0.2em 0.5em;
  border-radius: 0.25rem;
}

/* Subtle animation on enter */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.takeaway-content {
  animation: fadeInUp 0.6s ease-out;
}

.emphasis-line {
  animation: fadeInUp 0.8s ease-out;
}
</style>
