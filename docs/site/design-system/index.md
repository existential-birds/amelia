# Getting Started

Welcome to the Amelia Design System documentation. This design system was built by [hey-amelia](https://github.com/apps/hey-amelia), an AI-powered GitHub bot. It provides a cohesive set of design tokens, themes, and guidelines for building consistent user interfaces and documentation across the Amelia platform.

## Overview

The Amelia Design System is built around two complementary themes:

- **Dark Mode (Primary)**: Deep forest greens (#0D1A12) with gold accents (#FFC857)
- **Light Mode (Secondary)**: Daytime theme with warm cream backgrounds (#FDF8F0) and professional blue accents (#2E6B9C)

The system includes:
- Design tokens (colors, typography, spacing)
- VitePress documentation theme
- Slidev presentation theme
- D2 diagram theme
- Mermaid diagram theme

## Installation

### Using Design Tokens

The design tokens are available as CSS files in the `design-system/tokens/` directory:

```bash
# Clone the repository
git clone https://github.com/existential-birds/amelia.git
cd amelia

# Import tokens in your CSS
@import 'design-system/tokens/colors.css';
@import 'design-system/tokens/typography.css';
```

### VitePress Theme

To use this theme in your VitePress documentation:

1. Copy `.vitepress/theme/style.css` to your VitePress project
2. The theme automatically includes Google Fonts imports
3. Colors adapt based on system preference (dark mode by default)

```bash
# In your VitePress project
cp docs/site/.vitepress/theme/style.css .vitepress/theme/
```

### Slidev Theme

For presentations using Slidev:

```yaml
# In your slides.md frontmatter
---
theme: ./design-system/themes/slidev
colorSchema: dark  # or 'light'
---
```

### D2 Diagrams

Copy the theme variables to your D2 diagrams:

```bash
# Use the theme file
cp design-system/themes/d2/amelia-dark.d2 your-diagram.d2
```

## Quick Start

### Using Color Tokens

```css
/* Dark mode colors (default) */
.my-component {
  background-color: var(--background);  /* #0D1A12 */
  color: var(--foreground);              /* #EFF8E2 */
  border-color: var(--primary);          /* #FFC857 */
}

/* Status colors for workflow states */
.status-running {
  color: var(--status-running);  /* Gold in dark, Blue in light */
}
```

### Using Typography

```css
/* Apply font families */
body {
  font-family: var(--font-body);  /* Source Sans 3 */
}

h1, h2, h3 {
  font-family: var(--font-heading);  /* Barlow Condensed */
}

.logo {
  font-family: var(--font-display);  /* Bebas Neue */
}

/* Type scale (Major Third - 1.25 ratio) */
.text {
  font-size: var(--font-size-base);  /* 16px */
  line-height: var(--line-height-base);  /* 1.6 */
}

h1 {
  font-size: var(--font-size-4xl);  /* 49px */
  line-height: var(--line-height-4xl);  /* 1.1 */
}
```

### Creating Diagrams

**D2 Example:**

```d2
# Import dark theme
vars: {
  background: "#0D1A12"
  surface: "#1F332E"
  text: "#EFF8E2"
  accent: "#FFC857"
  green: "#5B8A72"
  blue: "#5B9BD5"
}

user: {
  style: {
    fill: ${surface}
    stroke: ${accent}
    font-color: ${text}
  }
}

api: {
  style: {
    fill: ${background}
    stroke: ${green}
    font-color: ${text}
  }
}

user -> api: Request {
  style.stroke: ${blue}
}
```

### Building Presentations

**Slidev Example:**

```markdown
---
theme: ./design-system/themes/slidev
colorSchema: dark
---

# My Presentation

Using design tokens

---

## Features

- Professional dark theme
- Professional color palette
- Consistent typography
```

## Theme Colors Reference

### Dark Mode (Primary)

| Token | Value | Usage |
|-------|-------|-------|
| `--background` | #0D1A12 | Main background |
| `--foreground` | #EFF8E2 | Main text |
| `--primary` | #FFC857 | Gold accent |
| `--accent` | #5B9BD5 | Blue interactive elements |
| `--destructive` | #A33D2E | Error states |

### Light Mode (Secondary)

| Token | Value | Usage |
|-------|-------|-------|
| `--background` | #FDF8F0 | Main background |
| `--foreground` | #1A2F23 | Main text |
| `--primary` | #2E6B9C | Professional blue |
| `--accent` | #E8B84A | Gold highlights |
| `--destructive` | #8B3224 | Error states |

## Font Families

- **Display**: Bebas Neue (logos, brand elements)
- **Heading**: Barlow Condensed (section headings)
- **Body**: Source Sans 3 (body text, UI)
- **Mono**: IBM Plex Mono (code, technical content)

## Next Steps

- Explore the [Color System](/design-system/color-system) in detail
- Learn about [Typography](/design-system/typography) and type scale
- Create [Diagrams](/design-system/diagrams) with D2 and Mermaid
- Build [Presentations](/design-system/presentations) with Slidev
- Reference the complete [Token API](/design-system/tokens)
