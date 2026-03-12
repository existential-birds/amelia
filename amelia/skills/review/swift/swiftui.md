# SwiftUI Code Review

## Quick Reference

| Issue Type | Reference |
|------------|-----------|
| View extraction, modifiers, body complexity | — |
| @State, @Binding, @Observable, @Bindable | — |
| LazyStacks, AnyView, ForEach, identity | — |
| VoiceOver, Dynamic Type, labels, traits | — |

## Review Checklist

- [ ] View body under 10 composed elements (extract subviews)
- [ ] Modifiers in correct order (padding before background)
- [ ] @StateObject for view-owned objects, @ObservedObject for passed objects
- [ ] @Bindable used for two-way bindings to @Observable (iOS 17+)
- [ ] LazyVStack/LazyHStack for scrolling lists with 50+ items
- [ ] No AnyView (use @ViewBuilder or generics instead)
- [ ] ForEach uses stable Identifiable IDs (not array indices)
- [ ] All images/icons have accessibilityLabel
- [ ] Custom controls have accessibilityAddTraits(.isButton)
- [ ] Dynamic Type supported (no fixed font sizes)
- [ ] .task modifier for async work (not onAppear + Task)

## Review Questions

1. Could this large view body be split into smaller, reusable Views?
2. Is modifier order intentional? (padding -> background -> frame)
3. Is @StateObject/@ObservedObject usage correct for ownership?
4. Could LazyVStack improve this ScrollView's performance?
5. Would VoiceOver users understand this interface?
