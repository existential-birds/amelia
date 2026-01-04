# Amelia Design System

A unified design system for the Amelia AI orchestrator with dark-first theming optimized for extended developer sessions.

## Overview

The Amelia Design System provides:

- **Design Tokens** - OKLCH color palette, typography scale, and spacing
- **Diagram Themes** - Consistent styling for D2 and Mermaid diagrams
- **Presentation Theme** - Slidev theme for stakeholder presentations
- **Documentation Theme** - VitePress theme for the documentation site

## Quick Start

### Using Color Tokens

```css
/* Import the token file */
@import 'design-system/tokens/colors.css';

/* Use the CSS custom properties */
.my-element {
  background: var(--background);
  color: var(--foreground);
  border-color: var(--accent);
}
```

### Using Typography

```css
@import 'design-system/tokens/typography.css';

.display-heading {
  font-family: var(--font-display);
}

.body-text {
  font-family: var(--font-body);
}
```

### Using Diagram Themes

**D2:**

```d2
# Copy vars block from design-system/themes/d2/amelia-dark.d2
```

**Mermaid:**

```markdown
# Use frontmatter from design-system/themes/mermaid/amelia-dark.md
```

### Using the Slidev Theme

```yaml
# slides.md frontmatter
theme: ./design-system/themes/slidev
```

## Directory Structure

```
design-system/
├── tokens/
│   ├── colors.css          # CSS custom properties (dark + light)
│   ├── colors.json         # JSON for tooling
│   └── typography.css      # Font stacks, scale
├── themes/
│   ├── d2/                  # D2 diagram themes
│   ├── mermaid/             # Mermaid diagram themes
│   ├── slidev/              # Slidev presentation theme
│   └── vitepress/           # VitePress documentation theme
├── assets/
│   ├── logo/                # Logo SVG variants
│   └── fonts/               # Self-hosted WOFF2 fonts
└── examples/                # Usage examples
```

## Design Principles

1. **Dark-First** - Optimized for extended developer sessions
2. **Light Mode for Presentations** - Projector-friendly alternative
3. **OKLCH Colors** - Perceptually uniform color space
4. **Accessible** - Designed for WCAG 2.1 AA contrast on primary text/background pairs (`--foreground` on `--background`, `--muted-foreground` on `--muted`)

## Color Palette

| Role | Dark Mode | Light Mode |
|------|-----------|------------|
| Background | Deep Forest #0D1A12 | Warm Cream #FDF8F0 |
| Surface | Forest Green #1F332E | Mist #E8F0E5 |
| Accent | Gold #FFC857 | Forest Green #2D5A3D |
| Foreground | Pale Sage #EFF8E2 | Deep Forest #0D1A12 |

## Typography

| Role | Font | Usage |
|------|------|-------|
| Display | Bebas Neue | Large titles, hero text |
| Heading | Barlow Condensed | Section headings, navigation |
| Body | Source Sans 3 | Body copy, UI text |
| Code | IBM Plex Mono | Code blocks, technical content |

## Dashboard Integration

**Decision: Token Duplication (Option A)**

The dashboard (`dashboard/src/styles/globals.css`) maintains its own copy of the design tokens, while `design-system/tokens/` provides portable copies for external use.

**Rationale:**
- Dashboard already has working token implementation
- Avoids build process complexity for token synchronization
- Design system tokens are standalone and portable to other projects
- Dashboard can adopt synced tokens in the future if needed (Option B)

If you need to update tokens:
1. Update `design-system/tokens/colors.css` (canonical source)
2. Manually sync relevant changes to `dashboard/src/styles/globals.css`

## License

Elastic License 2.0 - See LICENSE file for details.
