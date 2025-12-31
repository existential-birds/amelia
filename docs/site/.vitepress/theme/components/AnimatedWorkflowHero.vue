<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

// Agent workflow states: architect -> developer -> reviewer -> (loop back to developer or done)
type AgentState = 'architect' | 'developer' | 'reviewer' | 'approved'

const currentAgent = ref<AgentState>('architect')
const cycleCount = ref(0)
let animationInterval: ReturnType<typeof setInterval> | null = null
let animationTimeout: ReturnType<typeof setTimeout> | null = null

const agents = [
  { id: 'architect', label: 'Architect', sublabel: 'plans' },
  { id: 'developer', label: 'Developer', sublabel: 'calls tools' },
  { id: 'reviewer', label: 'Reviewer', sublabel: 'validates' }
] as const

const startInterval = () => {
  animationInterval = setInterval(() => {
    switch (currentAgent.value) {
      case 'architect':
        currentAgent.value = 'developer'
        break
      case 'developer':
        currentAgent.value = 'reviewer'
        break
      case 'reviewer':
        // After 2 review cycles, show "approved" briefly then restart
        if (cycleCount.value >= 1) {
          currentAgent.value = 'approved'
          cycleCount.value = 0
          // Stop interval during approved state to avoid race condition
          if (animationInterval) {
            clearInterval(animationInterval)
            animationInterval = null
          }
          // Single timeout to transition back to architect
          animationTimeout = setTimeout(() => {
            currentAgent.value = 'architect'
            animationTimeout = null
            // Restart the interval for the next cycle
            startInterval()
          }, 1500)
        } else {
          // Loop back to developer (simulating revision)
          currentAgent.value = 'developer'
          cycleCount.value++
        }
        break
    }
  }, 2000)
}

onMounted(() => {
  startInterval()
})

onUnmounted(() => {
  if (animationInterval) {
    clearInterval(animationInterval)
  }
  if (animationTimeout) {
    clearTimeout(animationTimeout)
  }
})

const isActive = (agentId: string) => currentAgent.value === agentId
const isApproved = () => currentAgent.value === 'approved'
</script>

<template>
  <div class="workflow-hero">
    <svg
      viewBox="0 0 400 320"
      class="workflow-diagram"
      aria-label="Amelia agent workflow: Architect plans, Developer executes, Reviewer validates"
    >
      <defs>
        <!-- Gradient for active state glow -->
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>

        <!-- Arrow marker -->
        <marker
          id="arrowhead"
          markerWidth="10"
          markerHeight="7"
          refX="9"
          refY="3.5"
          orient="auto"
        >
          <polygon
            points="0 0, 10 3.5, 0 7"
            fill="var(--vp-c-text-3)"
          />
        </marker>

        <marker
          id="arrowhead-active"
          markerWidth="10"
          markerHeight="7"
          refX="9"
          refY="3.5"
          orient="auto"
        >
          <polygon
            points="0 0, 10 3.5, 0 7"
            fill="var(--vp-c-brand-1)"
          />
        </marker>
      </defs>

      <!-- Architect Node -->
      <g class="agent-node" :class="{ active: isActive('architect') }">
        <rect
          x="140"
          y="20"
          width="120"
          height="70"
          rx="8"
          class="node-bg"
          :filter="isActive('architect') ? 'url(#glow)' : ''"
        />
        <text x="200" y="50" class="node-label">Architect</text>
        <text x="200" y="70" class="node-sublabel">plans</text>
      </g>

      <!-- Arrow: Architect -> Developer -->
      <path
        d="M 200 90 L 200 125"
        class="connector"
        :class="{ active: isActive('developer') }"
        marker-end="url(#arrowhead)"
      />

      <!-- Developer Node -->
      <g class="agent-node" :class="{ active: isActive('developer') }">
        <rect
          x="140"
          y="130"
          width="120"
          height="70"
          rx="8"
          class="node-bg"
          :filter="isActive('developer') ? 'url(#glow)' : ''"
        />
        <text x="200" y="160" class="node-label">Developer</text>
        <text x="200" y="180" class="node-sublabel">calls tools</text>
      </g>

      <!-- Arrow: Developer -> Reviewer -->
      <path
        d="M 200 200 L 200 235"
        class="connector"
        :class="{ active: isActive('reviewer') }"
        marker-end="url(#arrowhead)"
      />

      <!-- Reviewer Node -->
      <g class="agent-node" :class="{ active: isActive('reviewer') || isApproved() }">
        <rect
          x="140"
          y="240"
          width="120"
          height="70"
          rx="8"
          class="node-bg"
          :class="{ approved: isApproved() }"
          :filter="isActive('reviewer') || isApproved() ? 'url(#glow)' : ''"
        />
        <text x="200" y="270" class="node-label">Reviewer</text>
        <text x="200" y="290" class="node-sublabel">
          {{ isApproved() ? '✓ approved' : 'validates' }}
        </text>
      </g>

      <!-- Loop arrow: Reviewer -> Developer (revision loop) -->
      <path
        d="M 260 275 Q 320 275 320 165 Q 320 130 260 165"
        class="connector loop-connector"
        :class="{ active: cycleCount > 0 && isActive('developer') }"
        fill="none"
        marker-end="url(#arrowhead)"
      />
      <text x="340" y="200" class="loop-label">loop until</text>
      <text x="340" y="218" class="loop-label">approved</text>
    </svg>
    <!-- Screen reader announcement -->
    <span class="sr-only" role="status" aria-live="polite">
      {{ isApproved() ? 'Workflow complete: changes approved' : `Current step: ${currentAgent}` }}
    </span>
  </div>
</template>

<style scoped>
.workflow-hero {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  max-width: 400px;
  margin: 0 auto;
}

.workflow-diagram {
  width: 100%;
  height: auto;
}

/* Node styling */
.node-bg {
  fill: var(--vp-c-bg-alt);
  stroke: var(--vp-c-divider);
  stroke-width: 2;
  transition: all 0.3s ease;
}

.agent-node.active .node-bg {
  stroke: var(--vp-c-brand-1);
  stroke-width: 3;
}

.node-bg.approved {
  stroke: var(--vp-c-tip-1);
  fill: var(--vp-c-tip-soft);
}

.node-label {
  fill: var(--vp-c-text-1);
  font-family: var(--amelia-font-heading);
  font-size: 18px;
  font-weight: 600;
  text-anchor: middle;
}

.node-sublabel {
  fill: var(--vp-c-text-2);
  font-family: var(--vp-font-family-base);
  font-size: 14px;
  text-anchor: middle;
}

.agent-node.active .node-label {
  fill: var(--vp-c-brand-1);
}

/* Connector styling */
.connector {
  stroke: var(--vp-c-text-3);
  stroke-width: 2;
  fill: none;
  transition: all 0.3s ease;
}

.connector.active {
  stroke: var(--vp-c-brand-1);
  stroke-width: 2;
  stroke-dasharray: 6, 4;
  animation: flowPulse 0.5s linear infinite;
}

.loop-connector {
  stroke-dasharray: 5, 5;
}

.loop-label {
  fill: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  text-anchor: start;
}

/* Pulse animation for active nodes */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

.agent-node.active .node-bg {
  animation: pulse 1.5s ease-in-out infinite;
}

/* Entrance animation */
@keyframes fadeSlideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.workflow-hero {
  animation: fadeSlideIn 0.6s ease-out;
}

/* Animated flow along connectors */
@keyframes flowPulse {
  0% {
    stroke-dashoffset: 10;
  }
  100% {
    stroke-dashoffset: 0;
  }
}

/* Screen reader only utility */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* Respect user's reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  .workflow-hero,
  .agent-node,
  .connector,
  .node-bg {
    animation: none !important;
    transition: none !important;
  }
}

/* Hide on mobile/tablet - too complex for small screens */
@media (max-width: 1024px) {
  .workflow-hero {
    display: none;
  }
}
</style>
