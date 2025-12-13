/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

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

export default {
  extends: DefaultTheme,
  Layout: () => {
    return h(DefaultTheme.Layout, null, {
      // Custom layout slots can be added here
      // https://vitepress.dev/guide/extending-default-theme#layout-slots
    })
  },
  enhanceApp({ app, router, siteData }) {
    // App-level customizations can be added here
  }
} satisfies Theme
