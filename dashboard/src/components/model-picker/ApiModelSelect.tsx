import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useModelsStore } from '@/store/useModelsStore';
import { useRecentModels } from '@/hooks/useRecentModels';
import { ModelPickerSheet } from './ModelPickerSheet';
import { ProviderLogo } from './ProviderLogo';
import { cn } from '@/lib/utils';
import { AGENT_MODEL_REQUIREMENTS } from './constants';
import { filterModelsByRequirements } from '@/lib/models-utils';
import type { ModelInfo } from './types';

const BROWSE_SENTINEL = Symbol('browse');
const BROWSE_SENTINEL_VALUE = BROWSE_SENTINEL.description ?? '__browse__';

interface ApiModelSelectProps {
  agentKey: string;
  value: string;
  onChange: (modelId: string) => void;
  error?: boolean;
  className?: string;
}

/**
 * Dropdown with recent models + browse link for API driver model selection.
 */
export function ApiModelSelect({ agentKey, value, onChange, error, className }: ApiModelSelectProps) {
  const models = useModelsStore((state) => state.models);
  const fetchModels = useModelsStore((state) => state.fetchModels);
  const lookupModelById = useModelsStore((state) => state.lookupModelById);
  const { recentModelIds, addRecentModel } = useRecentModels();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [manualModelId, setManualModelId] = useState(value);
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [requirementsWarning, setRequirementsWarning] = useState<string | null>(null);
  const [unverifiedWarning, setUnverifiedWarning] = useState<string | null>(null);

  // Eagerly fetch models on mount (idempotent — fetchModels checks models.length and lastFetched, skips if already loaded)
  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  useEffect(() => {
    setManualModelId(value);
  }, [value]);

  const recentModels = recentModelIds
    .map((id) => models.find((m) => m.id === id))
    .filter((m): m is ModelInfo => m !== undefined)
    .slice(0, 5);

  // Ensure current value is always represented in dropdown items
  const currentInRecent = recentModels.some((m) => m.id === value);
  const currentModel = !currentInRecent && value ? models.find((m) => m.id === value) : undefined;
  const displayModels = currentModel ? [currentModel, ...recentModels] : recentModels;

  // Whether we have a fallback item for a value not yet in the store (e.g. during loading)
  const valueNotYetInStore = value && !displayModels.some((m) => m.id === value);

  const updateRequirementsWarning = useCallback(
    (model: ModelInfo | undefined) => {
      const requirements = AGENT_MODEL_REQUIREMENTS[agentKey];
      if (!requirements || !model) {
        setRequirementsWarning(null);
        return;
      }

      const matchesRequirements = filterModelsByRequirements([model], requirements).length > 0;
      setRequirementsWarning(
        matchesRequirements ? null : `May not meet ${agentKey} requirements`
      );
    },
    [agentKey]
  );

  useEffect(() => {
    const selectedModel = models.find((model) => model.id === value);
    updateRequirementsWarning(selectedModel);
    if (selectedModel) {
      setUnverifiedWarning(null);
    }
  }, [models, value, updateRequirementsWarning]);

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

  const handleManualLookup = async () => {
    const modelId = manualModelId.trim();
    if (!modelId) {
      return;
    }

    setIsLookingUp(true);
    setUnverifiedWarning(null);

    try {
      const model = await lookupModelById(modelId);
      addRecentModel(model.id);
      onChange(model.id);
      setManualModelId(model.id);
      updateRequirementsWarning(model);
    } catch (error) {
      console.error(`Model lookup failed for "${modelId}":`, error);
      // Any verification failure — 404, network, or timeout — still accepts the
      // typed ID with a non-blocking warning; a genuinely invalid model fails
      // fast at run time on the backend.
      addRecentModel(modelId);
      onChange(modelId);
      setManualModelId(modelId);
      setRequirementsWarning(null);
      setUnverifiedWarning(
        "Couldn't verify this model — it may not exist or support tools"
      );
    } finally {
      setIsLookingUp(false);
    }
  };

  const handleManualKeyDown = async (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') {
      return;
    }

    event.preventDefault();
    await handleManualLookup();
  };

  const selectionControl =
    displayModels.length === 0 && !value ? (
      <ModelPickerSheet
        agentKey={agentKey}
        currentModel={value}
        onSelect={handleSheetSelect}
        trigger={
          <Button variant="outline" size="sm" className={cn('h-7 w-full sm:w-[180px] text-xs', error && !value && 'border-destructive', className)}>
            Select model...
          </Button>
        }
      />
    ) : (
      <Select value={value} onValueChange={handleSelect}>
        <SelectTrigger className={cn('h-7 w-full sm:w-[180px] text-xs bg-background/50', error && !value && 'border-destructive', className)}>
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
    );

  return (
    <div className="space-y-2">
      {selectionControl}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={manualModelId}
          onChange={(event) => {
            setManualModelId(event.target.value);
          }}
          onKeyDown={handleManualKeyDown}
          placeholder="Type any model ID"
          className="h-8 text-xs sm:w-[180px]"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 text-xs"
          onClick={() => {
            void handleManualLookup();
          }}
          disabled={isLookingUp || manualModelId.trim().length === 0}
        >
          {isLookingUp ? 'Looking up...' : 'Use model code'}
        </Button>
      </div>

      {(unverifiedWarning ?? requirementsWarning) && (
        <p className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>{unverifiedWarning ?? requirementsWarning}</span>
        </p>
      )}

      <ModelPickerSheet
        agentKey={agentKey}
        currentModel={value}
        onSelect={handleSheetSelect}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}
