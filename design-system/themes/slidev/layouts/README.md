# Slidev Custom Layouts

This directory contains custom Slidev layouts for the Amelia design system theme.

## Available Layouts

### 1. action.vue
Standard action-title slide with title, subtitle, and source footer.

**Props:**
- `title` (required): Main slide title
- `subtitle` (optional): Subtitle text
- `source` (optional): Source citation for footer

**Usage:**
```md
---
layout: action
title: "Next Steps"
subtitle: "Key Actions for Q4"
source: "Strategic Planning 2025"
---

- Action item 1
- Action item 2
- Action item 3
```

### 2. scqa.vue
SCQA framework (4-panel) for executive narratives. Displays Situation, Complication, Question, and Answer in a 2x2 grid layout.

**Named Slots:**
- `::situation::`
- `::complication::`
- `::question::`
- `::answer::`

**Usage:**
```md
---
layout: scqa
---

::situation::
Current market conditions and baseline metrics.
::

::complication::
Emerging challenges and competitive pressures.
::

::question::
What strategic approach should we take?
::

::answer::
Recommended solution with clear benefits.
::
```

### 3. summary.vue
Executive summary with recommendation callout box.

**Props:**
- `title` (required): Slide title
- `recommendation` (optional): Text for highlighted recommendation box

**Usage:**
```md
---
layout: summary
title: "Executive Summary"
recommendation: "Proceed with phased rollout beginning Q1 2025"
---

- Key finding 1
- Key finding 2
- Key finding 3
```

### 4. data.vue
Full-bleed chart slide optimized for data visualization. Chart covers 90% of body zone.

**Props:**
- `title` (required): Slide title
- `chartTitle` (optional): Chart-specific title
- `source` (optional): Source citation for footer

**Usage:**
```md
---
layout: data
title: "Q4 Performance"
chartTitle: "Revenue Growth by Region"
source: "Internal Analytics Dashboard"
---

<YourChartComponent />
```

### 5. ghost.vue
Wireframe/planning mode for early-stage presentations with draft watermark.

**Props:**
- `title` (required): Slide title
- `placeholder` (optional): Placeholder text for content area
- `notes` (optional): Notes/comments (displayed as sticky notes)

**Usage:**
```md
---
layout: ghost
title: "Future Feature Concept"
placeholder: "Wireframe for new dashboard goes here"
notes: "Need to validate with stakeholders before proceeding"
---

[Content in planning phase]
```

## Design System Integration

All layouts use Amelia design tokens from `../styles/base.css`:

- **Colors**: Automatically adapt to dark/light mode using CSS custom properties
- **Typography**: Use design system fonts (display, heading, body, mono)
- **Spacing**: Follow consistent padding and margin conventions
- **Borders**: Use system border colors and styles

## Dark/Light Mode Support

All layouts automatically support both dark and light modes through:
- System preference detection (`prefers-color-scheme`)
- Manual override via `.light` class on root element
- Design token inheritance from `../../tokens/colors.css`

## License

This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
