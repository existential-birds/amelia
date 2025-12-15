/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { defineConfig } from 'vitepress'

/**
 * Shared sidebar configuration for Ideas, Reference, and Design System sections.
 * Used across multiple URL prefixes to maintain consistent navigation.
 */
const sharedSidebar = [
  {
    text: 'Ideas & Explorations',
    items: [
      { text: 'Overview', link: '/ideas/' },
      { text: 'Session Continuity', link: '/ideas/session-continuity' },
      { text: 'CAPEX Tracking', link: '/ideas/capex-tracking' },
      { text: 'Knowledge Library', link: '/ideas/knowledge-library' },
      { text: 'AWS AgentCore', link: '/ideas/aws-agentcore' },
      { text: 'Debate Mode', link: '/ideas/debate-mode' },
      { text: 'Spec Builder', link: '/ideas/spec-builder' },
      { text: 'Planning Workflows', link: '/ideas/planning-workflows' }
    ]
  },
  {
    text: 'Research',
    items: [
      { text: 'Benchmarking', link: '/ideas/research/benchmarking' },
      { text: '12-Factor Compliance', link: '/ideas/research/12-factor-compliance' },
      { text: 'Context Engineering', link: '/ideas/research/context-engineering-gaps' },
      { text: 'Knowledge Agents', link: '/ideas/research/knowledge-agents' }
    ]
  },
  {
    text: 'Reference',
    items: [
      { text: 'Roadmap', link: '/reference/roadmap' }
    ]
  },
  {
    text: 'Design System',
    collapsed: true,
    items: [
      { text: 'Getting Started', link: '/design-system/' },
      { text: 'Color System', link: '/design-system/color-system' },
      { text: 'Typography', link: '/design-system/typography' },
      { text: 'Diagrams', link: '/design-system/diagrams' },
      { text: 'Presentations', link: '/design-system/presentations' },
      { text: 'Design Tokens', link: '/design-system/tokens' }
    ]
  }
]

/**
 * VitePress Configuration
 *
 * Configures the Amelia documentation site with:
 * - Project-wide documentation
 * - Design system reference
 * - Ideas/brainstorming section
 * - Dark/light mode support
 */
export default defineConfig({
  title: 'Amelia',
  description: 'Documentation for the Amelia agentic coding orchestrator',

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
      { text: 'Guide', link: '/guide/usage' },
      { text: 'Architecture', link: '/architecture/overview' },
      { text: 'Ideas', link: '/ideas/' },
      { text: 'Roadmap', link: '/reference/roadmap' }
    ],

    // Sidebar navigation
    sidebar: {
      '/guide/': [
        {
          text: 'User Guide',
          items: [
            { text: 'Usage', link: '/guide/usage' },
            { text: 'Configuration', link: '/guide/configuration' },
            { text: 'Troubleshooting', link: '/guide/troubleshooting' }
          ]
        },
        {
          text: 'Example Artifacts',
          items: [
            { text: 'Overview', link: '/guide/artifacts/' },
            { text: 'Design Example', link: '/guide/artifacts/design-example' },
            { text: 'Plan Example', link: '/guide/artifacts/plan-example' },
            { text: 'Review Example', link: '/guide/artifacts/review-example' }
          ]
        }
      ],
      '/architecture/': [
        {
          text: 'Architecture',
          items: [
            { text: 'Overview', link: '/architecture/overview' },
            { text: 'Concepts', link: '/architecture/concepts' },
            { text: 'Data Model', link: '/architecture/data-model' }
          ]
        }
      ],
      '/design-system/': sharedSidebar,
      '/reference/': sharedSidebar,
      '/ideas/': sharedSidebar
    },

    // Social links
    socialLinks: [
      { icon: 'github', link: 'https://github.com/anderskev/amelia' }
    ],

    // Footer
    footer: {
      message: 'Built by hey-amelia bot. Released under the <a href="https://github.com/anderskev/amelia/blob/main/LICENSE">MPL-2.0 License</a>.',
      copyright: 'Copyright © 2024-2025 <a href="https://anderskev.com">@anderskev</a>'
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
    languageAlias: {
      'd2': 'yaml'
    }
  },

  // Head configuration
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/amelia/favicon.svg' }],
    ['link', { rel: 'stylesheet', href: '/amelia/fonts/fonts.css' }]
  ]
})
