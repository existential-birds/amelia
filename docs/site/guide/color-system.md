# Color System

The Amelia color system is built on two complementary themes that adapt to user preferences. All colors use the OKLCH color space for perceptual uniformity and better color interpolation.

## Design Philosophy

The Amelia Design System features dual themes designed for professional environments:

- **Dark Mode (Primary)**: Deep forest green backgrounds with gold accents
- **Light Mode (Secondary)**: Daytime professional theme with warm cream backgrounds and blue accents

## Core Color Tokens

### Dark Mode (Default)

The default dark mode uses deep forest greens with gold accents:

<div class="color-swatch-grid">

| Token | Hex | OKLCH | Usage |
|-------|-----|-------|-------|
| `--background` | #0D1A12 | oklch(8% 0.02 150) | Main background |
| `--foreground` | #EFF8E2 | oklch(95% 0.02 120) | Main text color |
| `--card` | #1F332E | oklch(18% 0.025 150) | Elevated surfaces |
| `--primary` | #FFC857 | oklch(82% 0.16 85) | Gold - primary actions |
| `--secondary` | #4A5C54 | oklch(35% 0.04 150) | Muted panels |
| `--muted` | #2B3D35 | oklch(25% 0.03 150) | Subtle backgrounds |
| `--muted-foreground` | #88A896 | oklch(60% 0.05 150) | Secondary text |
| `--accent` | #5B9BD5 | oklch(65% 0.12 240) | Blue - links & interactive |
| `--destructive` | #A33D2E | oklch(50% 0.2 25) | Error states |

</div>

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

### Light Mode

The light mode provides a warm, professional aesthetic for daytime use:

<div class="color-swatch-grid">

| Token | Hex | OKLCH | Usage |
|-------|-----|-------|-------|
| `--background` | #FDF8F0 | oklch(96% 0.02 85) | Main background |
| `--foreground` | #1A2F23 | oklch(20% 0.04 150) | Main text color |
| `--card` | #FFFDF9 | oklch(99% 0.01 85) | Elevated surfaces |
| `--primary` | #2E6B9C | oklch(45% 0.12 240) | Professional blue |
| `--secondary` | #F5F1E8 | oklch(94% 0.015 85) | Light panels |
| `--muted` | #EBE5D8 | oklch(90% 0.02 85) | Subtle backgrounds |
| `--muted-foreground` | #5C7263 | oklch(45% 0.03 150) | Secondary text |
| `--accent` | #E8B84A | oklch(75% 0.14 85) | Gold highlights |
| `--destructive` | #8B3224 | oklch(45% 0.18 25) | Error states |

</div>

## Status Colors

Workflow state colors that adapt to both themes:

### Dark Mode Status

| Token | Hex | OKLCH | Usage |
|-------|-----|-------|-------|
| `--status-running` | #FFC857 | oklch(82% 0.16 85) | In progress |
| `--status-completed` | #5B8A72 | oklch(50% 0.1 150) | Successfully done |
| `--status-pending` | #4A5C54 | oklch(35% 0.04 150) | Queued/waiting |
| `--status-blocked` | #A33D2E | oklch(50% 0.2 25) | Blocked/awaiting |
| `--status-failed` | #A33D2E | oklch(50% 0.2 25) | Error state |
| `--status-cancelled` | #5B6B7A | oklch(45% 0.03 250) | Cancelled |

### Light Mode Status

| Token | Hex | OKLCH | Usage |
|-------|-----|-------|-------|
| `--status-running` | #2E6B9C | oklch(45% 0.12 240) | In progress |
| `--status-completed` | #3D7552 | oklch(40% 0.1 150) | Successfully done |
| `--status-pending` | #B8AE9C | oklch(60% 0.02 85) | Queued/waiting |
| `--status-blocked` | #8B3224 | oklch(45% 0.18 25) | Blocked/awaiting |
| `--status-failed` | #8B3224 | oklch(45% 0.18 25) | Error state |
| `--status-cancelled` | #6B7D8C | oklch(50% 0.04 250) | Cancelled |

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

### Dark Mode Charts

| Token | Color | Usage |
|-------|-------|-------|
| `--chart-1` | #FFC857 (Gold) | Primary data series |
| `--chart-2` | #5B8A72 (Green) | Secondary data series |
| `--chart-3` | #5B9BD5 (Blue) | Tertiary data series |
| `--chart-4` | #A33D2E (Red) | Warning/error data |
| `--chart-5` | #88A896 (Gray) | Neutral data |

### Light Mode Charts

| Token | Color | Usage |
|-------|-------|-------|
| `--chart-1` | #2E6B9C (Blue) | Primary data series |
| `--chart-2` | #3D7552 (Green) | Secondary data series |
| `--chart-3` | #E8B84A (Gold) | Tertiary data series |
| `--chart-4` | #8B3224 (Red) | Warning/error data |
| `--chart-5` | #5C7263 (Gray) | Neutral data |

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

All Amelia colors are defined in OKLCH (Oklab Lightness Chroma Hue) for:

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

- Learn about [Typography](/guide/typography) tokens
- Create themed [Diagrams](/guide/diagrams)
- Build [Presentations](/guide/presentations) with consistent colors
- Reference the complete [Token API](/api/tokens)
