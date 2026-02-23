<template>
  <section class="amelia-section capabilities-research" aria-label="Agent orchestration capabilities">
    <h2 class="section-heading">Capabilities</h2>
    <ul ref="gridRef" class="capabilities-grid" role="list">
      <li
        v-for="(item, i) in items"
        :key="item.capability"
        class="capability"
        :class="{ 'is-visible': visibleItems.has(i) }"
        :style="{ '--reveal-delay': `${i * 80}ms` }"
      >
        <span class="capability-index" aria-hidden="true">{{ String(i + 1).padStart(2, '0') }}</span>
        <div class="capability-content">
          <strong class="capability-name">{{ item.capability }}</strong>
          <span class="capability-detail">{{ item.detail }}</span>
        </div>
      </li>
    </ul>
    <a
      :href="withBase('/architecture/inspiration')"
      class="research-link"
      :class="{ 'is-visible': linkVisible }"
      aria-label="View full research foundations"
    >
      Full research foundations &rarr;
    </a>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { withBase } from 'vitepress'

const items = [
  { capability: 'Plan, build, review, ship', detail: 'Architect plans, you approve, Developer codes, Reviewer checks — looping on feedback until it passes.' },
  { capability: 'RAG-powered context', detail: 'Agents query your project docs via pgvector with hierarchical retrieval.' },
  { capability: 'Sandboxed execution', detail: 'Code runs in Docker with network isolation. Hard decisions route to a dedicated reasoning model.' },
  { capability: 'Mix models and drivers', detail: 'Assign different LLMs and driver types (CLI or API) per agent role.' },
  { capability: 'Resilient workflows', detail: 'Resume from checkpoints, configure via profiles, generate specs from issues.' },
  { capability: 'Real-time dashboard', detail: 'WebSocket-powered UI shows agent progress as it happens.' },
]

const gridRef = ref<HTMLElement | null>(null)
const visibleItems = ref<Set<number>>(new Set())
const linkVisible = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (prefersReducedMotion) {
    items.forEach((_, i) => visibleItems.value.add(i))
    linkVisible.value = true
    return
  }

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const el = entry.target as HTMLElement
          const index = Number(el.dataset.index)
          if (!isNaN(index)) {
            visibleItems.value = new Set([...visibleItems.value, index])
          }
          if (el.classList.contains('research-link')) {
            linkVisible.value = true
          }
          observer?.unobserve(el)
        }
      })
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  )

  if (gridRef.value) {
    const children = gridRef.value.querySelectorAll('.capability')
    children.forEach((child, i) => {
      ;(child as HTMLElement).dataset.index = String(i)
      observer?.observe(child)
    })
  }

  const link = gridRef.value?.parentElement?.querySelector('.research-link')
  if (link) observer?.observe(link)
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<style scoped>
.capabilities-research {
  max-width: 100%;
  padding-left: 0;
  padding-right: 0;
  padding-top: 2rem;
  padding-bottom: 2.5rem;
}

.section-heading {
  font-family: var(--vp-font-family-mono);
  font-weight: 500;
  font-size: 1.75rem;
  letter-spacing: -0.02em;
  text-transform: uppercase;
  color: var(--vp-c-heading-1);
  margin-bottom: 1.5rem;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}

.capability {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 0.625rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.4s ease, transform 0.4s ease;
  transition-delay: var(--reveal-delay, 0ms);
}

.capability.is-visible {
  opacity: 1;
  transform: translateY(0);
}

.capability-index {
  font-family: var(--vp-font-family-mono);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  line-height: 1.4;
  letter-spacing: 0.02em;
  flex-shrink: 0;
  padding-top: 0.0625rem;
}

.capability-content {
  display: flex;
  flex-direction: column;
}

.capability-name {
  font-family: var(--vp-font-family-mono);
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--vp-c-text-1);
  line-height: 1.4;
}

.capability-detail {
  font-size: 0.875rem;
  color: var(--vp-c-text-2);
  line-height: 1.5;
  margin-top: 0.125rem;
}

.research-link {
  display: inline-block;
  margin-top: 1.25rem;
  font-family: var(--vp-font-family-mono);
  font-size: 0.8125rem;
  color: var(--vp-c-brand-1);
  font-weight: 500;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.4s ease 0.1s, transform 0.4s ease 0.1s, text-decoration-color 0.2s ease;
}

.research-link.is-visible {
  opacity: 1;
  transform: translateY(0);
}

.research-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .capabilities-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .capability,
  .research-link {
    opacity: 1;
    transform: none;
    transition: none;
  }
}
</style>
