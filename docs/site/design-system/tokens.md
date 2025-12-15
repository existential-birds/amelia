# Design Tokens API Reference

Complete API reference for all Amelia Design System tokens. These tokens are available in CSS custom properties and can be used across all design system themes (VitePress, Slidev, D2, Mermaid).

## Color Tokens

### Core Colors

#### Background & Foreground

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--background` | #0D1A12 (oklch 8% 0.02 150) | #FDF8F0 (oklch 96% 0.02 85) | Main page background |
| `--foreground` | #EFF8E2 (oklch 95% 0.02 120) | #1A2F23 (oklch 20% 0.04 150) | Main text color |

**Usage:**
```css
body {
  background-color: var(--background);
  color: var(--foreground);
}
```

#### Card & Surface

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--card` | #1F332E (oklch 18% 0.025 150) | #FFFDF9 (oklch 99% 0.01 85) | Elevated surface background |
| `--card-foreground` | #EFF8E2 (oklch 95% 0.02 120) | #1A2F23 (oklch 20% 0.04 150) | Text on card surfaces |
| `--popover` | #1F332E (oklch 18% 0.025 150) | #FFFDF9 (oklch 99% 0.01 85) | Popover/dropdown background |
| `--popover-foreground` | #EFF8E2 (oklch 95% 0.02 120) | #1A2F23 (oklch 20% 0.04 150) | Text in popovers |

**Usage:**
```css
.card {
  background-color: var(--card);
  color: var(--card-foreground);
  border-radius: 0.5rem;
  padding: 1rem;
}
```

#### Primary

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--primary` | #FFC857 (oklch 82% 0.16 85) | #2E6B9C (oklch 45% 0.12 240) | Primary brand color |
| `--primary-foreground` | #0D1A12 (oklch 8% 0.02 150) | #FFFDF9 (oklch 99% 0.01 85) | Text on primary color |

**Usage:**
```css
.button-primary {
  background-color: var(--primary);
  color: var(--primary-foreground);
}
```

#### Secondary

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--secondary` | #4A5C54 (oklch 35% 0.04 150) | #F5F1E8 (oklch 94% 0.015 85) | Secondary surfaces |
| `--secondary-foreground` | #EFF8E2 (oklch 95% 0.02 120) | #1A2F23 (oklch 20% 0.04 150) | Text on secondary |

**Usage:**
```css
.button-secondary {
  background-color: var(--secondary);
  color: var(--secondary-foreground);
}
```

#### Muted

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--muted` | #2B3D35 (oklch 25% 0.03 150) | #EBE5D8 (oklch 90% 0.02 85) | Subtle backgrounds |
| `--muted-foreground` | #88A896 (oklch 60% 0.05 150) | #5C7263 (oklch 45% 0.03 150) | Secondary text |

**Usage:**
```css
.muted-text {
  color: var(--muted-foreground);
}

.muted-background {
  background-color: var(--muted);
}
```

#### Accent

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--accent` | #5B9BD5 (oklch 65% 0.12 240) | #E8B84A (oklch 75% 0.14 85) | Interactive elements, links |
| `--accent-foreground` | #EFF8E2 (oklch 95% 0.02 120) | #1A2F23 (oklch 20% 0.04 150) | Text on accent color |

**Usage:**
```css
a {
  color: var(--accent);
}

a:hover {
  color: var(--primary);
}
```

#### Destructive

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--destructive` | #A33D2E (oklch 50% 0.2 25) | #8B3224 (oklch 45% 0.18 25) | Error, danger states |
| `--destructive-foreground` | #EFF8E2 (oklch 95% 0.02 120) | #FFFDF9 (oklch 99% 0.01 85) | Text on destructive |

**Usage:**
```css
.error-message {
  background-color: var(--destructive);
  color: var(--destructive-foreground);
}
```

### Borders & Inputs

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--border` | oklch(30% 0.02 150 / 0.2) | oklch(25% 0.03 150 / 0.15) | Default borders |
| `--input` | oklch(30% 0.02 150 / 0.3) | oklch(25% 0.03 150 / 0.2) | Input field borders |
| `--ring` | oklch(82% 0.16 85 / 0.5) | oklch(45% 0.12 240 / 0.5) | Focus ring color |

**Usage:**
```css
.input {
  border: 1px solid var(--input);
}

.input:focus {
  outline: none;
  box-shadow: 0 0 0 3px var(--ring);
}
```

### Status Colors

Workflow state indicators that adapt to both themes.

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--status-running` | #FFC857 (oklch 82% 0.16 85) | #2E6B9C (oklch 45% 0.12 240) | In progress state |
| `--status-completed` | #5B8A72 (oklch 50% 0.1 150) | #3D7552 (oklch 40% 0.1 150) | Success state |
| `--status-pending` | #4A5C54 (oklch 35% 0.04 150) | #B8AE9C (oklch 60% 0.02 85) | Queued state |
| `--status-blocked` | #A33D2E (oklch 50% 0.2 25) | #8B3224 (oklch 45% 0.18 25) | Blocked state |
| `--status-failed` | #A33D2E (oklch 50% 0.2 25) | #8B3224 (oklch 45% 0.18 25) | Error state |
| `--status-cancelled` | oklch(45% 0.03 250) | oklch(50% 0.04 250) | Cancelled state |

**Usage:**
```css
.status {
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.875rem;
}

.status--running {
  background-color: var(--status-running);
  color: var(--background);
}

.status--completed {
  background-color: var(--status-completed);
  color: var(--foreground);
}
```

### Sidebar Colors

Specialized tokens for sidebar navigation components.

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--sidebar` | oklch(12% 0.02 150) | oklch(94% 0.015 85) | Sidebar background |
| `--sidebar-foreground` | oklch(95% 0.02 120) | oklch(20% 0.04 150) | Sidebar text |
| `--sidebar-primary` | oklch(82% 0.16 85) | oklch(45% 0.12 240) | Sidebar primary accent |
| `--sidebar-primary-foreground` | oklch(8% 0.02 150) | oklch(99% 0.01 85) | Text on sidebar primary |
| `--sidebar-accent` | oklch(25% 0.03 150) | oklch(90% 0.02 85) | Sidebar accent background |
| `--sidebar-accent-foreground` | oklch(95% 0.02 120) | oklch(20% 0.04 150) | Text on sidebar accent |
| `--sidebar-border` | oklch(30% 0.02 150 / 0.15) | oklch(25% 0.03 150 / 0.1) | Sidebar borders |
| `--sidebar-ring` | hsl(217.2 91.2% 59.8%) | hsl(217.2 91.2% 59.8%) | Sidebar focus ring |

**Usage:**
```css
.sidebar {
  background-color: var(--sidebar);
  color: var(--sidebar-foreground);
  border-right: 1px solid var(--sidebar-border);
}

.sidebar-item--active {
  background-color: var(--sidebar-accent);
  color: var(--sidebar-accent-foreground);
}
```

### Chart Colors

Data visualization color palette.

#### Dark Mode Charts

| Token | Color | OKLCH | Description |
|-------|-------|-------|-------------|
| `--chart-1` | #FFC857 | oklch(82% 0.16 85) | Primary data series |
| `--chart-2` | #5B8A72 | oklch(50% 0.1 150) | Secondary data series |
| `--chart-3` | #5B9BD5 | oklch(65% 0.12 240) | Tertiary data series |
| `--chart-4` | #A33D2E | oklch(50% 0.2 25) | Warning/error data |
| `--chart-5` | #88A896 | oklch(60% 0.05 150) | Neutral data |

#### Light Mode Charts

| Token | Color | OKLCH | Description |
|-------|-------|-------|-------------|
| `--chart-1` | #2E6B9C | oklch(45% 0.12 240) | Primary data series |
| `--chart-2` | #3D7552 | oklch(40% 0.1 150) | Secondary data series |
| `--chart-3` | #E8B84A | oklch(75% 0.14 85) | Tertiary data series |
| `--chart-4` | #8B3224 | oklch(45% 0.18 25) | Warning/error data |
| `--chart-5` | #5C7263 | oklch(45% 0.03 150) | Neutral data |

**Usage:**
```css
.chart-bar:nth-child(1) { background-color: var(--chart-1); }
.chart-bar:nth-child(2) { background-color: var(--chart-2); }
.chart-bar:nth-child(3) { background-color: var(--chart-3); }
.chart-bar:nth-child(4) { background-color: var(--chart-4); }
.chart-bar:nth-child(5) { background-color: var(--chart-5); }
```

## Typography Tokens

### Font Families

| Token | Value | Google Fonts URL | Description |
|-------|-------|------------------|-------------|
| `--font-display` | "Bebas Neue", sans-serif | [Bebas Neue](https://fonts.google.com/specimen/Bebas+Neue) | Display font for logos, brand elements |
| `--font-heading` | "Barlow Condensed", sans-serif | [Barlow Condensed](https://fonts.google.com/specimen/Barlow+Condensed) | Heading font for titles |
| `--font-body` | "Source Sans 3", sans-serif | [Source Sans 3](https://fonts.google.com/specimen/Source+Sans+3) | Body font for content |
| `--font-mono` | "IBM Plex Mono", monospace | [IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono) | Monospace font for code |

**Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap');
```

**Usage:**
```css
.logo {
  font-family: var(--font-display);
}

h1, h2, h3 {
  font-family: var(--font-heading);
}

body {
  font-family: var(--font-body);
}

code, pre {
  font-family: var(--font-mono);
}
```

### Font Sizes

Based on Major Third (1.25) modular scale.

| Token | Rem | Pixels | Line Height | Description |
|-------|-----|--------|-------------|-------------|
| `--font-size-xs` | 0.75rem | 12px | 1.4 | Extra small text |
| `--font-size-sm` | 0.875rem | 14px | 1.5 | Small text |
| `--font-size-base` | 1rem | 16px | 1.6 | Base body text |
| `--font-size-lg` | 1.25rem | 20px | 1.5 | Large text |
| `--font-size-xl` | 1.563rem | 25px | 1.3 | h4 headings |
| `--font-size-2xl` | 1.953rem | 31px | 1.2 | h3 headings |
| `--font-size-3xl` | 2.441rem | 39px | 1.15 | h2 headings |
| `--font-size-4xl` | 3.052rem | 49px | 1.1 | h1 headings |
| `--font-size-5xl` | 3.815rem | 61px | 1.05 | Display text |

**Usage:**
```css
.caption {
  font-size: var(--font-size-xs);
  line-height: var(--line-height-xs);
}

body {
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
}

h1 {
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
}
```

### Line Heights

| Token | Value | Use Case |
|-------|-------|----------|
| `--line-height-xs` | 1.4 | Extra small text (12px) |
| `--line-height-sm` | 1.5 | Small text (14px) |
| `--line-height-base` | 1.6 | Body text (16px) |
| `--line-height-lg` | 1.5 | Large text (20px) |
| `--line-height-xl` | 1.3 | h4 (25px) |
| `--line-height-2xl` | 1.2 | h3 (31px) |
| `--line-height-3xl` | 1.15 | h2 (39px) |
| `--line-height-4xl` | 1.1 | h1 (49px) |
| `--line-height-5xl` | 1.05 | Display (61px) |

### Font Weights

#### Display Font (Bebas Neue)

| Token | Value | Description |
|-------|-------|-------------|
| `--font-weight-display-regular` | 400 | Only weight available |

#### Heading Font (Barlow Condensed)

| Token | Value | Description |
|-------|-------|-------------|
| `--font-weight-heading-medium` | 500 | Medium weight |
| `--font-weight-heading-semibold` | 600 | Semi-bold weight |
| `--font-weight-heading-bold` | 700 | Bold weight |

#### Body Font (Source Sans 3)

| Token | Value | Description |
|-------|-------|-------------|
| `--font-weight-body-regular` | 400 | Regular weight |
| `--font-weight-body-semibold` | 600 | Semi-bold weight |

#### Monospace Font (IBM Plex Mono)

| Token | Value | Description |
|-------|-------|-------------|
| `--font-weight-mono-regular` | 400 | Regular weight |
| `--font-weight-mono-medium` | 500 | Medium weight |

**Usage:**
```css
.display-text {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
}

h1 {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
}

strong {
  font-weight: var(--font-weight-body-semibold);
}
```

## Token Import

### CSS Import

Import all design tokens:

```css
/* Import color tokens */
@import 'design-system/tokens/colors.css';

/* Import typography tokens */
@import 'design-system/tokens/typography.css';
```

### JSON Schema

Color tokens are also available as JSON:

```json
{
  "dark": {
    "background": "#0D1A12",
    "foreground": "#EFF8E2",
    "primary": "#FFC857"
    // ... more tokens
  },
  "light": {
    "background": "#FDF8F0",
    "foreground": "#1A2F23",
    "primary": "#2E6B9C"
    // ... more tokens
  }
}
```

**Location**: [design-system/tokens/colors.json](https://github.com/anderskev/amelia/blob/main/design-system/tokens/colors.json)

## Theme Switching

### Automatic (System Preference)

Colors automatically adapt based on system color scheme preference:

```css
/* Dark mode (default) */
:root {
  --background: oklch(8% 0.02 150);
  --primary: oklch(82% 0.16 85);
}

/* Light mode (when system prefers light) */
@media (prefers-color-scheme: light) {
  :root {
    --background: oklch(96% 0.02 85);
    --primary: oklch(45% 0.12 240);
  }
}
```

### Manual Override

Force light mode with a class:

```css
.light {
  --background: oklch(96% 0.02 85);
  --primary: oklch(45% 0.12 240);
  /* ... all light mode tokens */
}
```

```javascript
// Toggle theme
document.documentElement.classList.toggle('light');

// Set based on preference
if (window.matchMedia('(prefers-color-scheme: light)').matches) {
  document.documentElement.classList.add('light');
}
```

## Usage Patterns

### Complete Component Example

```css
.card {
  /* Layout */
  padding: 1.5rem;
  border-radius: 0.5rem;

  /* Colors */
  background-color: var(--card);
  color: var(--card-foreground);
  border: 1px solid var(--border);

  /* Typography */
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
}

.card__title {
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  line-height: var(--line-height-2xl);
  font-weight: var(--font-weight-heading-bold);
  color: var(--foreground);
  margin-bottom: 0.5rem;
}

.card__description {
  color: var(--muted-foreground);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-sm);
}

.card__button {
  background-color: var(--primary);
  color: var(--primary-foreground);
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-body-semibold);
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
  border: none;
  cursor: pointer;
}

.card__button:hover {
  opacity: 0.9;
}

.card__button:focus {
  outline: none;
  box-shadow: 0 0 0 3px var(--ring);
}
```

### Responsive Typography

```css
/* Base (mobile) */
.hero-title {
  font-family: var(--font-display);
  font-size: var(--font-size-3xl);
  line-height: var(--line-height-3xl);
}

/* Tablet */
@media (min-width: 768px) {
  .hero-title {
    font-size: var(--font-size-4xl);
    line-height: var(--line-height-4xl);
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .hero-title {
    font-size: var(--font-size-5xl);
    line-height: var(--line-height-5xl);
  }
}
```

## Browser Compatibility

### OKLCH Color Space

OKLCH colors have excellent modern browser support:
- Chrome/Edge: 111+
- Firefox: 113+
- Safari: 15.4+

For older browsers, the tokens also provide fallback hex values.

### CSS Custom Properties

Supported in all modern browsers:
- Chrome/Edge: 49+
- Firefox: 31+
- Safari: 9.1+

## Related Resources

- [Color System Guide](/design-system/color-system)
- [Typography Guide](/design-system/typography)
- [Getting Started](/design-system/)
- [Diagrams](/design-system/diagrams)
- [Presentations](/design-system/presentations)
