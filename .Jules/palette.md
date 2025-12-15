# Palette's Journal

## 2024-05-22 - Accessibility in Dynamic Forms
**Learning:** When revealing form fields dynamically (like a rejection reason), focus management is critical. Users on screen readers or using keyboards might miss the new field if focus isn't moved there.
**Action:** Use `autoFocus` on the first input of a dynamically revealed form section, or programmatic focus management.
