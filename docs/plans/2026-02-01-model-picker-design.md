# Model Selection Picker for API Drivers

**Date**: 2026-02-01
**Status**: Draft
**Author**: Claude (brainstorming session)

## Overview

Replace the hardcoded API model dropdown with a rich, agent-aware model picker that pulls from [models.dev](https://models.dev).

### Goals

- Enable informed model selection with pricing, capabilities, and context limits
- Pre-filter models based on agent requirements (tool_call, reasoning, etc.)
- Provide search and filtering for the 100+ models available via API drivers
- Keep the UI responsive and mobile-friendly

### Non-Goals

- Changing CLI driver model selection (keeps simple opus/sonnet/haiku dropdown)
- Backend changes or model data caching on server
- Per-task cost estimation

## User Flow

1. User opens Profile Edit modal, configures an agent with `api` driver
2. Model field shows a dropdown with recently used models + "Browse all models..." link
3. Clicking "Browse all models..." opens a Sheet (slide-over panel)
4. Sheet shows models filtered by agent requirements (e.g., Architect sees models with tool_call + reasoning)
5. User can search, adjust filters, expand model details
6. Selecting a model closes the Sheet and populates the dropdown
7. Recently used models are tracked in localStorage for quick access next time

## Data Model

### Models.dev Structure

Data fetched from `https://models.dev/api.json`:

```typescript
interface ModelInfo {
  id: string;                    // "claude-sonnet-4-20250514"
  name: string;                  // "Claude Sonnet 4"
  provider: string;              // "anthropic"
  capabilities: {
    tool_call: boolean;
    reasoning: boolean;
    structured_output: boolean;
  };
  limit: {
    context: number;             // 200000
    output: number;              // 16000
  };
  cost: {
    input: number;               // per 1M tokens
    output: number;
    reasoning?: number;
  };
  modalities: {
    input: string[];             // ["text", "image", "pdf"]
    output: string[];            // ["text"]
  };
  release_date?: string;
  knowledge?: string;            // knowledge cutoff
}
```

### Zustand Store

```typescript
// useModelsStore.ts
interface ModelsStore {
  models: ModelInfo[];
  providers: string[];           // unique provider list for filtering
  isLoading: boolean;
  error: string | null;
  lastFetched: number | null;

  fetchModels: () => Promise<void>;
  getModelsForAgent: (agentKey: string) => ModelInfo[];
}
```

### Recently Used (localStorage)

- Key: `amelia:recent-models`
- Value: `string[]` (last 10 model IDs)
- Updated on each model selection

## Agent Capability Mapping

All agents require `tool_call`. Secondary capabilities and context preferences vary:

```typescript
const AGENT_MODEL_REQUIREMENTS: Record<string, AgentRequirements> = {
  architect: {
    capabilities: ['tool_call', 'reasoning', 'structured_output'],
    minContext: 200_000,
    priceTier: 'any',
  },
  developer: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 200_000,
    priceTier: 'any',
  },
  reviewer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 128_000,
    priceTier: 'any',
  },
  plan_validator: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  task_reviewer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  evaluator: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  brainstormer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 64_000,
    priceTier: 'standard',
  },
};
```

### Price Tier Thresholds

Based on output cost per 1M tokens:

| Tier | Output Cost |
|------|-------------|
| Budget | < $1 |
| Standard | $1 - $10 |
| Premium | > $10 |

## UI Components

### Component Hierarchy

```
ModelPickerSheet (Sheet wrapper)
├── SheetHeader
│   ├── Title ("Select Model for {Agent}")
│   └── SheetClose button
├── SearchAndFilters
│   ├── SearchInput (text search by name/provider)
│   ├── FilterChips (active filters, removable)
│   └── FilterDropdowns
│       ├── Capabilities (multi-select)
│       ├── Context Size (min threshold)
│       └── Price Tier (Budget/Standard/Premium)
├── ModelList
│   ├── RecentModelsSection (if any recent, collapsible)
│   │   └── ModelListItem (compact)
│   ├── Separator
│   └── AllModelsSection
│       └── ModelListItem (compact, expandable)
│           └── ModelDetailPanel (expanded state)
└── SheetFooter (mobile: sticky select button)
```

### ModelListItem (Compact View)

- Provider logo (from models.dev CDN: `https://models.dev/logos/{provider}.svg`)
- Model name
- Price tier badge (Budget/Standard/Premium)
- Capability icons (tool, brain, brackets)
- Context size (e.g., "200K")

### ModelDetailPanel (Expanded)

- Full pricing breakdown (input/output/reasoning per 1M tokens)
- All modalities supported
- Release date & knowledge cutoff
- "Select" button

## Responsive Behavior

### Desktop (≥768px)

- Sheet slides in from right, ~450px wide
- Model list scrolls within Sheet
- Expanded detail appears inline below the item
- Clicking outside or X closes Sheet

### Mobile (<768px)

- Sheet slides up from bottom, full height (with drag handle)
- Search input sticky at top
- Filter chips horizontally scrollable
- Model list takes remaining space
- Expanded detail pushes other items down
- Sticky footer with "Select" button when a model is highlighted
- Swipe down to close

### Touch Considerations

- List items have comfortable tap targets (min 44px height)
- Expand/collapse via tap anywhere on item row
- Select via explicit "Select" button (not auto-select on tap)
- Filter dropdowns use native mobile selects on small screens

## Integration with ProfileEditModal

### Current State

Simple dropdown with hardcoded options:

```tsx
<Select value={agent.model} onValueChange={handleModelChange}>
  <SelectContent>
    {MODEL_OPTIONS_BY_DRIVER['api'].map(model => (
      <SelectItem key={model} value={model}>{model}</SelectItem>
    ))}
  </SelectContent>
</Select>
```

### New Component (ApiModelSelect)

Dropdown with recent models + browse link:

```tsx
<div className="space-y-1">
  <Select value={agent.model} onValueChange={onModelChange}>
    <SelectTrigger>
      <SelectValue placeholder="Select model..." />
    </SelectTrigger>
    <SelectContent>
      {recentModels.map(model => (
        <SelectItem key={model.id} value={model.id}>
          <ProviderLogo /> {model.name}
        </SelectItem>
      ))}
      {recentModels.length > 0 && <Separator />}
    </SelectContent>
  </Select>

  <ModelPickerSheet
    agentKey={agentKey}
    currentModel={agent.model}
    onSelect={onModelChange}
    trigger={
      <Button variant="link" size="sm" className="h-auto p-0">
        Browse all models...
      </Button>
    }
  />
</div>
```

### Conditional Rendering

- `api` driver: Show `ApiModelSelect` with full picker
- `cli` driver: Keep existing simple `Select` with opus/sonnet/haiku

## Data Fetching & Error Handling

### Fetch Strategy

```typescript
fetchModels: async () => {
  // Skip if already fetched this session
  if (get().models.length > 0 && get().lastFetched) {
    return;
  }

  set({ isLoading: true, error: null });

  try {
    const response = await fetch('https://models.dev/api.json');
    const data = await response.json();

    // Transform nested provider/models structure to flat list
    const models = flattenModelsData(data);
    const providers = [...new Set(models.map(m => m.provider))];

    set({
      models,
      providers,
      isLoading: false,
      lastFetched: Date.now()
    });
  } catch (error) {
    set({
      error: 'Failed to load models. Check your connection.',
      isLoading: false
    });
  }
}
```

### Error States

| State | UI |
|-------|-----|
| Loading | Skeleton list items |
| Error | Alert with retry button, fallback to recent models |
| Empty results | "No models match your filters" + clear filters button |

### Manual Refresh

Refresh icon button in Sheet header, refetches ignoring cache.

### Offline Resilience

If fetch fails but recent models exist in localStorage, show those with banner: "Showing cached models - couldn't refresh list"

## File Structure

### New Files

```
dashboard/src/
├── components/
│   └── model-picker/
│       ├── ModelPickerSheet.tsx      # Main Sheet wrapper
│       ├── ModelSearchFilters.tsx    # Search + filter controls
│       ├── ModelList.tsx             # List with recent + all sections
│       ├── ModelListItem.tsx         # Compact row, expandable
│       ├── ModelDetailPanel.tsx      # Expanded detail view
│       ├── ApiModelSelect.tsx        # Dropdown + browse link combo
│       ├── constants.ts              # Agent requirements, price tiers
│       └── types.ts                  # ModelInfo, AgentRequirements
├── stores/
│   └── useModelsStore.ts             # Zustand store for models.dev data
└── lib/
    └── models-utils.ts               # flattenModelsData, filterModels helpers
```

### Modified Files

- `ProfileEditModal.tsx` - Import `ApiModelSelect`, conditionally render based on driver

### Tests

```
dashboard/src/__tests__/
├── components/model-picker/
│   ├── ModelPickerSheet.test.tsx     # Sheet open/close, selection
│   ├── ModelList.test.tsx            # Filtering, expansion
│   └── ApiModelSelect.test.tsx       # Dropdown + sheet integration
└── stores/
    └── useModelsStore.test.ts        # Fetch, cache, filter logic
```

## Dependencies

No new dependencies - uses existing shadcn/ui components:
- Sheet
- Select
- Button
- Badge
- Input
- Separator
- ScrollArea

## Open Questions

None - all decisions made during brainstorming session.

## References

- [models.dev GitHub](https://github.com/anomalyco/models.dev)
- [models.dev API](https://models.dev/api.json)
- [shadcn/ui Sheet](https://ui.shadcn.com/docs/components/sheet)
