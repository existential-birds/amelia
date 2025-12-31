<!--
  Pyramid Layout

  Visualizes the pyramid principle - hierarchical structure with key message at top,
  supporting arguments in middle, and evidence at bottom.

  Usage:
    ---
    layout: pyramid
    ---

    ::top::
    # Key Message
    Main conclusion or recommendation

    ::supporting::
    ## Supporting Arguments
    - Argument 1
    - Argument 2
    - Argument 3

    ::evidence::
    ### Evidence
    - Data point 1
    - Data point 2
    - Data point 3
-->

<template>
  <div class="pyramid-layout">
    <div class="pyramid-container">
      <!-- Top tier: Key message -->
      <div class="pyramid-tier tier-top">
        <div class="tier-content">
          <slot name="top" />
        </div>
      </div>

      <!-- Middle tier: Supporting arguments -->
      <div class="pyramid-tier tier-middle">
        <div class="tier-content">
          <slot name="supporting" />
        </div>
      </div>

      <!-- Bottom tier: Evidence -->
      <div class="pyramid-tier tier-bottom">
        <div class="tier-content">
          <slot name="evidence" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pyramid-layout {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.pyramid-container {
  width: 100%;
  max-width: 1000px;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.pyramid-tier {
  display: flex;
  justify-content: center;
  transform-origin: center;
  will-change: transform;
  transition: transform 0.3s ease;
}

.tier-content {
  background-color: var(--card);
  border: 2px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Top tier: Key message - narrowest */
.tier-top .tier-content {
  width: 50%;
  border-color: var(--primary);
  border-width: 3px;
  background: linear-gradient(135deg, var(--card) 0%, var(--muted) 100%);
}

/* Middle tier: Supporting - medium width */
.tier-middle .tier-content {
  width: 70%;
  border-color: var(--accent);
}

/* Bottom tier: Evidence - widest */
.tier-bottom .tier-content {
  width: 90%;
  border-color: var(--secondary);
}

/* Typography adjustments */
.tier-content :deep(h1),
.tier-content :deep(h2),
.tier-content :deep(h3) {
  margin-top: 0;
  margin-bottom: 0.75rem;
}

.tier-content :deep(ul),
.tier-content :deep(ol) {
  margin-bottom: 0;
}

.tier-content :deep(li) {
  margin-bottom: 0.5rem;
}

.tier-content :deep(li:last-child) {
  margin-bottom: 0;
}

/* Hover effect */
.pyramid-tier:hover {
  transform: scale(1.02);
}

.pyramid-tier:hover .tier-content {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
