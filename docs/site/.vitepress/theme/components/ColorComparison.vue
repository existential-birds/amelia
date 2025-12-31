<script setup lang="ts">
import { ref } from 'vue'

interface ColorPair {
  name: string
  dark: { hex: string; oklch?: string }
  light: { hex: string; oklch?: string }
  usage?: string
}

interface Props {
  colors: ColorPair[]
  title?: string
}

defineProps<Props>()

const copiedIndex = ref<number | null>(null)
const copiedSide = ref<'dark' | 'light' | null>(null)

const copyToClipboard = async (text: string, index: number, side: 'dark' | 'light') => {
  try {
    await navigator.clipboard.writeText(text)
    copiedIndex.value = index
    copiedSide.value = side
    setTimeout(() => {
      copiedIndex.value = null
      copiedSide.value = null
    }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}
</script>

<template>
  <div class="color-comparison">
    <h3 v-if="title" class="comparison-title">{{ title }}</h3>

    <!-- Header -->
    <div class="comparison-header">
      <div class="header-token">Token</div>
      <div class="header-dark">Dark Mode</div>
      <div class="header-light">Light Mode</div>
      <div class="header-usage">Usage</div>
    </div>

    <!-- Color rows -->
    <div
      v-for="(color, index) in colors"
      :key="color.name"
      class="comparison-row"
    >
      <!-- Token name -->
      <div class="cell-token">
        <code>{{ color.name }}</code>
      </div>

      <!-- Dark mode swatch -->
      <div class="cell-swatch">
        <button
          type="button"
          class="swatch-container"
          :style="{ backgroundColor: color.dark.hex }"
          :title="`Click to copy ${color.dark.hex}`"
          :aria-label="`Copy ${color.dark.hex} to clipboard`"
          @click="copyToClipboard(color.dark.hex, index, 'dark')"
        >
          <div v-if="copiedIndex === index && copiedSide === 'dark'" class="copied-feedback">
            Copied!
          </div>
        </button>
        <div class="swatch-details">
          <span class="hex-value">{{ color.dark.hex }}</span>
          <span v-if="color.dark.oklch" class="oklch-value">{{ color.dark.oklch }}</span>
        </div>
      </div>

      <!-- Light mode swatch -->
      <div class="cell-swatch">
        <button
          type="button"
          class="swatch-container"
          :style="{ backgroundColor: color.light.hex }"
          :title="`Click to copy ${color.light.hex}`"
          :aria-label="`Copy ${color.light.hex} to clipboard`"
          @click="copyToClipboard(color.light.hex, index, 'light')"
        >
          <div v-if="copiedIndex === index && copiedSide === 'light'" class="copied-feedback">
            Copied!
          </div>
        </button>
        <div class="swatch-details">
          <span class="hex-value">{{ color.light.hex }}</span>
          <span v-if="color.light.oklch" class="oklch-value">{{ color.light.oklch }}</span>
        </div>
      </div>

      <!-- Usage description -->
      <div class="cell-usage">
        {{ color.usage }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.color-comparison {
  margin: 1.5rem 0 2rem;
  border: 1px solid var(--vp-c-border);
  border-radius: 12px;
  overflow: hidden;
  background-color: var(--vp-c-bg-soft);
}

.comparison-title {
  margin: 0;
  padding: 1rem 1.25rem;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
  border-bottom: 1px solid var(--vp-c-border);
  background-color: var(--vp-c-bg);
}

.comparison-header {
  display: grid;
  grid-template-columns: 160px 1fr 1fr 120px;
  gap: 1px;
  padding: 0.75rem 1rem;
  background-color: var(--vp-c-bg);
  border-bottom: 2px solid var(--vp-c-border);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vp-c-text-2);
}

.header-token { grid-column: 1; }
.header-dark { grid-column: 2; text-align: center; }
.header-light { grid-column: 3; text-align: center; }
.header-usage { grid-column: 4; }

.comparison-row {
  display: grid;
  grid-template-columns: 160px 1fr 1fr 120px;
  gap: 1px;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--vp-c-divider);
  align-items: center;
  transition: background-color 0.15s ease;
}

.comparison-row:last-child {
  border-bottom: none;
}

.comparison-row:hover {
  background-color: var(--vp-c-bg);
}

.cell-token {
  font-family: var(--vp-font-family-mono);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.cell-token code {
  background: none;
  padding: 0;
  font-size: inherit;
  color: inherit;
}

.cell-swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.5rem;
}

.swatch-container {
  width: 100%;
  height: 48px;
  border-radius: 6px;
  cursor: pointer;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--shadow-color-soft);
  box-shadow: 0 2px 4px var(--shadow-color-subtle);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  padding: 0;
  font: inherit;
}

.swatch-container:hover {
  transform: scale(1.02);
  box-shadow: 0 4px 8px var(--shadow-color-soft);
}

.swatch-container:active {
  transform: scale(0.98);
}

.copied-feedback {
  background-color: rgba(0, 0, 0, 0.85);
  color: white;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  animation: fadeInOut 2s ease;
}

@keyframes fadeInOut {
  0% { opacity: 0; transform: scale(0.9); }
  15% { opacity: 1; transform: scale(1); }
  85% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(0.9); }
}

.swatch-details {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
}

.hex-value {
  font-family: var(--vp-font-family-mono);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.oklch-value {
  font-family: var(--vp-font-family-mono);
  font-size: 0.7rem;
  color: var(--vp-c-text-3);
  white-space: nowrap;
}

.cell-usage {
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  line-height: 1.4;
}

/* Responsive: stack on mobile */
@media (max-width: 900px) {
  .comparison-header {
    display: none;
  }

  .comparison-row {
    grid-template-columns: 1fr;
    gap: 0.75rem;
    padding: 1rem;
  }

  .cell-token {
    font-size: 0.9rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--vp-c-divider);
  }

  .cell-swatch {
    flex-direction: row;
    justify-content: flex-start;
    gap: 1rem;
    padding: 0;
  }

  .cell-swatch::before {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--vp-c-text-3);
    min-width: 50px;
  }

  .cell-swatch:nth-of-type(2)::before {
    content: 'Dark';
  }

  .cell-swatch:nth-of-type(3)::before {
    content: 'Light';
  }

  .swatch-container {
    width: 80px;
    height: 40px;
    flex-shrink: 0;
  }

  .swatch-details {
    align-items: flex-start;
    text-align: left;
  }

  .cell-usage {
    padding-top: 0.5rem;
    border-top: 1px solid var(--vp-c-divider);
    font-style: italic;
  }
}
</style>
