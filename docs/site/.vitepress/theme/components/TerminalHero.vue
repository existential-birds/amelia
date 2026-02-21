<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'

type Phase =
  | 'command'
  | 'started'
  | 'architect'
  | 'approval'
  | 'approved'
  | 'developer'
  | 'reviewer'
  | 'done'

// State
const currentPhase = ref<Phase>('command')
const typedCommand = ref('')
const visibleLines = ref<number>(0)
const isTyping = ref(true)
const prefersReducedMotion = ref(false)

// Terminal body ref for auto-scroll
const terminalBody = ref<HTMLElement | null>(null)

// Animation control
const animationActive = ref(true)
const animationTimeouts = new Set<number>()
const fullCommand = 'amelia start PROJ-42 --stream'

// Line visibility control
const showLine = (lineNumber: number) => visibleLines.value >= lineNumber

// Auto-scroll to bottom when new lines appear
watch(visibleLines, () => {
  nextTick(() => {
    if (terminalBody.value) {
      terminalBody.value.scrollTop = terminalBody.value.scrollHeight
    }
  })
})

// Phase-based line numbers — mirrors real `amelia start --stream` output
const LINES = {
  COMMAND: 1,
  BLANK_1: 2,
  // start_command output
  STARTED: 3,
  ISSUE: 4,
  WORKTREE: 5,
  STATUS: 6,
  BLANK_2: 7,
  DASHBOARD: 8,
  BLANK_3: 9,
  // stream: architect stage
  STAGE_ARCHITECT: 10,
  CLAUDE_HEADER: 11,
  CLAUDE_MSG: 12,
  TOOL_1: 13,
  TOOL_2: 14,
  STAGE_ARCHITECT_DONE: 15,
  BLANK_4: 16,
  // approval gate
  APPROVAL: 17,
  APPROVED: 18,
  BLANK_5: 19,
  // stream: developer stage
  STAGE_DEVELOPER: 20,
  DEV_TOOL_1: 21,
  DEV_TOOL_2: 22,
  DEV_TOOL_3: 23,
  STAGE_DEVELOPER_DONE: 24,
  BLANK_6: 25,
  // stream: reviewer stage
  STAGE_REVIEWER: 26,
  STAGE_REVIEWER_DONE: 27,
  REVIEW_RESULT: 28,
  BLANK_7: 29,
  // completion
  COMPLETED: 30,
  BLANK_8: 31,
}

// Animation sequence
const startAnimation = async () => {
  if (prefersReducedMotion.value) {
    typedCommand.value = fullCommand
    visibleLines.value = LINES.BLANK_8
    currentPhase.value = 'done'
    return
  }

  // Phase 1: Type command (2s)
  currentPhase.value = 'command'
  typedCommand.value = ''
  visibleLines.value = LINES.COMMAND
  isTyping.value = true

  for (let i = 0; i <= fullCommand.length; i++) {
    if (!animationActive.value) return
    typedCommand.value = fullCommand.slice(0, i)
    await sleep(2000 / fullCommand.length)
  }
  isTyping.value = false
  await sleep(300)

  // Phase 2: Workflow started output (1.2s)
  currentPhase.value = 'started'
  visibleLines.value = LINES.BLANK_1
  await sleep(100)
  visibleLines.value = LINES.STARTED
  await sleep(100)
  visibleLines.value = LINES.ISSUE
  await sleep(80)
  visibleLines.value = LINES.WORKTREE
  await sleep(80)
  visibleLines.value = LINES.STATUS
  await sleep(200)
  visibleLines.value = LINES.BLANK_2
  await sleep(80)
  visibleLines.value = LINES.DASHBOARD
  await sleep(400)

  // Phase 3: Architect stage (2.5s)
  currentPhase.value = 'architect'
  visibleLines.value = LINES.BLANK_3
  await sleep(100)
  visibleLines.value = LINES.STAGE_ARCHITECT
  await sleep(400)
  visibleLines.value = LINES.CLAUDE_HEADER
  await sleep(150)
  visibleLines.value = LINES.CLAUDE_MSG
  await sleep(400)
  visibleLines.value = LINES.TOOL_1
  await sleep(350)
  visibleLines.value = LINES.TOOL_2
  await sleep(350)
  visibleLines.value = LINES.STAGE_ARCHITECT_DONE
  await sleep(300)

  // Phase 4: Approval gate (2.5s)
  currentPhase.value = 'approval'
  visibleLines.value = LINES.BLANK_4
  await sleep(100)
  visibleLines.value = LINES.APPROVAL
  await sleep(2400)

  // Phase 5: Approved (0.6s)
  currentPhase.value = 'approved'
  visibleLines.value = LINES.APPROVED
  await sleep(600)

  // Phase 6: Developer stage (2s)
  currentPhase.value = 'developer'
  visibleLines.value = LINES.BLANK_5
  await sleep(100)
  visibleLines.value = LINES.STAGE_DEVELOPER
  await sleep(350)
  visibleLines.value = LINES.DEV_TOOL_1
  await sleep(350)
  visibleLines.value = LINES.DEV_TOOL_2
  await sleep(350)
  visibleLines.value = LINES.DEV_TOOL_3
  await sleep(350)
  visibleLines.value = LINES.STAGE_DEVELOPER_DONE
  await sleep(300)

  // Phase 7: Reviewer stage (1.2s)
  currentPhase.value = 'reviewer'
  visibleLines.value = LINES.BLANK_6
  await sleep(100)
  visibleLines.value = LINES.STAGE_REVIEWER
  await sleep(400)
  visibleLines.value = LINES.STAGE_REVIEWER_DONE
  await sleep(200)
  visibleLines.value = LINES.REVIEW_RESULT
  await sleep(400)

  // Phase 8: Complete (2.5s)
  currentPhase.value = 'done'
  visibleLines.value = LINES.BLANK_7
  await sleep(100)
  visibleLines.value = LINES.COMPLETED
  await sleep(100)
  visibleLines.value = LINES.BLANK_8
  await sleep(3000)

  // Restart
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
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion.value = mediaQuery.matches
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
    <div ref="terminalBody" class="terminal-body">
      <!-- $ amelia start PROJ-42 --stream -->
      <div v-if="showLine(LINES.COMMAND)" class="terminal-line prompt">
        <span class="prompt-symbol">$</span>
        <span class="command">{{ typedCommand }}</span>
        <span v-if="isTyping" class="cursor">█</span>
      </div>

      <div v-if="showLine(LINES.BLANK_1)" class="terminal-line blank"></div>

      <!-- ✓ Workflow started: a1b2c3d4 -->
      <div v-if="showLine(LINES.STARTED)" class="terminal-line">
        <span class="checkmark">✓</span>
        <span>Workflow started: </span><span class="text-bold">a1b2c3d4</span>
      </div>

      <!-- Indented workflow details -->
      <div v-if="showLine(LINES.ISSUE)" class="terminal-line detail">
        <span>Issue: PROJ-42</span>
      </div>
      <div v-if="showLine(LINES.WORKTREE)" class="terminal-line detail">
        <span>Worktree: ~/projects/myapp</span>
      </div>
      <div v-if="showLine(LINES.STATUS)" class="terminal-line detail">
        <span>Status: running</span>
      </div>

      <div v-if="showLine(LINES.BLANK_2)" class="terminal-line blank"></div>

      <!-- View in dashboard: http://127.0.0.1:8420 -->
      <div v-if="showLine(LINES.DASHBOARD)" class="terminal-line dim">
        <span>View in dashboard: </span><span class="accent">http://127.0.0.1:8420</span>
      </div>

      <div v-if="showLine(LINES.BLANK_3)" class="terminal-line blank"></div>

      <!-- Starting architect... -->
      <div v-if="showLine(LINES.STAGE_ARCHITECT)" class="terminal-line dim">
        <span>Starting architect...</span>
      </div>

      <!-- ◆ Claude -->
      <div v-if="showLine(LINES.CLAUDE_HEADER)" class="terminal-line claude-header">
        <span class="claude-diamond">◆</span>
        <span class="claude-name">Claude</span>
      </div>

      <!-- │ Analyzing codebase structure and decomposing task... -->
      <div v-if="showLine(LINES.CLAUDE_MSG)" class="terminal-line claude-msg">
        <span class="pipe">│</span>
        <span>Analyzing codebase structure and decomposing task...</span>
      </div>

      <!-- ⚡ [architect] Tool: Read -->
      <div v-if="showLine(LINES.TOOL_1)" class="terminal-line tool-call">
        <span class="tool-icon">⚡</span>
        <span class="tool-agent">[architect]</span>
        <span> Tool: </span><span class="tool-name">Read</span>
      </div>

      <!-- ⚡ [architect] Tool: Grep -->
      <div v-if="showLine(LINES.TOOL_2)" class="terminal-line tool-call">
        <span class="tool-icon">⚡</span>
        <span class="tool-agent">[architect]</span>
        <span> Tool: </span><span class="tool-name">Grep</span>
      </div>

      <!-- Completed architect -->
      <div v-if="showLine(LINES.STAGE_ARCHITECT_DONE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Completed architect</span>
      </div>

      <div v-if="showLine(LINES.BLANK_4)" class="terminal-line blank"></div>

      <!-- Approval required: Plan ready for review -->
      <div v-if="showLine(LINES.APPROVAL) && !showLine(LINES.APPROVED)" class="terminal-line approval">
        <span class="approval-text">Approval required:</span>
        <span> Plan ready for review</span><span class="pulsing-dots">...</span>
      </div>

      <!-- Plan approved -->
      <div v-if="showLine(LINES.APPROVED)" class="terminal-line">
        <span class="checkmark">✓</span>
        <span>Plan approved</span>
      </div>

      <div v-if="showLine(LINES.BLANK_5)" class="terminal-line blank"></div>

      <!-- Starting developer... -->
      <div v-if="showLine(LINES.STAGE_DEVELOPER)" class="terminal-line dim">
        <span>Starting developer...</span>
      </div>

      <!-- ⚡ [developer] Tool: Edit -->
      <div v-if="showLine(LINES.DEV_TOOL_1)" class="terminal-line tool-call">
        <span class="tool-icon">⚡</span>
        <span class="tool-agent">[developer]</span>
        <span> Tool: </span><span class="tool-name">Edit</span>
      </div>

      <!-- ⚡ [developer] Tool: Write -->
      <div v-if="showLine(LINES.DEV_TOOL_2)" class="terminal-line tool-call">
        <span class="tool-icon">⚡</span>
        <span class="tool-agent">[developer]</span>
        <span> Tool: </span><span class="tool-name">Write</span>
      </div>

      <!-- ⚡ [developer] Tool: Bash -->
      <div v-if="showLine(LINES.DEV_TOOL_3)" class="terminal-line tool-call">
        <span class="tool-icon">⚡</span>
        <span class="tool-agent">[developer]</span>
        <span> Tool: </span><span class="tool-name">Bash</span>
      </div>

      <!-- Completed developer -->
      <div v-if="showLine(LINES.STAGE_DEVELOPER_DONE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Completed developer</span>
      </div>

      <div v-if="showLine(LINES.BLANK_6)" class="terminal-line blank"></div>

      <!-- Starting reviewer... -->
      <div v-if="showLine(LINES.STAGE_REVIEWER)" class="terminal-line dim">
        <span>Starting reviewer...</span>
      </div>

      <!-- Completed reviewer -->
      <div v-if="showLine(LINES.STAGE_REVIEWER_DONE)" class="terminal-line success">
        <span class="checkmark">✓</span>
        <span>Completed reviewer</span>
      </div>

      <!-- Review approved (low severity, 0 issues) -->
      <div v-if="showLine(LINES.REVIEW_RESULT)" class="terminal-line">
        <span>Review </span><span class="review-approved">approved</span>
        <span class="dim-inline"> (low severity, 0 issues)</span>
      </div>

      <div v-if="showLine(LINES.BLANK_7)" class="terminal-line blank"></div>

      <!-- Workflow completed successfully! -->
      <div v-if="showLine(LINES.COMPLETED)" class="terminal-line completed">
        <span>Workflow completed successfully!</span>
      </div>

      <div v-if="showLine(LINES.BLANK_8)" class="terminal-line blank"></div>
    </div>
  </div>
</template>

<style scoped>
/* Hardcode dark terminal colors so site theme toggle doesn't affect it */
.terminal-hero {
  --terminal-bg: #050A07;
  --terminal-text: #E8F0DC;
  --terminal-text-dim: #6B8A78;
  --terminal-accent: #FFC857;
  --terminal-success: #5B8A72;
  --terminal-chrome: #12201A;
  --terminal-border: #3A4D42;

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
  scroll-behavior: smooth;
  scrollbar-width: none; /* Firefox */
}

.terminal-body::-webkit-scrollbar {
  display: none; /* Chrome/Safari */
}

.terminal-line {
  margin: 0;
  padding: 0;
  opacity: 1;
  animation: fadeIn 0.15s ease-in;
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

/* Prompt */
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

/* Success checkmark */
.checkmark {
  color: var(--terminal-success);
  margin-right: 8px;
}

/* Bold text */
.text-bold {
  font-weight: 600;
}

/* Indented detail lines (Issue:, Worktree:, Status:) */
.terminal-line.detail {
  padding-left: 24px;
  color: var(--terminal-text);
}

/* Dim text */
.terminal-line.dim {
  color: var(--terminal-text-dim);
}

.dim-inline {
  color: var(--terminal-text-dim);
}

/* Accent (URLs, etc.) */
.accent {
  color: var(--terminal-accent);
}

/* Claude header: ◆ Claude */
.terminal-line.claude-header {
  padding-left: 16px;
}

.claude-diamond {
  color: var(--terminal-accent);
  margin-right: 6px;
}

.claude-name {
  color: var(--terminal-accent);
  font-weight: 500;
}

/* Claude message with pipe: │ text */
.terminal-line.claude-msg {
  padding-left: 16px;
  color: var(--terminal-text);
}

.pipe {
  color: var(--terminal-text-dim);
  margin-right: 8px;
}

/* Tool calls: ⚡ [agent] Tool: name */
.terminal-line.tool-call {
  color: var(--terminal-text);
}

.tool-icon {
  color: var(--terminal-accent);
  margin-right: 4px;
}

.tool-agent {
  color: #5DADE2;
  margin-right: 2px;
}

.tool-name {
  color: var(--terminal-text);
  font-weight: 500;
}

/* Success lines */
.terminal-line.success {
  color: var(--terminal-success);
}

/* Approval */
.terminal-line.approval {
  color: var(--terminal-text);
}

.approval-text {
  color: var(--terminal-accent);
  font-weight: 600;
}

.pulsing-dots {
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

/* Review result */
.review-approved {
  color: var(--terminal-success);
  font-weight: 600;
}

/* Completion */
.terminal-line.completed {
  color: var(--terminal-success);
  font-weight: 600;
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

.terminal-hero.reduced-motion .pulsing-dots {
  animation: none;
  opacity: 1;
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
</style>
