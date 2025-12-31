/**
 * Amelia Design System VitePress Theme
 *
 * Custom theme extending VitePress default theme with:
 * - Custom color palette
 * - Custom typography (Bebas Neue, Barlow Condensed, Source Sans 3, IBM Plex Mono)
 * - Design system token integration
 */

import { h } from 'vue'
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import './style.css'
import './custom.css'
import ColorComparison from './components/ColorComparison.vue'
import AnimatedWorkflowHero from './components/AnimatedWorkflowHero.vue'
import TerminalHero from './components/TerminalHero.vue'

export default {
  extends: DefaultTheme,
  Layout: () => {
    return h(DefaultTheme.Layout, null, {
      // Inject animated workflow diagram into the hero image slot
      'home-hero-image': () => h(AnimatedWorkflowHero)
    })
  },
  enhanceApp({ app, router, siteData }) {
    // Register custom components globally
    app.component('ColorComparison', ColorComparison)
    app.component('AnimatedWorkflowHero', AnimatedWorkflowHero)
    app.component('TerminalHero', TerminalHero)
  }
} satisfies Theme
