import { defineConfig } from 'vitepress'

const siteUrl = 'https://existential-birds.github.io'
const basePath = '/amelia/'
const fullUrl = `${siteUrl}${basePath}`

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
  titleTemplate: ':title | Amelia – Open-Source Agent Orchestrator',
  description: 'Amelia is an open-source agent orchestration framework. Plan, build, review, and ship code with multi-agent AI workflows.',

  lang: 'en-US',
  cleanUrls: true,
  lastUpdated: true,

  // Base path for deployment
  base: basePath,

  // Dark mode as default
  appearance: 'dark',

  // Sitemap generation
  sitemap: {
    hostname: fullUrl
  },

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

  // Head configuration - static global tags
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/amelia/favicon.svg' }],
    ['link', { rel: 'stylesheet', href: '/amelia/fonts/fonts.css' }],
    // Open Graph - static
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Amelia' }],
    // Twitter Card - static
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
  ],

  // Dynamic per-page meta tags
  transformPageData(pageData, ctx) {
    const canonicalUrl = `${fullUrl}${pageData.relativePath.replace(/index\.md$/, '').replace(/\.md$/, '')}`
    const pageTitle = pageData.frontmatter.title ?? pageData.title
    const title = pageTitle ? `${pageTitle} | Amelia` : ctx.siteConfig.site.title
    const description = pageData.frontmatter.description ?? ctx.siteConfig.site.description

    pageData.frontmatter.head ??= []
    pageData.frontmatter.head.push(
      // Canonical URL
      ['link', { rel: 'canonical', href: canonicalUrl }],
      // Open Graph - per-page
      ['meta', { property: 'og:title', content: title }],
      ['meta', { property: 'og:description', content: description }],
      ['meta', { property: 'og:url', content: canonicalUrl }],
      // Twitter Card - per-page
      ['meta', { name: 'twitter:title', content: title }],
      ['meta', { name: 'twitter:description', content: description }],
    )

    // JSON-LD: SoftwareApplication on homepage
    if (pageData.relativePath === 'index.md') {
      pageData.frontmatter.head.push([
        'script',
        { type: 'application/ld+json' },
        JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'SoftwareApplication',
          name: 'Amelia',
          description: 'Open-source agent orchestration framework for multi-agent AI coding workflows.',
          applicationCategory: 'DeveloperApplication',
          operatingSystem: 'Linux, macOS',
          offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
          author: {
            '@type': 'Organization',
            name: 'existential-birds',
            url: 'https://github.com/existential-birds'
          },
          codeRepository: 'https://github.com/existential-birds/amelia',
          license: 'https://opensource.org/licenses/Apache-2.0'
        })
      ])
    }

    // JSON-LD: Article on documentation pages
    if (pageData.relativePath !== 'index.md' && pageData.frontmatter.layout !== 'home') {
      pageData.frontmatter.head.push([
        'script',
        { type: 'application/ld+json' },
        JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'TechArticle',
          headline: pageTitle,
          description,
          url: canonicalUrl,
          ...(pageData.lastUpdated ? { dateModified: new Date(pageData.lastUpdated).toISOString() } : {}),
          author: {
            '@type': 'Organization',
            name: 'existential-birds',
            url: 'https://github.com/existential-birds'
          }
        })
      ])
    }
  }
})
