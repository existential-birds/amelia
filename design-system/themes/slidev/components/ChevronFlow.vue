<script setup lang="ts">
/**
 * ChevronFlow Component
 *
 * Visualizes sequential process steps using arrow-shaped chevrons.
 * Each step shows its status (completed, active, or pending) through
 * color coding. Commonly used for workflows, pipelines, and processes.
 *
 * @example
 * ```vue
 * <ChevronFlow :steps="[
 *   { label: 'Plan', status: 'completed' },
 *   { label: 'Build', status: 'active' },
 *   { label: 'Deploy', status: 'pending' },
 * ]" />
 * ```
 */

type StepStatus = 'completed' | 'active' | 'pending';

interface Step {
  /** Label for the step */
  label: string;
  /** Current status of the step */
  status: StepStatus;
}

interface Props {
  /** Array of process steps in order */
  steps: Step[];
}

defineProps<Props>();

/**
 * Get the background color based on step status
 */
const getStatusColor = (status: StepStatus): string => {
  switch (status) {
    case 'completed':
      return 'var(--status-completed)';
    case 'active':
      return 'var(--status-running)';
    case 'pending':
      return 'var(--status-pending)';
  }
};

/**
 * Get the text color based on step status
 */
const getStatusTextColor = (status: StepStatus): string => {
  switch (status) {
    case 'completed':
    case 'pending':
      return 'var(--foreground)';
    case 'active':
      return 'var(--primary-foreground)';
  }
};

/**
 * Get the status icon
 */
const getStatusIcon = (status: StepStatus): string => {
  switch (status) {
    case 'completed':
      return '✓';
    case 'active':
      return '▶';
    case 'pending':
      return '○';
  }
};
</script>

<template>
  <div class="chevron-flow" role="list" aria-label="Process flow">
    <div
      v-for="(step, index) in steps"
      :key="index"
      role="listitem"
      class="chevron-step"
      :class="`chevron-step--${step.status}`"
      :style="{
        backgroundColor: getStatusColor(step.status),
        color: getStatusTextColor(step.status),
      }"
      :aria-current="step.status === 'active' ? 'step' : undefined"
    >
      <div class="chevron-content">
        <span class="chevron-icon" aria-hidden="true">{{ getStatusIcon(step.status) }}</span>
        <span class="chevron-label">{{ step.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chevron-flow {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  padding: 1rem 0;
}

.chevron-step {
  position: relative;
  flex: 1;
  min-width: 120px;
  padding: 1rem 2rem 1rem 2.5rem;
  clip-path: polygon(0% 0%, calc(100% - 1.5rem) 0%, 100% 50%, calc(100% - 1.5rem) 100%, 0% 100%, 1.5rem 50%);
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chevron-step:first-child {
  clip-path: polygon(0% 0%, calc(100% - 1.5rem) 0%, 100% 50%, calc(100% - 1.5rem) 100%, 0% 100%);
  padding-left: 1.5rem;
}

.chevron-step:last-child {
  clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%, 1.5rem 50%);
  padding-right: 1.5rem;
}

.chevron-step:first-child:last-child {
  clip-path: none;
  padding-left: 1.5rem;
  padding-right: 1.5rem;
  border-radius: 4px;
}

.chevron-step:hover {
  filter: brightness(1.1);
  transform: scale(1.02);
  z-index: 1;
}

.chevron-step--active {
  box-shadow: 0 0 0 3px var(--ring);
  z-index: 2;
}

.chevron-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  white-space: nowrap;
}

.chevron-icon {
  font-size: var(--font-size-base);
  line-height: 1;
}

.chevron-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-heading-semibold);
  line-height: var(--line-height-base);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Status-specific styling */
.chevron-step--pending {
  opacity: 0.6;
}

.chevron-step--active {
  font-weight: var(--font-weight-heading-bold);
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .chevron-flow {
    flex-direction: column;
    gap: 0.5rem;
  }

  .chevron-step {
    clip-path: none;
    width: 100%;
    padding: 1rem 1.5rem;
    border-radius: 4px;
    border-left: 4px solid currentColor;
  }

  .chevron-step:first-child,
  .chevron-step:last-child {
    clip-path: none;
    padding: 1rem 1.5rem;
  }

  .chevron-label {
    font-size: var(--font-size-sm);
  }
}

/* Print styles */
@media print {
  .chevron-step {
    break-inside: avoid;
  }
}
</style>
