<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

type Phase = 'command' | 'fetch' | 'plan' | 'approval' | 'approved' | 'execute' | 'review' | 'done'

// State
const currentPhase = ref<Phase>('command')
const typedCommand = ref('')
const visibleLines = ref<number>(0)
const isTyping = ref(true)
const prefersReducedMotion = ref(false)
const executeStep = ref(0) // 0 = not started, 1-3 = steps

// Animation control
const animationActive = ref(true)
const animationTimeouts = new Set<number>()
const fullCommand = 'amelia start 42 --profile research'

// Line visibility control
const showLine = (lineNumber: number) => visibleLines.value >= lineNumber

// Phase-based line numbers
const LINES = {
  COMMAND: 1,
  BLANK_1: 2,
  FETCH: 3,
  ISSUE: 4,
  BLANK_2: 5,
  PLAN: 6,
  PLAN_READY: 7,
  BLANK_3: 8,
  PLAN_GOAL: 9,
  BLANK_4: 10,
  APPROVAL: 11,
  APPROVED: 12,
  BLANK_5: 13,
  TOOL_1: 14,
  TOOL_2: 15,
  TOOL_3: 16,
  EXECUTE_DONE: 17,
  BLANK_6: 18,
  REVIEW: 19,
  REVIEW_DONE: 20,
  BLANK_7: 21,
  FINAL: 22,
  BLANK_8: 23,
}

// Animation sequence
const startAnimation = async () => {
  if (prefersReducedMotion.value) {
    // Show final state immediately
    typedCommand.value = fullCommand
    visibleLines.value = LINES.BLANK_8
    currentPhase.value = 'done'
    return
  }

  // Phase 1: Type command (2.5s)
  currentPhase.value = 'command'
  typedCommand.value = ''
  visibleLines.value = LINES.COMMAND
  isTyping.value = true

  for (let i = 0; i <= fullCommand.length; i++) {
    if (!animationActive.value) return // Cancelled
    typedCommand.value = fullCommand.slice(0, i)
    await sleep(2500 / fullCommand.length)
  }
  isTyping.value = false
  await sleep(400)

  // Phase 2: Fetch issue (1.2s)
  currentPhase.value = 'fetch'
  visibleLines.value = LINES.BLANK_1
  await sleep(150)
  visibleLines.value = LINES.FETCH
  await sleep(900) // Spinner visible
  visibleLines.value = LINES.ISSUE
  await sleep(300)

  // Phase 3: Plan (1.8s)
  currentPhase.value = 'plan'
  visibleLines.value = LINES.BLANK_2
  await sleep(150)
  visibleLines.value = LINES.PLAN
  await sleep(600) // Spinner visible
  visibleLines.value = LINES.PLAN_READY
  await sleep(300)
  visibleLines.value = LINES.BLANK_3
  await sleep(150)
  visibleLines.value = LINES.PLAN_GOAL // Plan goal appears
  await sleep(600)

  // Phase 4: Approval gate (3.0s - KEY pause)
  currentPhase.value = 'approval'
  visibleLines.value = LINES.BLANK_4
  await sleep(150)
  visibleLines.value = LINES.APPROVAL
  await sleep(2850) // Long pause with pulsing cursor

  // Phase 5: Approved (0.8s)
  currentPhase.value = 'approved'
  visibleLines.value = LINES.APPROVED
  await sleep(800)

  // Phase 6: Execute (2.4s)
  currentPhase.value = 'execute'
  visibleLines.value = LINES.BLANK_5
  await sleep(150)

  // Show agentic tool calls
  for (let step = 1; step <= 3; step++) {
    executeStep.value = step
    visibleLines.value = LINES.TOOL_1 + (step - 1)
    await sleep(700)
  }

  visibleLines.value = LINES.EXECUTE_DONE
  await sleep(450)

  // Phase 7: Review (1.5s)
  currentPhase.value = 'review'
  visibleLines.value = LINES.BLANK_6
  await sleep(150)
  visibleLines.value = LINES.REVIEW
  await sleep(900)
  visibleLines.value = LINES.REVIEW_DONE
  await sleep(450)

  // Phase 8: Complete (2.5s)
  currentPhase.value = 'done'
  visibleLines.value = LINES.BLANK_7
  await sleep(150)
  visibleLines.value = LINES.FINAL
  await sleep(150)
  visibleLines.value = LINES.BLANK_8
  await sleep(3000)

  // Restart animation cleanly
  executeStep.value = 0
  if (animationActive.value) {
    startAnimation()
  }
}

const sleep = (ms: number): Promise<void> => {
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      animationTimeouts.delete(timeoutId)
      resolve()
    }, ms)
    animationTimeouts.add(timeoutId)
  })
}

onMounted(() => {
  // Check for reduced motion preference
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion.value = mediaQuery.matches

  // Start animation
  startAnimation()
})

onUnmounted(() => {
  animationActive.value = false
  animationTimeouts.forEach((timeoutId) => clearTimeout(timeoutId))
  animationTimeouts.clear()
})
</script>

<template>
  <div
    class="terminal-hero"
    :class="{ 'reduced-motion': prefersReducedMotion }"
    role="region"
    aria-label="Amelia terminal workflow demonstration"
  >
    <!-- Window chrome -->
    <div class="terminal-chrome">
      <div class="traffic-lights">
        <span class="traffic-light close" aria-hidden="true"></span>
        <span class="traffic-light minimize" aria-hidden="true"></span>
        <span class="traffic-light maximize" aria-hidden="true"></span>
      </div>
      <div class="terminal-title">amelia</div>
    </div>

    <!-- Terminal body -->
    <div class="terminal-body">
      <!-- Command line -->
      <div v-if="showLine(LINES.COMMAND)" class="terminal-line prompt">
        <span class="prompt-symbol">$</span>
        <span class="command">{{ typedCommand }}</span>
        <span v-if="isTyping" class="cursor">█</span>
      </div>

      <div v-if="showLine(LINES.BLANK_1)" class="terminal-line blank"></div>

      <!-- Fetch phase -->
      <div v-if="showLine(LINES.FETCH) && !showLine(LINES.ISSUE)" class="terminal-line progress">
        <span class="spinner">◐</span>
        <span>Analyzing issue context...</span>
      </div>

      <div v-if="showLine(LINES.ISSUE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Issue #42: Implement recursive sub-agent decomposition</span>
      </div>

      <div v-if="showLine(LINES.BLANK_2)" class="terminal-line blank"></div>

      <!-- Plan phase -->
      <div v-if="showLine(LINES.PLAN) && !showLine(LINES.PLAN_READY)" class="terminal-line progress">
        <span class="spinner">◐</span>
        <span>Architect decomposing task...</span>
      </div>

      <div v-if="showLine(LINES.PLAN_READY)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Plan ready</span>
      </div>

      <div v-if="showLine(LINES.BLANK_3)" class="terminal-line blank"></div>

      <!-- Plan Goal -->
      <div v-if="showLine(LINES.PLAN_GOAL)" class="plan-goal">
        <div class="goal-title">◆ Strategy</div>
        <div class="goal-text">  RLM-inspired recursive decomposition</div>
        <div class="goal-files">  Patterns: sub-agents, context-folding</div>
      </div>

      <div v-if="showLine(LINES.BLANK_4)" class="terminal-line blank"></div>

      <!-- Approval phase -->
      <div v-if="showLine(LINES.APPROVAL) && !showLine(LINES.APPROVED)" class="terminal-line progress approval">
        <span class="spinner">◐</span>
        <span>Awaiting human approval<span class="pulsing-dots">...</span></span>
      </div>

      <div v-if="showLine(LINES.APPROVED)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Approved via dashboard</span>
      </div>

      <div v-if="showLine(LINES.BLANK_5)" class="terminal-line blank"></div>

      <!-- Execute phase - agentic tool calls -->
      <div v-if="showLine(LINES.TOOL_1) && executeStep >= 1 && !showLine(LINES.EXECUTE_DONE)" class="terminal-line tool-call">
        <span class="tool-icon">→</span>
        <span class="tool-name">spawn</span>
        <span class="tool-cmd">codebase-analyzer (src/)</span>
      </div>

      <div v-if="showLine(LINES.TOOL_2) && executeStep >= 2 && !showLine(LINES.EXECUTE_DONE)" class="terminal-line tool-call">
        <span class="tool-icon">→</span>
        <span class="tool-name">spawn</span>
        <span class="tool-cmd">test-scanner (tests/)</span>
      </div>

      <div v-if="showLine(LINES.TOOL_3) && executeStep >= 3 && !showLine(LINES.EXECUTE_DONE)" class="terminal-line tool-call">
        <span class="tool-icon">→</span>
        <span class="tool-name">spawn</span>
        <span class="tool-cmd">doc-reviewer (docs/)</span>
      </div>

      <div v-if="showLine(LINES.EXECUTE_DONE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Sub-agents complete</span>
      </div>

      <div v-if="showLine(LINES.BLANK_6)" class="terminal-line blank"></div>

      <!-- Review phase -->
      <div v-if="showLine(LINES.REVIEW) && !showLine(LINES.REVIEW_DONE)" class="terminal-line progress">
        <span class="spinner">◐</span>
        <span>Synthesizing results...</span>
      </div>

      <div v-if="showLine(LINES.REVIEW_DONE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Changes ready for review</span>
      </div>

      <div v-if="showLine(LINES.BLANK_7)" class="terminal-line blank"></div>

      <!-- Final message -->
      <div v-if="showLine(LINES.FINAL)" class="terminal-line info">
        <span class="indent"></span>
        <span>View results at <span class="accent">localhost:8420</span></span>
      </div>

      <div v-if="showLine(LINES.BLANK_8)" class="terminal-line blank"></div>
    </div>
  </div>
</template>

<style scoped>
.terminal-hero {
  max-width: 800px;
  margin: 0 auto;
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  line-height: 1.6;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 32px var(--shadow-color-strong);
}

/* Window chrome */
.terminal-chrome {
  background: var(--terminal-chrome);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--terminal-border);
}

.traffic-lights {
  display: flex;
  gap: 8px;
}

.traffic-light {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.traffic-light.close {
  background: #ff5f57;
}

.traffic-light.minimize {
  background: #febc2e;
}

.traffic-light.maximize {
  background: #28c840;
}

.terminal-title {
  color: var(--terminal-text-dim);
  font-size: 13px;
  font-weight: 500;
}

/* Terminal body */
.terminal-body {
  background: var(--terminal-bg);
  padding: 24px;
  color: var(--terminal-text);
  height: 480px;
  overflow-y: auto;
}

.terminal-line {
  margin: 0;
  padding: 0;
  opacity: 1;
  animation: fadeIn 0.2s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.terminal-line.blank {
  height: 1.6em;
}

.terminal-line.prompt {
  color: var(--terminal-text);
}

.prompt-symbol {
  color: var(--terminal-success);
  margin-right: 8px;
}

.command {
  color: var(--terminal-text);
}

.cursor {
  color: var(--terminal-text);
  animation: blink 1s step-end infinite;
  margin-left: 2px;
}

@keyframes blink {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

.terminal-line.success {
  color: var(--terminal-text);
}

.checkmark {
  color: var(--terminal-success);
  margin-right: 8px;
}

.terminal-line.progress {
  color: var(--terminal-text);
}

.spinner {
  color: var(--terminal-accent);
  margin-right: 8px;
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.terminal-line.approval .pulsing-dots {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.terminal-line.info {
  color: var(--terminal-text-dim);
}

.accent {
  color: var(--terminal-accent);
}

.indent {
  display: inline-block;
  width: 32px;
}

/* Plan Goal box */
.plan-goal {
  color: var(--terminal-text-dim);
  margin-left: 32px;
  font-family: inherit;
  white-space: pre;
  animation: fadeIn 0.3s ease-in;
}

.goal-title,
.goal-text,
.goal-files {
  margin: 0;
  padding: 0;
  line-height: 1.6;
}

.goal-title {
  color: var(--terminal-accent);
  font-weight: 500;
}

.goal-files {
  color: var(--terminal-text-dim);
  opacity: 0.8;
}

/* Agentic tool calls */
.terminal-line.tool-call {
  color: var(--terminal-text);
}

.tool-icon {
  color: var(--terminal-accent);
  margin-right: 8px;
}

.tool-name {
  color: var(--terminal-success);
  font-weight: 500;
  margin-right: 8px;
}

.tool-name::after {
  content: ':';
}

.tool-cmd {
  color: var(--terminal-text-dim);
}

/* Reduced motion: disable animations */
.terminal-hero.reduced-motion {
  transition: none;
}

.terminal-hero.reduced-motion .terminal-line {
  animation: none;
}

.terminal-hero.reduced-motion .cursor {
  animation: none;
  opacity: 1;
}

.terminal-hero.reduced-motion .spinner {
  animation: none;
}

.terminal-hero.reduced-motion .pulsing-dots {
  animation: none;
  opacity: 1;
}

.terminal-hero.reduced-motion .plan-goal {
  animation: none;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .terminal-hero {
    font-size: 12px;
    border-radius: 6px;
  }

  .terminal-body {
    padding: 16px;
    height: 380px;
  }

  .terminal-chrome {
    padding: 10px 12px;
  }

  .traffic-light {
    width: 10px;
    height: 10px;
  }
}

/* Dark mode support (terminal is always inverted) */
@media (prefers-color-scheme: light) {
  .terminal-hero {
    /* Keep terminal theme from CSS variables (inverted) */
  }
}
</style>
