# Typography

The Amelia typography system ensures consistent and accessible text across all platforms. It features carefully selected Google Fonts and a modular type scale based on the Major Third ratio (1.25).

## Font Families

The design system uses four specialized font families, each serving a specific purpose:

### Display Font - Bebas Neue

**Token**: `--font-display`
**Google Fonts**: [Bebas Neue](https://fonts.google.com/specimen/Bebas+Neue)
**Weight**: 400 (Regular)

Used for the Amelia logo, brand elements, and large impact text. Features a bold, condensed sans-serif design with uppercase styling.

```css
.logo {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
```

**Example:**
<div style="font-family: 'Bebas Neue', sans-serif; font-size: 48px; letter-spacing: 0.02em;">
DESIGN SYSTEM
</div>

### Heading Font - Barlow Condensed

**Token**: `--font-heading`
**Google Fonts**: [Barlow Condensed](https://fonts.google.com/specimen/Barlow+Condensed)
**Weights**: 500 (Medium), 600 (Semi-Bold), 700 (Bold)

Used for section headings, titles, and navigation. A modern, condensed sans-serif that maintains readability while saving space.

```css
h1, h2, h3 {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);
}

h4, h5 {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-semibold);
}
```

**Example:**
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 36px; font-weight: 700;">
Section Heading
</div>

### Body Font - Source Sans 3

**Token**: `--font-body`
**Google Fonts**: [Source Sans 3](https://fonts.google.com/specimen/Source+Sans+3)
**Weights**: 400 (Regular), 600 (Semi-Bold)

Used for all body text, UI elements, and general content. Highly readable with excellent screen rendering.

```css
body {
  font-family: var(--font-body);
  font-weight: var(--font-weight-body-regular);
}

strong, .semibold {
  font-weight: var(--font-weight-body-semibold);
}
```

**Example:**
<div style="font-family: 'Source Sans 3', sans-serif; font-size: 16px;">
The quick brown fox jumps over the lazy dog. This is body text with excellent readability and clean rendering on screens.
</div>

### Monospace Font - IBM Plex Mono

**Token**: `--font-mono`
**Google Fonts**: [IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono)
**Weights**: 400 (Regular), 500 (Medium)

Used for code blocks, technical content, and terminal output. Features clear character distinction and comfortable reading for code.

```css
code, pre {
  font-family: var(--font-mono);
  font-weight: var(--font-weight-mono-regular);
}

.code-emphasis {
  font-weight: var(--font-weight-mono-medium);
}
```

**Example:**
<div style="font-family: 'IBM Plex Mono', monospace; font-size: 14px;">
const greeting = "Hello, World!";
</div>

## Type Scale

The Amelia type scale uses a **Major Third (1.25)** ratio, creating harmonious size relationships across all text elements.

### Scale Reference

| Token | Size | Line Height | Rem | Pixels | Usage |
|-------|------|-------------|-----|--------|-------|
| `--font-size-xs` | 0.75rem | 1.4 | 0.75 | 12px | Small labels, captions |
| `--font-size-sm` | 0.875rem | 1.5 | 0.875 | 14px | Secondary text, metadata |
| `--font-size-base` | 1rem | 1.6 | 1.0 | 16px | Body text, paragraphs |
| `--font-size-lg` | 1.25rem | 1.5 | 1.25 | 20px | Large body text, h5 |
| `--font-size-xl` | 1.563rem | 1.3 | 1.563 | 25px | h4 headings |
| `--font-size-2xl` | 1.953rem | 1.2 | 1.953 | 31px | h3 headings |
| `--font-size-3xl` | 2.441rem | 1.15 | 2.441 | 39px | h2 headings |
| `--font-size-4xl` | 3.052rem | 1.1 | 3.052 | 49px | h1 headings |
| `--font-size-5xl` | 3.815rem | 1.05 | 3.815 | 61px | Display text, hero titles |

### Visual Scale Example

<div style="margin: 2rem 0;">
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 3.815rem; line-height: 1.05; margin-bottom: 0.5rem;">Display 5XL</div>
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 3.052rem; line-height: 1.1; margin-bottom: 0.5rem;">Heading 4XL</div>
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 2.441rem; line-height: 1.15; margin-bottom: 0.5rem;">Heading 3XL</div>
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 1.953rem; line-height: 1.2; margin-bottom: 0.5rem;">Heading 2XL</div>
<div style="font-family: 'Barlow Condensed', sans-serif; font-size: 1.563rem; line-height: 1.3; margin-bottom: 0.5rem;">Heading XL</div>
<div style="font-family: 'Source Sans 3', sans-serif; font-size: 1.25rem; line-height: 1.5; margin-bottom: 0.5rem;">Large Text</div>
<div style="font-family: 'Source Sans 3', sans-serif; font-size: 1rem; line-height: 1.6; margin-bottom: 0.5rem;">Base Text (16px)</div>
<div style="font-family: 'Source Sans 3', sans-serif; font-size: 0.875rem; line-height: 1.5; margin-bottom: 0.5rem;">Small Text (14px)</div>
<div style="font-family: 'Source Sans 3', sans-serif; font-size: 0.75rem; line-height: 1.4;">Extra Small (12px)</div>
</div>

## Usage Guidelines

### Import Google Fonts

Add these imports to your HTML or CSS:

```html
<!-- In HTML head -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```

```css
/* Or in CSS */
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap');
```

### Typography Tokens

Import the typography tokens CSS:

```css
@import 'design-system/tokens/typography.css';

/* Use in components */
body {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
}

h1 {
  font-family: var(--font-heading);
  font-size: var(--font-size-4xl);
  line-height: var(--line-height-4xl);
  font-weight: var(--font-weight-heading-bold);
}
```

### Heading Hierarchy

Use headings in semantic order:

```html
<h1>Page Title (4XL)</h1>
<h2>Section Heading (3XL)</h2>
<h3>Subsection Heading (2XL)</h3>
<h4>Minor Heading (XL)</h4>
<h5>Small Heading (LG)</h5>
<h6>Tiny Heading (Base, Semibold)</h6>
```

### Line Height Best Practices

Line heights are optimized for each size:

- **Large text (4XL-5XL)**: Tighter line height (1.05-1.1) for impact
- **Headings (XL-3XL)**: Balanced spacing (1.15-1.3)
- **Body text (Base-LG)**: Comfortable reading (1.5-1.6)
- **Small text (XS-SM)**: Adequate spacing (1.4-1.5)

```css
.hero-title {
  font-size: var(--font-size-5xl);
  line-height: var(--line-height-5xl);  /* 1.05 */
}

.body-text {
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);  /* 1.6 */
}
```

### Font Weight Usage

Use appropriate weights for emphasis and hierarchy:

```css
/* Display font - only one weight available */
.display-text {
  font-family: var(--font-display);
  font-weight: var(--font-weight-display-regular);  /* 400 */
}

/* Headings - three weights */
.heading-bold {
  font-family: var(--font-heading);
  font-weight: var(--font-weight-heading-bold);  /* 700 */
}

.heading-medium {
  font-weight: var(--font-weight-heading-medium);  /* 500 */
}

/* Body - two weights */
.body-regular {
  font-family: var(--font-body);
  font-weight: var(--font-weight-body-regular);  /* 400 */
}

.body-semibold {
  font-weight: var(--font-weight-body-semibold);  /* 600 */
}

/* Code - two weights */
.code-regular {
  font-family: var(--font-mono);
  font-weight: var(--font-weight-mono-regular);  /* 400 */
}

.code-medium {
  font-weight: var(--font-weight-mono-medium);  /* 500 */
}
```

## Accessibility

### Contrast Requirements

Ensure text meets WCAG AA standards:

- **Normal text** (< 18px): 4.5:1 contrast ratio minimum
- **Large text** (≥ 18px or ≥ 14px bold): 3:1 contrast ratio minimum
- **AAA standard**: 7:1 for normal, 4.5:1 for large

The Amelia color tokens are designed to meet these requirements:

```css
/* Good contrast examples */
.dark-mode-text {
  background-color: var(--background);  /* #0D1A12 */
  color: var(--foreground);              /* #EFF8E2 */
  /* Contrast ratio: ~14:1 (AAA) */
}

.light-mode-text {
  background-color: var(--background);  /* #FDF8F0 */
  color: var(--foreground);              /* #1A2F23 */
  /* Contrast ratio: ~12:1 (AAA) */
}
```

### Responsive Typography

Use relative units (rem) for scalability:

::: tip Best Practice
```css
/* Good - uses rem (scales with user preferences) */
.text {
  font-size: var(--font-size-base);  /* 1rem = 16px */
}
```
:::

::: danger Avoid
```css
/* Bad - fixed pixels don't respect user preferences */
.text {
  font-size: 16px;
}
```
:::

### Line Length

Maintain optimal line length for readability:

- **Optimal**: 45-75 characters per line
- **Maximum**: 90 characters per line

```css
.readable-content {
  max-width: 65ch;  /* Approximately 65 characters */
  margin: 0 auto;
}
```

## Common Patterns

### Hero Section

```css
.hero {
  font-family: var(--font-display);
  font-size: var(--font-size-5xl);
  line-height: var(--line-height-5xl);
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--primary);
}
```

### Article Content

```css
.article {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--foreground);
  max-width: 65ch;
}

.article h2 {
  font-family: var(--font-heading);
  font-size: var(--font-size-3xl);
  line-height: var(--line-height-3xl);
  font-weight: var(--font-weight-heading-bold);
  margin-top: 2em;
  margin-bottom: 0.5em;
}
```

### Code Blocks

```css
.code-block {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-sm);
  background-color: var(--muted);
  padding: 1rem;
  border-radius: 0.5rem;
  overflow-x: auto;
}

.inline-code {
  font-family: var(--font-mono);
  font-size: 0.9em;  /* Slightly smaller than surrounding text */
  background-color: var(--muted);
  padding: 0.2em 0.4em;
  border-radius: 0.25rem;
}
```

### UI Components

```css
.button {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-body-semibold);
  letter-spacing: 0.01em;
}

.label {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-body-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.caption {
  font-family: var(--font-body);
  font-size: var(--font-size-xs);
  color: var(--muted-foreground);
}
```

## Next Steps

- Explore the [Color System](/design-system/color-system) for text colors
- Create [Diagrams](/design-system/diagrams) with consistent fonts
- Build [Presentations](/design-system/presentations) using the type scale
- Reference the complete [Token API](/design-system/tokens)
