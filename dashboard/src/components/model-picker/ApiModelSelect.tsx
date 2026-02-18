import { useEffect, useState } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { useModelsStore } from '@/store/useModelsStore';
import { useRecentModels } from '@/hooks/useRecentModels';
import { ModelPickerSheet } from './ModelPickerSheet';
import { ProviderLogo } from './ProviderLogo';
import { cn } from '@/lib/utils';
import type { ModelInfo } from './types';

const BROWSE_SENTINEL = Symbol('browse');
const BROWSE_SENTINEL_VALUE = BROWSE_SENTINEL.description ?? '__browse__';

interface ApiModelSelectProps {
  agentKey: string;
  value: string;
  onChange: (modelId: string) => void;
  error?: boolean;
}

/**
 * Dropdown with recent models + browse link for API driver model selection.
 */
export function ApiModelSelect({ agentKey, value, onChange, error }: ApiModelSelectProps) {
  const models = useModelsStore((state) => state.models);
  const fetchModels = useModelsStore((state) => state.fetchModels);
  const { recentModelIds, addRecentModel } = useRecentModels();
  const [sheetOpen, setSheetOpen] = useState(false);

  // Eagerly fetch models on mount (idempotent — fetchModels checks models.length and lastFetched, skips if already loaded)
  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  // Get recent models that exist in the store
  const recentModels = recentModelIds
    .map((id) => models.find((m) => m.id === id))
    .filter((m): m is ModelInfo => m !== undefined)
    .slice(0, 5); // Show max 5 in dropdown

  // Ensure current value is always represented in dropdown items
  const currentInRecent = recentModels.some((m) => m.id === value);
  const currentModel = !currentInRecent && value ? models.find((m) => m.id === value) : undefined;
  const displayModels = currentModel ? [currentModel, ...recentModels] : recentModels;

  // Whether we have a fallback item for a value not yet in the store (e.g. during loading)
  const valueNotYetInStore = value && !displayModels.some((m) => m.id === value);

  const handleSelect = (modelId: string) => {
    if (!modelId) return;
    if (modelId === BROWSE_SENTINEL_VALUE) {
      setSheetOpen(true);
      return;
    }
    addRecentModel(modelId);
    onChange(modelId);
  };

  const handleSheetSelect = (modelId: string) => {
    addRecentModel(modelId);
    onChange(modelId);
  };

  // Show bare button fallback when no models loaded AND no current selection
  if (displayModels.length === 0 && !value) {
    return (
      <ModelPickerSheet
        agentKey={agentKey}
        currentModel={value}
        onSelect={handleSheetSelect}
        trigger={
          <Button variant="outline" size="sm" className={cn('h-7 w-full sm:w-[180px] text-xs', error && !value && 'border-destructive')}>
            Select model...
          </Button>
        }
      />
    );
  }

  return (
    <>
      <Select value={value} onValueChange={handleSelect}>
        <SelectTrigger className={cn('h-7 w-full sm:w-[180px] text-xs bg-background/50', error && !value && 'border-destructive')}>
          <SelectValue placeholder="Select model..." />
        </SelectTrigger>
        <SelectContent>
          {displayModels.map((model) => (
            <SelectItem key={model.id} value={model.id}>
              <span className="flex items-center gap-2">
                <ProviderLogo provider={model.provider} className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{model.name}</span>
              </span>
            </SelectItem>
          ))}
          {valueNotYetInStore && (
            <SelectItem value={value}>
              <span className="truncate text-muted-foreground">{value}</span>
            </SelectItem>
          )}
          <SelectSeparator />
          <SelectItem value={BROWSE_SENTINEL_VALUE}>
            <span className="text-muted-foreground">Browse all models...</span>
          </SelectItem>
        </SelectContent>
      </Select>

      <ModelPickerSheet
        agentKey={agentKey}
        currentModel={value}
        onSelect={handleSheetSelect}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </>
  );
}
