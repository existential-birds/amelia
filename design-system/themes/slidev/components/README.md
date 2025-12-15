# Slidev Visualization Components

Professional consulting visualization components for the Amelia Slidev theme. All components use Amelia design tokens and support both dark and light modes.

## Components

### 1. PyramidDiagram

Visualizes the Pyramid Principle hierarchy with layered trapezoids.

**Props:**
- `layers: Layer[]` - Array of pyramid layers from top (most important) to bottom
  - `label: string` - Primary text for the layer
  - `detail?: string` - Optional secondary detail text

**Example:**
```vue
<PyramidDiagram :layers="[
  { label: 'Main Message', detail: 'Key recommendation' },
  { label: 'Supporting Point 1', detail: 'Evidence' },
  { label: 'Supporting Point 2', detail: 'Analysis' },
]" />
```

---

### 2. SCQABlock

Single SCQA quadrant with appropriate color coding for structured business communication.

**Props:**
- `type: 'situation' | 'complication' | 'question' | 'answer'` - Type determines color and icon
- `title: string` - Title text for the block

**Example:**
```vue
<SCQABlock type="situation" title="Current State">
  <p>We have 5 manual processes consuming 20 hours/week</p>
</SCQABlock>
```

---

### 3. HarveyBall

Qualitative indicator using SVG circles for quick visual assessment.

**Props:**
- `fill: 'empty' | 'quarter' | 'half' | 'three-quarter' | 'full'` - Fill level
- `size?: 'sm' | 'md' | 'lg'` - Size variant (default: 'md')

**Example:**
```vue
<HarveyBall fill="three-quarter" size="lg" />
```

---

### 4. LayerCakeDiagram

Stacked horizontal bands for architecture layers or technology stacks.

**Props:**
- `layers: Layer[]` - Array of layers from top to bottom
  - `label: string` - Primary label for the layer
  - `sublabel?: string` - Optional secondary label (e.g., technologies)
  - `highlight?: boolean` - Whether this layer should be highlighted

**Example:**
```vue
<LayerCakeDiagram :layers="[
  { label: 'Presentation', sublabel: 'React, Vue', highlight: true },
  { label: 'Business Logic', sublabel: 'Python, FastAPI' },
  { label: 'Data Layer', sublabel: 'PostgreSQL, Redis' },
]" />
```

---

### 5. ChevronFlow

Arrow-shaped process steps with status colors for workflows and pipelines.

**Props:**
- `steps: Step[]` - Array of process steps in order
  - `label: string` - Label for the step
  - `status: 'completed' | 'active' | 'pending'` - Current status

**Example:**
```vue
<ChevronFlow :steps="[
  { label: 'Plan', status: 'completed' },
  { label: 'Build', status: 'active' },
  { label: 'Deploy', status: 'pending' },
]" />
```

---

### 6. WaterfallBar

Bridge chart segment for visualizing sequential value changes.

**Props:**
- `value: number | string` - Numeric value to display
- `label: string` - Label for the bar
- `type: 'start' | 'increase' | 'decrease' | 'end'` - Type of bar segment
- `showConnector?: boolean` - Whether to show connector line to previous bar

**Example:**
```vue
<WaterfallBar value="50" label="Q1 Revenue" type="start" />
<WaterfallBar value="15" label="Growth" type="increase" showConnector />
<WaterfallBar value="-10" label="Costs" type="decrease" showConnector />
<WaterfallBar value="55" label="Q2 Revenue" type="end" showConnector />
```

---

### 7. RecommendationBox

Highlighted callout box with colored left border for key messages.

**Props:**
- `type: 'recommendation' | 'warning' | 'insight' | 'action'` - Type determines styling and icon

**Example:**
```vue
<RecommendationBox type="recommendation">
  <p>Implement automated testing to reduce deployment time by 40%</p>
</RecommendationBox>
```

## Design Features

All components include:

- **TypeScript props** - Full type safety
- **Design tokens** - Consistent Amelia brand colors and typography
- **Dark/light mode** - Automatic theme support
- **Responsive** - Mobile-optimized layouts
- **Accessible** - ARIA labels and semantic HTML
- **Interactive** - Hover effects and smooth transitions
- **Print-friendly** - Optimized for PDF export
- **JSDoc comments** - Complete inline documentation

## Usage in Slidev

Import components in your slides:

```markdown
---
theme: ./design-system/themes/slidev
---

# My Slide

<PyramidDiagram :layers="layers" />
```

Components are automatically available in all slides when using the Amelia theme.

## License

Mozilla Public License 2.0 - See component headers for details.
