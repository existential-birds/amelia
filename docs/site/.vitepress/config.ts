import { defineConfig } from 'vitepress'

/**
 * Guide sidebar - combines user documentation and architecture.
 * Used for both /guide/ and /architecture/ URL prefixes.
 */
const guideSidebar = [
  {
    text: 'User Guide',
    items: [
      { text: 'Usage', link: '/guide/usage' },
      { text: 'Configuration', link: '/guide/configuration' },
      { text: 'Troubleshooting', link: '/guide/troubleshooting' }
    ]
  },
  {
    text: 'Architecture',
    items: [
      { text: 'Overview', link: '/architecture/overview' },
      { text: 'Concepts', link: '/architecture/concepts' },
      { text: 'Data Model', link: '/architecture/data-model' },
      { text: 'Inspiration', link: '/architecture/inspiration' }
    ]
  }
]

/**
 * About sidebar - reference content.
 * Used for /reference/ URL prefix.
 */
const aboutSidebar = [
  {
    text: 'Reference',
    items: [
      { text: 'Roadmap', link: '/reference/roadmap' }
    ]
  }
]

/**
 * VitePress Configuration
 *
 * Configures the Amelia documentation site with:
 * - Project-wide documentation
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
      { text: 'About', link: '/reference/roadmap' }
    ],

    // Sidebar navigation
    sidebar: {
      '/guide/': guideSidebar,
      '/architecture/': guideSidebar,
      '/reference/': aboutSidebar
    },

    // Social links
    socialLinks: [
      { icon: 'github', link: 'https://github.com/existential-birds/amelia' }
    ],

    // Footer
    footer: {
      message: 'Built by hey-amelia bot. Released under the <a href="https://github.com/existential-birds/amelia/blob/main/LICENSE">Apache License 2.0</a>.',
      copyright: 'Copyright © 2024-2025 <a href="https://github.com/existential-birds">@existential-birds</a>'
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
