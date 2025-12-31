/**
 * Shiki Theme Configuration for Slidev
 *
 * Defines syntax highlighting themes for code blocks in presentations.
 * Uses Amelia design system colors for dark mode and min-light for light mode.
 */

import { defineShikiSetup } from '@slidev/types'

export default defineShikiSetup(() => {
  return {
    themes: {
      // Dark theme: Amelia design system colors
      dark: {
        name: 'amelia-dark',
        type: 'dark',
        colors: {
          // Editor colors
          'editor.background': '#0D1A12',
          'editor.foreground': '#EFF8E2',

          // UI elements
          'editorLineNumber.foreground': '#88A896',
          'editorLineNumber.activeForeground': '#5B8A72',
          'editorCursor.foreground': '#FFC857',

          // Selection and highlights
          'editor.selectionBackground': '#5B8A7233',
          'editor.lineHighlightBackground': '#1A2F2011',
          'editor.findMatchBackground': '#FFC85733',
          'editor.findMatchHighlightBackground': '#FFC85722',
        },
        tokenColors: [
          // Keywords (if, const, let, function, class, etc.)
          {
            scope: ['keyword', 'storage.type', 'storage.modifier'],
            settings: {
              foreground: '#FFC857', // Amelia accent (warm yellow)
              fontStyle: 'bold'
            }
          },

          // Strings
          {
            scope: ['string', 'string.quoted'],
            settings: {
              foreground: '#5B8A72' // Amelia primary (green)
            }
          },

          // Functions and methods
          {
            scope: [
              'entity.name.function',
              'support.function',
              'meta.function-call'
            ],
            settings: {
              foreground: '#5B9BD5' // Blue for functions
            }
          },

          // Comments
          {
            scope: ['comment', 'punctuation.definition.comment'],
            settings: {
              foreground: '#88A896', // Muted green
              fontStyle: 'italic'
            }
          },

          // Variables and parameters
          {
            scope: [
              'variable',
              'variable.parameter',
              'meta.definition.variable'
            ],
            settings: {
              foreground: '#EFF8E2' // Amelia light foreground
            }
          },

          // Classes and types
          {
            scope: [
              'entity.name.type',
              'entity.name.class',
              'support.type',
              'support.class'
            ],
            settings: {
              foreground: '#FFC857', // Accent color for types
              fontStyle: 'bold'
            }
          },

          // Constants and numbers
          {
            scope: [
              'constant',
              'constant.numeric',
              'constant.language',
              'constant.character'
            ],
            settings: {
              foreground: '#FF9A76' // Warm orange for constants
            }
          },

          // Operators
          {
            scope: ['keyword.operator', 'punctuation'],
            settings: {
              foreground: '#C4D5BC' // Light muted green
            }
          },

          // Tags (HTML/JSX)
          {
            scope: [
              'entity.name.tag',
              'meta.tag',
              'punctuation.definition.tag'
            ],
            settings: {
              foreground: '#5B8A72' // Primary green
            }
          },

          // Attributes
          {
            scope: ['entity.other.attribute-name'],
            settings: {
              foreground: '#FFC857', // Accent yellow
              fontStyle: 'italic'
            }
          },

          // Imports and requires
          {
            scope: [
              'keyword.control.import',
              'keyword.control.from',
              'keyword.control.export'
            ],
            settings: {
              foreground: '#FFC857',
              fontStyle: 'bold'
            }
          },

          // Regular expressions
          {
            scope: ['string.regexp'],
            settings: {
              foreground: '#FF9A76' // Orange
            }
          },

          // Invalid/deprecated
          {
            scope: ['invalid', 'invalid.illegal'],
            settings: {
              foreground: '#FF6B6B' // Red for errors
            }
          },

          // Markdown headings
          {
            scope: ['markup.heading', 'entity.name.section'],
            settings: {
              foreground: '#5B8A72',
              fontStyle: 'bold'
            }
          },

          // Markdown bold
          {
            scope: ['markup.bold'],
            settings: {
              foreground: '#FFC857',
              fontStyle: 'bold'
            }
          },

          // Markdown italic
          {
            scope: ['markup.italic'],
            settings: {
              foreground: '#EFF8E2',
              fontStyle: 'italic'
            }
          },

          // Markdown code
          {
            scope: ['markup.inline.raw', 'markup.fenced_code'],
            settings: {
              foreground: '#88A896'
            }
          },

          // Markdown links
          {
            scope: ['markup.underline.link', 'string.other.link'],
            settings: {
              foreground: '#5B9BD5',
              fontStyle: 'underline'
            }
          },
        ]
      },

      // Light theme: Use Shiki's built-in min-light theme
      light: 'min-light',
    }
  }
})
