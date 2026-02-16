---
name: review-css-complexity
description: Scan codebase for overly complex CSS/styling patterns that should be simplified
---

Scan the codebase for overly complex CSS and styling patterns. Look for:

## Red Flags

1. **Absolute positioning with placeholders** - If you see absolute positioning combined with invisible placeholder elements to maintain layout, it's probably overcomplicated. Use flexbox/grid instead.

2. **Complex width/height calculations** - Formulas like `width: ${(hasMore ? visibleCount + Math.min(3, hiddenCount) - 1 : visibleCount - 1) * 16 + 120}px` are a code smell. Use CSS variables or simpler layouts.

3. **Nested positioning contexts** - Multiple layers of relative/absolute positioning that could be flattened.

4. **Transform calculations** - Complex `translateX/translateY` calculations when simple flexbox/grid would work.

5. **Manual spacing calculations** - Computing gaps/offsets manually instead of using CSS gap, space-x, or margins.

## What to Look For

Search for files containing:
- `style={{` with complex JavaScript expressions
- Multiple layers of `absolute` and `relative` positioning
- Placeholder divs with `opacity-0` used for layout
- Calculations involving multiple conditional operators in inline styles
- Comments explaining complex positioning logic (if it needs explaining, it's too complex)

## Good Alternatives

- Flexbox with `-space-x-*` for overlapping elements
- CSS Grid for complex layouts
- CSS custom properties for dynamic values
- Tailwind utility classes over inline styles

## Output

For each file with issues:
1. File path and line numbers
2. What's overcomplicated
3. Suggested simpler approach
4. Estimated complexity reduction (high/medium/low priority)

Focus on dashboard/src and amelia frontend code.
