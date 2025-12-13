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

  // Theme configuration
  themeConfig: {
    // Logo in navigation
    logo: '/logo/amelia-gold.svg',

    // Hide site title text in nav (logo is sufficient)
    siteTitle: false,

    // Navigation menu
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'API', link: '/api/tokens' },
      {
        text: 'Resources',
        items: [
          { text: 'GitHub', link: 'https://github.com/anderskev/amelia' },
          { text: 'License', link: '/license' }
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
      message: 'Released under the MPL-2.0 License.',
      copyright: 'Copyright © 2024-2025 Amelia Project'
    },

    // Search configuration
    search: {
      provider: 'local'
    },

    // Edit link
    editLink: {
      pattern: 'https://github.com/anderskev/amelia/edit/main/docs/site/:path',
      text: 'Edit this page on GitHub'
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
    // Register d2 as a custom language (D2 diagramming language)
    languages: [
      {
        id: 'd2',
        scopeName: 'source.d2',
        // Use YAML-like highlighting as a reasonable approximation
        grammar: {
          patterns: [
            { match: '#.*$', name: 'comment.line.d2' },
            { match: '->|<-|<->|--|:', name: 'keyword.operator.d2' },
            { match: '"[^"]*"', name: 'string.quoted.double.d2' },
            { match: "'[^']*'", name: 'string.quoted.single.d2' },
            { match: '\\b(shape|style|fill|stroke|font-color|opacity|label|icon|near|direction)\\b', name: 'keyword.control.d2' },
            { match: '\\b[a-zA-Z_][a-zA-Z0-9_-]*\\b', name: 'variable.other.d2' }
          ]
        }
      }
    ]
  },

  // Head configuration
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/logo/amelia-gold.svg' }]
    // Fonts are self-hosted via /fonts/fonts.css (imported in theme/style.css)
  ]
})
