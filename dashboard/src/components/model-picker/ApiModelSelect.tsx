import { useEffect } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useModelsStore } from '@/store/useModelsStore';
import { useRecentModels } from '@/hooks/useRecentModels';
import { ModelPickerSheet } from './ModelPickerSheet';
import { ProviderLogo } from './ProviderLogo';
import type { ModelInfo } from './types';

interface ApiModelSelectProps {
  agentKey: string;
  value: string;
  onChange: (modelId: string) => void;
}

/**
 * Dropdown with recent models + browse link for API driver model selection.
 */
export function ApiModelSelect({ agentKey, value, onChange }: ApiModelSelectProps) {
  const { models, fetchModels } = useModelsStore();
  const { recentModelIds, addRecentModel } = useRecentModels();

  // Fetch models on mount to populate recent models display
  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  // Get recent models that exist in the store
  const recentModels = recentModelIds
    .map((id) => models.find((m) => m.id === id))
    .filter((m): m is ModelInfo => m !== undefined)
    .slice(0, 5); // Show max 5 in dropdown

  const handleSelect = (modelId: string) => {
    addRecentModel(modelId);
    onChange(modelId);
  };

  return (
    <div className="space-y-1">
      <Select value={value} onValueChange={handleSelect}>
        <SelectTrigger className="h-7 w-full sm:w-[180px] text-xs bg-background/50">
          <SelectValue placeholder="Select model..." />
        </SelectTrigger>
        <SelectContent>
          {recentModels.length > 0 ? (
            <>
              {recentModels.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  <span className="flex items-center gap-2">
                    <ProviderLogo provider={model.provider} className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{model.name}</span>
                  </span>
                </SelectItem>
              ))}
              <Separator className="my-1" />
            </>
          ) : (
            <SelectItem value={value || '_placeholder'} disabled={!value}>
              {value || 'No recent models'}
            </SelectItem>
          )}
        </SelectContent>
      </Select>

      <ModelPickerSheet
        agentKey={agentKey}
        currentModel={value}
        onSelect={handleSelect}
        trigger={
          <Button variant="link" size="sm" className="h-auto p-0 text-xs">
            Browse all models...
          </Button>
        }
      />
    </div>
  );
}
