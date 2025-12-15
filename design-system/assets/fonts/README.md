# Amelia Design System - Fonts

This directory contains self-hosted font files for the Amelia design system. All fonts are downloaded from Google Fonts and stored locally to eliminate external requests in production.

## Font Families

### Bebas Neue
- **Purpose**: Display font for headers
- **Weights**: 400 (Regular)
- **Files**: `bebas-neue-regular.woff2`

### Barlow Condensed
- **Purpose**: Primary UI font
- **Weights**: 500 (Medium), 600 (SemiBold), 700 (Bold)
- **Files**:
  - `barlow-condensed-500.woff2`
  - `barlow-condensed-600.woff2`
  - `barlow-condensed-700.woff2`

### Source Sans 3
- **Purpose**: Body text font
- **Type**: Variable font (weight range 200-900)
- **Files**: `source-sans-3-variable.woff2`

### IBM Plex Mono
- **Purpose**: Monospace font for code
- **Weights**: 400 (Regular), 500 (Medium)
- **Files**:
  - `ibm-plex-mono-400.woff2`
  - `ibm-plex-mono-500.woff2`

## Usage

### In Design System
Import the `fonts.css` file to load all font-face declarations:

```css
@import './fonts.css';
```

The font families can then be used in your CSS:

```css
body {
  font-family: 'Source Sans 3', sans-serif;
}

h1, h2, h3 {
  font-family: 'Bebas Neue', sans-serif;
}

.ui-text {
  font-family: 'Barlow Condensed', sans-serif;
}

code, pre {
  font-family: 'IBM Plex Mono', monospace;
}
```

### In VitePress Documentation
The fonts are also available in `/docs/site/public/fonts/` with their own `fonts.css` file that uses absolute paths to the `/fonts/` directory.

## File Format

All fonts are provided in WOFF2 format, which offers:
- Best compression ratio (smaller file sizes)
- Broad browser support (all modern browsers)
- Fast loading performance

## License

All fonts are licensed under the Open Font License (OFL) and are free to use for personal and commercial projects.

- Bebas Neue: https://github.com/dharmatype/Bebas-Neue
- Barlow Condensed: https://github.com/jpt/barlow
- Source Sans 3: https://github.com/adobe-fonts/source-sans
- IBM Plex Mono: https://github.com/IBM/plex

## Updating Fonts

To update the fonts, run the following commands to download the latest versions from Google Fonts:

```bash
cd design-system/assets/fonts

# Bebas Neue
curl -s "https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o bebas-neue-regular.woff2

# Barlow Condensed
curl -s "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o barlow-condensed-500.woff2

curl -s "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o barlow-condensed-600.woff2

curl -s "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o barlow-condensed-700.woff2

# Source Sans 3 (variable font - single file for all weights)
curl -s "https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@200..900&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o source-sans-3-variable.woff2

# IBM Plex Mono
curl -s "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o ibm-plex-mono-400.woff2

curl -s "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  | grep -o 'https://[^)]*\.woff2' | head -1 \
  | xargs curl -o ibm-plex-mono-500.woff2

# Copy to docs site
cp *.woff2 ../../../docs/site/public/fonts/
```
