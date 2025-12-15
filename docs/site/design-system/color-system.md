# Color System

The Amelia color system is built on two complementary themes that adapt to user preferences. All colors use the OKLCH color space for perceptual uniformity and better color interpolation.

## Design Philosophy

The Amelia Design System features dual themes designed for professional environments:

- **Dark Mode (Primary)**: Deep forest green backgrounds with gold accents
- **Light Mode (Secondary)**: Daytime professional theme with warm cream backgrounds and blue accents

## Core Color Tokens

<ColorComparison
  title="Core Colors"
  :colors="[
    { name: '--background', dark: { hex: '#0D1A12', oklch: 'oklch(8% 0.02 150)' }, light: { hex: '#FDF8F0', oklch: 'oklch(96% 0.02 85)' }, usage: 'Main background' },
    { name: '--foreground', dark: { hex: '#EFF8E2', oklch: 'oklch(95% 0.02 120)' }, light: { hex: '#1A2F23', oklch: 'oklch(20% 0.04 150)' }, usage: 'Main text color' },
    { name: '--card', dark: { hex: '#1F332E', oklch: 'oklch(18% 0.025 150)' }, light: { hex: '#FFFDF9', oklch: 'oklch(99% 0.01 85)' }, usage: 'Elevated surfaces' },
    { name: '--primary', dark: { hex: '#FFC857', oklch: 'oklch(82% 0.16 85)' }, light: { hex: '#2E6B9C', oklch: 'oklch(45% 0.12 240)' }, usage: 'Primary actions (Gold/Blue)' },
    { name: '--secondary', dark: { hex: '#4A5C54', oklch: 'oklch(35% 0.04 150)' }, light: { hex: '#F5F1E8', oklch: 'oklch(94% 0.015 85)' }, usage: 'Muted panels' },
    { name: '--muted', dark: { hex: '#2B3D35', oklch: 'oklch(25% 0.03 150)' }, light: { hex: '#EBE5D8', oklch: 'oklch(90% 0.02 85)' }, usage: 'Subtle backgrounds' },
    { name: '--muted-foreground', dark: { hex: '#88A896', oklch: 'oklch(60% 0.05 150)' }, light: { hex: '#5C7263', oklch: 'oklch(45% 0.03 150)' }, usage: 'Secondary text' },
    { name: '--accent', dark: { hex: '#5B9BD5', oklch: 'oklch(65% 0.12 240)' }, light: { hex: '#E8B84A', oklch: 'oklch(75% 0.14 85)' }, usage: 'Links & interactive (Blue/Gold)' },
    { name: '--destructive', dark: { hex: '#A33D2E', oklch: 'oklch(50% 0.2 25)' }, light: { hex: '#8B3224', oklch: 'oklch(45% 0.18 25)' }, usage: 'Error states' }
  ]"
/>

## Heading Colors

Coral/Terracotta headings add visual excitement while complementing the forest green palette:

<ColorComparison
  title="Heading Colors"
  :colors="[
    { name: '--vp-c-heading-1', dark: { hex: '#E8846E', oklch: 'oklch(72% 0.14 35)' }, light: { hex: '#A85035', oklch: 'oklch(50% 0.15 30)' }, usage: 'H1, H2 headings' },
    { name: '--vp-c-heading-2', dark: { hex: '#D9846E', oklch: 'oklch(68% 0.12 40)' }, light: { hex: '#B8634A', oklch: 'oklch(55% 0.13 35)' }, usage: 'H3-H6 headings' }
  ]"
/>

**Example Usage:**

```css
.vp-doc h1,
.vp-doc h2 {
  color: var(--vp-c-heading-1);
}

.vp-doc h3,
.vp-doc h4,
.vp-doc h5,
.vp-doc h6 {
  color: var(--vp-c-heading-2);
}
```

**Example Usage:**

```css
.dashboard {
  background-color: var(--background);
  color: var(--foreground);
}

.card {
  background-color: var(--card);
  border: 1px solid var(--border);
}

.primary-button {
  background-color: var(--primary);
  color: var(--primary-foreground);
}

.link {
  color: var(--accent);
}
```

## Status Colors

Workflow state colors that adapt to both themes:

<ColorComparison
  title="Status Colors"
  :colors="[
    { name: '--status-running', dark: { hex: '#FFC857', oklch: 'oklch(82% 0.16 85)' }, light: { hex: '#2E6B9C', oklch: 'oklch(45% 0.12 240)' }, usage: 'In progress' },
    { name: '--status-completed', dark: { hex: '#5B8A72', oklch: 'oklch(50% 0.1 150)' }, light: { hex: '#3D7552', oklch: 'oklch(40% 0.1 150)' }, usage: 'Successfully done' },
    { name: '--status-pending', dark: { hex: '#4A5C54', oklch: 'oklch(35% 0.04 150)' }, light: { hex: '#B8AE9C', oklch: 'oklch(60% 0.02 85)' }, usage: 'Queued/waiting' },
    { name: '--status-blocked', dark: { hex: '#A33D2E', oklch: 'oklch(50% 0.2 25)' }, light: { hex: '#8B3224', oklch: 'oklch(45% 0.18 25)' }, usage: 'Blocked/awaiting' },
    { name: '--status-failed', dark: { hex: '#A33D2E', oklch: 'oklch(50% 0.2 25)' }, light: { hex: '#8B3224', oklch: 'oklch(45% 0.18 25)' }, usage: 'Error state' },
    { name: '--status-cancelled', dark: { hex: '#5B6B7A', oklch: 'oklch(45% 0.03 250)' }, light: { hex: '#6B7D8C', oklch: 'oklch(50% 0.04 250)' }, usage: 'Cancelled' }
  ]"
/>

**Example Usage:**

```css
.workflow-status {
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
}

.workflow-status--running {
  background-color: var(--status-running);
  color: var(--background);
}

.workflow-status--completed {
  background-color: var(--status-completed);
  color: var(--foreground);
}

.workflow-status--failed {
  background-color: var(--status-failed);
  color: var(--foreground);
}
```

## Chart Colors

Data visualization palette for both themes:

<ColorComparison
  title="Chart Colors"
  :colors="[
    { name: '--chart-1', dark: { hex: '#FFC857' }, light: { hex: '#2E6B9C' }, usage: 'Primary data series' },
    { name: '--chart-2', dark: { hex: '#5B8A72' }, light: { hex: '#3D7552' }, usage: 'Secondary data series' },
    { name: '--chart-3', dark: { hex: '#5B9BD5' }, light: { hex: '#E8B84A' }, usage: 'Tertiary data series' },
    { name: '--chart-4', dark: { hex: '#A33D2E' }, light: { hex: '#8B3224' }, usage: 'Warning/error data' },
    { name: '--chart-5', dark: { hex: '#88A896' }, light: { hex: '#5C7263' }, usage: 'Neutral data' }
  ]"
/>

**Example Usage:**

```css
.chart-bar:nth-child(1) { background-color: var(--chart-1); }
.chart-bar:nth-child(2) { background-color: var(--chart-2); }
.chart-bar:nth-child(3) { background-color: var(--chart-3); }
.chart-bar:nth-child(4) { background-color: var(--chart-4); }
.chart-bar:nth-child(5) { background-color: var(--chart-5); }
```

## Sidebar Colors

Specialized colors for sidebar navigation:

```css
.sidebar {
  background-color: var(--sidebar);
  color: var(--sidebar-foreground);
  border-right: 1px solid var(--sidebar-border);
}

.sidebar-link--active {
  background-color: var(--sidebar-accent);
  color: var(--sidebar-accent-foreground);
}

.sidebar-link--primary {
  color: var(--sidebar-primary);
}
```

## Usage Guidelines

### Accessibility

All color combinations meet WCAG AA contrast requirements:

- Text colors on backgrounds: Minimum 4.5:1 ratio
- Large text (18px+): Minimum 3:1 ratio
- Interactive elements: Clear focus states with `--ring` color

### Color Modes

Colors automatically adapt based on user preferences:

```css
/* System preference detection (automatic) */
@media (prefers-color-scheme: light) {
  :root {
    /* Light mode colors applied */
  }
}

/* Manual override with class */
.light {
  /* Force light mode */
}
```

### Semantic Usage

Use semantic tokens instead of raw colors:

::: tip Good Practice
```css
.error-message {
  color: var(--destructive);
  background-color: var(--destructive-soft);
}
```
:::

::: danger Avoid
```css
.error-message {
  color: #A33D2E;  /* Don't use raw hex values */
  background-color: rgba(163, 61, 46, 0.16);
}
```
:::

### Alpha Transparency

For overlays and borders, use tokens with built-in alpha:

```css
.overlay {
  background-color: var(--border);  /* Pre-defined alpha */
}

.input {
  border: 1px solid var(--input);  /* Pre-defined alpha */
}

.focus-ring {
  box-shadow: 0 0 0 3px var(--ring);  /* Pre-defined alpha */
}
```

## Color Theory

### OKLCH Color Space

All colors are defined in OKLCH (Oklab Lightness Chroma Hue) for:

- **Perceptual uniformity**: Equal numerical changes = equal perceived changes
- **Predictable lightness**: Easier to create accessible color scales
- **Better interpolation**: Smooth gradients and animations
- **Wide gamut support**: Future-proof for modern displays

```css
/* OKLCH format: oklch(L% C H / alpha) */
--primary: oklch(82% 0.16 85);
/* L = 82% lightness, C = 0.16 chroma, H = 85° hue */
```

### Color Relationships

The color system maintains these relationships across themes:

1. **Primary**: Most prominent accent (gold/blue)
2. **Accent**: Interactive elements (blue/gold)
3. **Muted**: Reduced emphasis, backgrounds
4. **Destructive**: Errors and warnings (consistent red)

## Integration Examples

### Import Tokens

```css
/* Import all color tokens */
@import 'design-system/tokens/colors.css';

/* Use in components */
.component {
  background: var(--card);
  border: 1px solid var(--border);
}
```

### Theme Switching

```javascript
// Toggle theme programmatically
function toggleTheme() {
  document.documentElement.classList.toggle('light');
}

// Respect system preference
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
if (!prefersDark.matches) {
  document.documentElement.classList.add('light');
}
```

## Next Steps

- Learn about [Typography](/design-system/typography) tokens
- Create themed [Diagrams](/design-system/diagrams)
- Build [Presentations](/design-system/presentations) with consistent colors
- Reference the complete [Token API](/design-system/tokens)
