/**
 * Amelia Design System VitePress Theme
 *
 * Custom theme extending VitePress default theme with:
 * - Custom color palette
 * - Custom typography (Bebas Neue, Barlow Condensed, Source Sans 3, IBM Plex Mono)
 * - Design system token integration
 */

import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import './style.css'
import './custom.css'
import ColorComparison from './components/ColorComparison.vue'
import TerminalHero from './components/TerminalHero.vue'
import CapabilitiesAndResearch from './components/CapabilitiesAndResearch.vue'
import CtaSection from './components/CtaSection.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app, router, siteData }) {
    // Register custom components globally
    app.component('ColorComparison', ColorComparison)
    app.component('TerminalHero', TerminalHero)
    app.component('CapabilitiesAndResearch', CapabilitiesAndResearch)
    app.component('CtaSection', CtaSection)
  }
} satisfies Theme
