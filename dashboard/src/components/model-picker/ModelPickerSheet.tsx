import { useState, useEffect, useMemo, type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { useModelsStore } from '@/store/useModelsStore';
import { useRecentModels } from '@/hooks/useRecentModels';
import { ModelSearchFilters } from './ModelSearchFilters';
import { ModelList } from './ModelList';
import { getPriceTier, filterModelsByRequirements } from '@/lib/models-utils';
import { AGENT_MODEL_REQUIREMENTS } from './constants';
import type { ModelInfo } from './types';

interface ModelPickerSheetProps {
  agentKey: string;
  currentModel: string | null;
  onSelect: (modelId: string) => void;
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * Format agent key for display (e.g., "plan_validator" -> "Plan Validator").
 */
function formatAgentName(agentKey: string): string {
  return agentKey
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Filter models by search query and user-selected filters.
 */
function filterModels(
  models: ModelInfo[],
  searchQuery: string,
  capabilities: string[],
  priceTier: string | null,
  minContext: number | null
): ModelInfo[] {
  return models.filter((model) => {
    // Search query (name or provider)
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const matchesName = model.name.toLowerCase().includes(query);
      const matchesProvider = model.provider.toLowerCase().includes(query);
      if (!matchesName && !matchesProvider) {
        return false;
      }
    }

    // User-selected capabilities filter
    for (const cap of capabilities) {
      if (cap === 'reasoning' && !model.capabilities.reasoning) return false;
      if (cap === 'structured_output' && !model.capabilities.structured_output) return false;
    }

    // User-selected price tier filter
    if (priceTier) {
      const modelTier = getPriceTier(model.cost.output);
      if (modelTier !== priceTier) return false;
    }

    // User-selected context size filter
    if (minContext && model.limit.context < minContext) {
      return false;
    }

    return true;
  });
}

/**
 * Sheet component for browsing and selecting models.
 */
export function ModelPickerSheet({
  agentKey,
  currentModel,
  onSelect,
  trigger,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
}: ModelPickerSheetProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = controlledOnOpenChange ?? setInternalOpen;
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([]);
  const [selectedPriceTier, setSelectedPriceTier] = useState<string | null>(null);
  const [minContextSize, setMinContextSize] = useState<number | null>(null);

  const { recentModelIds, addRecentModel } = useRecentModels();
  const models = useModelsStore((state) => state.models);
  const isLoading = useModelsStore((state) => state.isLoading);
  const error = useModelsStore((state) => state.error);
  const fetchModels = useModelsStore((state) => state.fetchModels);
  const refreshModels = useModelsStore((state) => state.refreshModels);

  // Fetch models when sheet opens
  useEffect(() => {
    if (open) {
      fetchModels();
    }
  }, [open, fetchModels]);

  // Get agent-filtered models
  const agentModels = useMemo(() => {
    const requirements = AGENT_MODEL_REQUIREMENTS[agentKey];
    if (!requirements) {
      return models;
    }
    return filterModelsByRequirements(models, requirements);
  }, [agentKey, models]);

  // Apply user filters
  const filteredModels = useMemo(
    () =>
      filterModels(
        agentModels,
        searchQuery,
        selectedCapabilities,
        selectedPriceTier,
        minContextSize
      ),
    [agentModels, searchQuery, selectedCapabilities, selectedPriceTier, minContextSize]
  );

  const handleSelect = (modelId: string) => {
    addRecentModel(modelId);
    onSelect(modelId);
    setOpen(false);
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setSelectedCapabilities([]);
    setSelectedPriceTier(null);
    setMinContextSize(null);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {trigger && <SheetTrigger asChild>{trigger}</SheetTrigger>}
      <SheetContent
        side="right"
        className="w-full sm:max-w-[450px] flex flex-col p-0"
      >
        {/* Header */}
        <SheetHeader className="px-4 py-3 border-b border-border/30 flex-row items-center justify-between">
          <SheetTitle className="text-base">
            Select Model for {formatAgentName(agentKey)}
          </SheetTitle>
          <SheetDescription className="sr-only">
            Browse and select a model for the {formatAgentName(agentKey)} agent
          </SheetDescription>
          <Button
            variant="ghost"
            size="icon"
            onClick={refreshModels}
            disabled={isLoading}
            aria-label="Refresh models"
            className="h-8 w-8"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </SheetHeader>

        {/* Filters */}
        <div className="px-4 py-3 border-b border-border/30">
          <ModelSearchFilters
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            selectedCapabilities={selectedCapabilities}
            onCapabilitiesChange={setSelectedCapabilities}
            selectedPriceTier={selectedPriceTier}
            onPriceTierChange={setSelectedPriceTier}
            minContextSize={minContextSize}
            onMinContextChange={setMinContextSize}
            onClearFilters={handleClearFilters}
          />
        </div>

        {/* Model list */}
        <ModelList
          models={filteredModels}
          recentModelIds={recentModelIds}
          onSelect={handleSelect}
          selectedModelId={currentModel}
          isLoading={isLoading}
          error={error}
          onRetry={refreshModels}
        />
      </SheetContent>
    </Sheet>
  );
}
