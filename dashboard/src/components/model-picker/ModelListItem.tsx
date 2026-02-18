import { ChevronDown, Wrench, Brain, Braces } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatContextSize, getPriceTier } from '@/lib/models-utils';
import { ProviderLogo } from './ProviderLogo';
import type { ModelInfo } from './types';

interface ModelListItemProps {
  model: ModelInfo;
  onSelect: (modelId: string) => void;
  isSelected?: boolean;
  isExpanded?: boolean;
  onToggleExpand?: (modelId: string) => void;
}

/**
 * Price tier badge with color coding.
 */
function PriceTierBadge({ tier }: { tier: 'budget' | 'standard' | 'premium' }) {
  const variants = {
    budget: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
    standard: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    premium: 'bg-violet-500/10 text-violet-500 border-violet-500/20',
  };

  const labels = {
    budget: 'Budget',
    standard: 'Standard',
    premium: 'Premium',
  };

  return (
    <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', variants[tier])}>
      {labels[tier]}
    </Badge>
  );
}

/**
 * Capability icon with tooltip.
 */
function CapabilityIcon({
  capability,
  enabled,
}: {
  capability: 'tool_call' | 'reasoning' | 'structured_output';
  enabled: boolean;
}) {
  const icons = {
    tool_call: Wrench,
    reasoning: Brain,
    structured_output: Braces,
  };

  const labels = {
    tool_call: 'Tool calling',
    reasoning: 'Reasoning',
    structured_output: 'Structured output',
  };

  const Icon = icons[capability];

  return (
    <span
      title={labels[capability]}
      aria-label={labels[capability]}
      className={cn(
        'inline-flex',
        enabled ? 'text-foreground' : 'text-muted-foreground/30'
      )}
    >
      <Icon className="h-3 w-3" />
    </span>
  );
}

/**
 * Format cost for display (e.g., 3 -> "$3.00 / 1M").
 */
function formatCost(cost: number): string {
  return `$${cost.toFixed(2)} / 1M`;
}

/**
 * Compact model list item with expandable details.
 */
export function ModelListItem({
  model,
  onSelect,
  isSelected,
  isExpanded = false,
  onToggleExpand,
}: ModelListItemProps) {
  const priceTier = getPriceTier(model.cost.output);

  return (
    <div
      className={cn(
        'border-b border-border/30 last:border-b-0',
        isSelected && 'bg-accent/30'
      )}
    >
      {/* Compact row */}
      <button
        type="button"
        onClick={() => onToggleExpand?.(model.id)}
        data-selected={isSelected}
        aria-label={isExpanded ? 'Collapse model details' : 'Expand model details'}
        aria-expanded={isExpanded}
        aria-controls={`model-details-${model.id}`}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-accent/20 transition-colors min-h-[44px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {/* Provider logo */}
        <ProviderLogo provider={model.provider} />

        {/* Model name & provider */}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{model.name}</div>
          <div className="text-xs text-muted-foreground">{model.provider}</div>
        </div>

        {/* Capabilities */}
        <div className="hidden sm:flex items-center gap-1 shrink-0">
          <CapabilityIcon capability="tool_call" enabled={model.capabilities.tool_call} />
          <CapabilityIcon capability="reasoning" enabled={model.capabilities.reasoning} />
          <CapabilityIcon
            capability="structured_output"
            enabled={model.capabilities.structured_output}
          />
        </div>

        {/* Context size */}
        <span className="text-xs text-muted-foreground w-12 text-right shrink-0">
          {formatContextSize(model.limit.context)}
        </span>

        {/* Price tier */}
        <div className="w-[70px] shrink-0 flex justify-end">
          <PriceTierBadge tier={priceTier} />
        </div>

        {/* Expand indicator */}
        <ChevronDown
          className={cn(
            'h-4 w-4 text-muted-foreground transition-transform',
            isExpanded && 'rotate-180'
          )}
        />
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div id={`model-details-${model.id}`} className="px-3 pb-3 pt-1 bg-muted/20">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs mb-3">
            {/* Pricing */}
            <div>
              <div className="text-muted-foreground">Input</div>
              <div>{formatCost(model.cost.input)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Output</div>
              <div>{formatCost(model.cost.output)}</div>
            </div>
            {model.cost.reasoning !== undefined && (
              <div>
                <div className="text-muted-foreground">Reasoning</div>
                <div>{formatCost(model.cost.reasoning)}</div>
              </div>
            )}

            {/* Limits */}
            <div>
              <div className="text-muted-foreground">Context</div>
              <div>{model.limit.context != null ? `${model.limit.context.toLocaleString()} tokens` : 'Unknown'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Max output</div>
              <div>{model.limit.output != null ? `${model.limit.output.toLocaleString()} tokens` : 'Unknown'}</div>
            </div>

            {/* Modalities */}
            <div>
              <div className="text-muted-foreground">Input</div>
              <div>{model.modalities.input.join(', ')}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Output</div>
              <div>{model.modalities.output.join(', ')}</div>
            </div>

            {/* Dates */}
            {model.release_date && (
              <div>
                <div className="text-muted-foreground">Released</div>
                <div>{model.release_date}</div>
              </div>
            )}
            {model.knowledge && (
              <div>
                <div className="text-muted-foreground">Knowledge</div>
                <div>{model.knowledge}</div>
              </div>
            )}
          </div>

          {/* Capabilities (mobile) */}
          <div className="flex sm:hidden items-center gap-2 mb-3">
            <span className="text-xs text-muted-foreground">Capabilities:</span>
            <CapabilityIcon capability="tool_call" enabled={model.capabilities.tool_call} />
            <CapabilityIcon capability="reasoning" enabled={model.capabilities.reasoning} />
            <CapabilityIcon
              capability="structured_output"
              enabled={model.capabilities.structured_output}
            />
          </div>

          {/* Select button */}
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(model.id);
            }}
            aria-label="Select this model"
            className="w-full"
          >
            Select
          </Button>
        </div>
      )}
    </div>
  );
}
