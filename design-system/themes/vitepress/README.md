# Amelia VitePress Theme

VitePress theme for the Amelia Design System documentation.

## Features

- **Dark Mode (Primary)**: Deep forest greens (#0D1A12) with gold accents (#FFC857)
- **Light Mode (Secondary)**: Daytime theme with warm cream backgrounds (#FDF8F0) and professional blue accents (#2E6B9C)
- **Custom Typography**: Bebas Neue (display), Barlow Condensed (headings), Source Sans 3 (body), IBM Plex Mono (code)
- **OKLCH Colors**: Perceptually uniform color space for better color transitions
- **Accessible**: WCAG 2.1 AA compliant contrast ratios

## Installation

### Option 1: Use the theme directly in your VitePress project

```bash
# Copy theme files to your VitePress project
cp -r design-system/themes/vitepress/.vitepress/theme/* .vitepress/theme/
```

### Option 2: Import theme styles in your custom theme

```typescript
// .vitepress/theme/index.ts
import DefaultTheme from 'vitepress/theme'
import '../../design-system/themes/vitepress/style.css'
import '../../design-system/themes/vitepress/custom.css'

export default {
  extends: DefaultTheme,
  // ... your customizations
}
```

## Usage

The theme automatically applies based on system color scheme preference. Colors and typography are exposed as CSS custom properties.

### Using Color Tokens

```css
.my-component {
  background-color: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-brand-1);
}
```

### Available VitePress Color Variables

#### Base Colors

- `--vp-c-bg` - Main background
- `--vp-c-bg-alt` - Alternate background
- `--vp-c-bg-elv` - Elevated background
- `--vp-c-text-1` - Primary text
- `--vp-c-text-2` - Secondary text
- `--vp-c-text-3` - Tertiary text

#### Brand Colors

- `--vp-c-brand-1` - Primary brand (Gold in dark, Blue in light)
- `--vp-c-brand-2` - Brand hover state
- `--vp-c-brand-3` - Brand active state
- `--vp-c-brand-soft` - Brand with transparency

#### Semantic Colors

- `--vp-c-tip-1` - Tip callouts (Green)
- `--vp-c-warning-1` - Warning callouts (Gold)
- `--vp-c-danger-1` - Danger callouts (Red)
- `--vp-c-info-1` - Info callouts (Blue)

### Typography

```css
/* Font families */
--vp-font-family-base: "Source Sans 3", sans-serif;
--vp-font-family-mono: "IBM Plex Mono", monospace;

/* Custom Amelia fonts */
--amelia-font-heading: "Barlow Condensed", sans-serif;
--amelia-font-display: "Bebas Neue", sans-serif;
```

## Customization

### Override Colors

Create a `custom.css` file in your `.vitepress/theme/` directory:

```css
:root {
  /* Override any color tokens */
  --vp-c-brand-1: #your-color;
}
```

### Add Custom Components

Use the utility classes provided by the theme:

```markdown
<div class="display-text">AMELIA</div>
<div class="heading-text">Section Heading</div>
```

## Callout Styles

The theme provides styled callouts for documentation:

```markdown
::: tip
This is a tip with green accent
:::

::: warning
This is a warning with gold accent
:::

::: danger
This is a danger callout with red accent
:::

::: info
This is an info callout with blue accent
:::
```

## Color Reference

### Dark Mode (Default)

| Token | Hex | Usage |
|-------|-----|-------|
| Background | #0D1A12 | Main page background |
| Foreground | #EFF8E2 | Main text color |
| Brand | #FFC857 | Gold - links, buttons |
| Accent | #5B9BD5 | Blue - interactive elements |
| Tip | #5B8A72 | Green - success states |
| Danger | #A33D2E | Red - error states |

### Light Mode

| Token | Hex | Usage |
|-------|-----|-------|
| Background | #FDF8F0 | Main page background |
| Foreground | #1A2F23 | Main text color |
| Brand | #2E6B9C | Professional blue - links, buttons |
| Accent | #E8B84A | Gold - highlights |
| Tip | #3D7552 | Green - success states |
| Danger | #8B3224 | Red - error states |

## Development

### Building the Theme

The theme is built as part of the VitePress documentation site:

```bash
cd docs/site
npm install
npm run dev    # Development server
npm run build  # Production build
```

### Testing

The theme is tested by building the full documentation site. Any build errors indicate theme issues.

## License

MPL-2.0 - See LICENSE file for details.
