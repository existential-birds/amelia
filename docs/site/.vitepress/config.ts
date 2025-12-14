/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { defineConfig } from 'vitepress'

/**
 * VitePress Configuration
 *
 * Configures the Amelia Design System documentation site with:
 * - Custom theme
 * - Navigation structure
 * - Search functionality
 * - Dark/light mode support
 */
export default defineConfig({
  title: 'Amelia Design System',
  description: 'Design system for the Amelia AI orchestrator',

  // Base path for deployment
  base: '/amelia/',

  // Dark mode as default
  appearance: 'dark',

  // Theme configuration
  themeConfig: {
    // Use text title styled with Bebas Neue (see style.css)
    siteTitle: 'AMELIA',

    // Navigation menu
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'API', link: '/api/tokens' },
      {
        text: 'Resources',
        items: [
          { text: 'GitHub', link: 'https://github.com/anderskev/amelia' },
          { text: 'License', link: 'https://github.com/anderskev/amelia/blob/main/LICENSE' }
        ]
      }
    ],

    // Sidebar navigation
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Installation', link: '/guide/getting-started#installation' }
          ]
        },
        {
          text: 'Design Tokens',
          items: [
            { text: 'Color System', link: '/guide/color-system' },
            { text: 'Typography', link: '/guide/typography' }
          ]
        },
        {
          text: 'Themes',
          items: [
            { text: 'Diagrams', link: '/guide/diagrams' },
            { text: 'Presentations', link: '/guide/presentations' }
          ]
        }
      ],
      '/api/': [
        {
          text: 'API Reference',
          items: [
            { text: 'Design Tokens', link: '/api/tokens' }
          ]
        }
      ]
    },

    // Social links
    socialLinks: [
      { icon: 'github', link: 'https://github.com/anderskev/amelia' }
    ],

    // Footer
    footer: {
      message: 'Built by hey-amelia bot. Released under the MPL-2.0 License.',
      copyright: 'Copyright © 2024-2025 @anderskev'
    },

    // Search configuration
    search: {
      provider: 'local'
    },

    // Last updated timestamp
    lastUpdated: {
      text: 'Last updated',
      formatOptions: {
        dateStyle: 'medium',
        timeStyle: 'short'
      }
    }
  },

  // Markdown configuration
  markdown: {
    theme: {
      light: 'github-light',
      dark: 'github-dark'
    },
    lineNumbers: true,
    // Map d2 code blocks to YAML highlighting (similar syntax)
    // D2 is a diagramming language (https://d2lang.com) with YAML-like syntax
    languageAlias: {
      'd2': 'yaml'
    }
  },

  // Head configuration
  // Note: VitePress does NOT auto-prepend base path to head URLs - must include manually
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/amelia/logo/amelia-gold.svg' }],
    ['link', { rel: 'stylesheet', href: '/amelia/fonts/fonts.css' }]
  ]
})
