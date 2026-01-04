import { defineConfig } from 'vitepress'

/**
 * Shared sidebar configuration for Ideas, Reference, and Design System sections.
 * Used across multiple URL prefixes to maintain consistent navigation.
 */
const sharedSidebar = [
  {
    text: 'Ideas & Explorations',
    items: [
      { text: 'Overview', link: '/ideas/' }
    ]
  },
  {
    text: 'Research',
    items: [
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
      { text: 'Typography', link: '/design-system/typography' },
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
      { icon: 'github', link: 'https://github.com/existential-birds/amelia' }
    ],

    // Footer
    footer: {
      message: 'Built by hey-amelia bot. Released under the <a href="https://github.com/existential-birds/amelia/blob/main/LICENSE">Elastic License 2.0</a>.',
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
