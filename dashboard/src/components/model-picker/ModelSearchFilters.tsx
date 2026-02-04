import { Search, X, ChevronDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface ModelSearchFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedCapabilities: string[];
  onCapabilitiesChange: (capabilities: string[]) => void;
  selectedPriceTier: string | null;
  onPriceTierChange: (tier: string | null) => void;
  minContextSize: number | null;
  onMinContextChange: (size: number | null) => void;
  onClearFilters: () => void;
}

const CAPABILITY_OPTIONS = [
  { value: 'reasoning', label: 'Reasoning' },
  { value: 'structured_output', label: 'Structured Output' },
];

const PRICE_TIER_OPTIONS = [
  { value: 'budget', label: 'Budget (< $1)' },
  { value: 'standard', label: 'Standard ($1-$10)' },
  { value: 'premium', label: 'Premium (> $10)' },
];

const CONTEXT_SIZE_OPTIONS = [
  { value: 32000, label: '32K+' },
  { value: 64000, label: '64K+' },
  { value: 128000, label: '128K+' },
  { value: 200000, label: '200K+' },
];

/**
 * Search and filter controls for model picker.
 */
/**
 * Get display label for a capability value.
 */
function getCapabilityLabel(value: string): string {
  return CAPABILITY_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

/**
 * Get display label for a price tier value.
 */
function getPriceTierLabel(value: string): string {
  return PRICE_TIER_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

/**
 * Search and filter controls for model picker.
 */
export function ModelSearchFilters({
  searchQuery,
  onSearchChange,
  selectedCapabilities,
  onCapabilitiesChange,
  selectedPriceTier,
  onPriceTierChange,
  minContextSize,
  onMinContextChange,
  onClearFilters,
}: ModelSearchFiltersProps) {
  const hasActiveFilters =
    selectedCapabilities.length > 0 ||
    selectedPriceTier !== null ||
    minContextSize !== null;

  const handleCapabilityToggle = (capability: string) => {
    if (selectedCapabilities.includes(capability)) {
      onCapabilitiesChange(selectedCapabilities.filter((c) => c !== capability));
    } else {
      onCapabilitiesChange([...selectedCapabilities, capability]);
    }
  };

  const removeCapability = (capability: string) => {
    onCapabilitiesChange(selectedCapabilities.filter((c) => c !== capability));
  };

  return (
    <div className="space-y-3">
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search models..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8"
        />
      </div>

      {/* Filter dropdowns */}
      <div className="flex flex-wrap gap-2">
        {/* Capabilities (multi-select with checkboxes) */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="w-[130px] h-8 text-xs justify-between font-normal"
              aria-label="Capabilities"
            >
              {selectedCapabilities.length > 0
                ? `${selectedCapabilities.length} selected`
                : 'Capabilities'}
              <ChevronDown className="ml-1 h-3 w-3 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[150px]">
            {CAPABILITY_OPTIONS.map((opt) => (
              <DropdownMenuCheckboxItem
                key={opt.value}
                checked={selectedCapabilities.includes(opt.value)}
                onCheckedChange={() => handleCapabilityToggle(opt.value)}
              >
                {opt.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Price tier */}
        <Select
          value={selectedPriceTier ?? 'all'}
          onValueChange={(v) => onPriceTierChange(v === 'all' ? null : v)}
        >
          <SelectTrigger className="w-[130px] h-8 text-xs" aria-label="Price tier">
            <SelectValue placeholder="Price tier" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All prices</SelectItem>
            {PRICE_TIER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Context size */}
        <Select
          value={minContextSize?.toString() ?? 'any'}
          onValueChange={(v) => onMinContextChange(v === 'any' ? null : parseInt(v, 10))}
        >
          <SelectTrigger className="w-[100px] h-8 text-xs" aria-label="Context size">
            <SelectValue placeholder="Context" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any context</SelectItem>
            {CONTEXT_SIZE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={String(opt.value)}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Active filter chips */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2">
          {selectedCapabilities.map((cap) => (
            <Badge
              key={cap}
              variant="secondary"
              className="text-xs gap-1 pr-1"
            >
              {getCapabilityLabel(cap)}
              <button
                type="button"
                onClick={() => removeCapability(cap)}
                className="ml-1 hover:text-destructive"
                aria-label={`Remove ${getCapabilityLabel(cap)} filter`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          ))}
          {selectedPriceTier && (
            <Badge variant="secondary" className="text-xs gap-1 pr-1">
              {getPriceTierLabel(selectedPriceTier)}
              <button
                type="button"
                onClick={() => onPriceTierChange(null)}
                className="ml-1 hover:text-destructive"
                aria-label={`Remove ${getPriceTierLabel(selectedPriceTier)} filter`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          )}
          {minContextSize && (
            <Badge variant="secondary" className="text-xs gap-1 pr-1">
              {minContextSize / 1000}K+
              <button
                type="button"
                onClick={() => onMinContextChange(null)}
                className="ml-1 hover:text-destructive"
                aria-label={`Remove ${minContextSize / 1000}K+ context filter`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="h-6 px-2 text-xs"
            aria-label="Clear filters"
          >
            Clear filters
          </Button>
        </div>
      )}
    </div>
  );
}
