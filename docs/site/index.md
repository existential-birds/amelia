---
layout: home

hero:
  name: "Amelia Design System"
  text: "Aviation-Inspired Design"
  tagline: A unified design system for the Amelia AI orchestrator, featuring dark-first theming optimized for extended developer sessions.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/anderskev/amelia
  image:
    src: /logo/amelia-gold.svg
    alt: Amelia Logo

features:
  - icon: 🎨
    title: Design Tokens
    details: OKLCH color palette with dark and light modes, modular typography scale, and comprehensive spacing system.
    link: /guide/color-system
  - icon: 📊
    title: Diagram Themes
    details: Consistent styling for D2 and Mermaid diagrams with aviation-inspired aesthetics.
    link: /guide/diagrams
  - icon: 📽️
    title: Presentation Theme
    details: Slidev theme for stakeholder presentations with projector-optimized light mode.
    link: /guide/presentations
  - icon: 📚
    title: Documentation
    details: VitePress theme for beautiful, accessible documentation with aviation cockpit aesthetics.
  - icon: 🌙
    title: Dark-First Design
    details: Optimized for extended developer sessions with reduced eye strain and professional aesthetics.
  - icon: ♿
    title: Accessible
    details: WCAG 2.1 AA compliant contrast ratios ensuring readability for all users.
---

## Why Amelia Design System?

The Amelia Design System provides a cohesive visual language across all Amelia project artifacts—from documentation and diagrams to presentations and dashboards. Built on design tokens and aviation-inspired aesthetics, it ensures consistency while maintaining flexibility.

### Key Principles

1. **Dark-First** - Optimized for extended developer sessions with reduced eye strain
2. **Light Mode for Presentations** - Projector-friendly alternative for stakeholder meetings
3. **Aviation-Inspired** - Flight deck instrumentation aesthetic with cockpit green and gold accents
4. **OKLCH Colors** - Perceptually uniform color space for better color transitions
5. **Accessible** - WCAG 2.1 AA compliant contrast ratios

### Quick Start

```bash
# Clone the repository
git clone https://github.com/anderskev/amelia.git

# Navigate to design system
cd amelia/design-system
```

Import color tokens in your CSS:

```css
@import 'design-system/tokens/colors.css';

.my-element {
  background: var(--background);
  color: var(--foreground);
  border-color: var(--accent);
}
```

Import typography tokens:

```css
@import 'design-system/tokens/typography.css';

h1 {
  font-family: var(--font-heading);
  font-size: var(--font-size-4xl);
}
```

### Ready to dive in?

[Get Started](/guide/getting-started) with the Amelia Design System and bring aviation-inspired design to your project.
