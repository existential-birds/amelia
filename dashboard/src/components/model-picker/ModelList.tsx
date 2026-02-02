import { AlertCircle, RefreshCw } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ModelListItem } from './ModelListItem';
import type { ModelInfo } from './types';

interface ModelListProps {
  models: ModelInfo[];
  recentModelIds: string[];
  onSelect: (modelId: string) => void;
  selectedModelId: string | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

/**
 * Loading skeleton for model list.
 */
function ModelListSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2" data-testid="model-skeleton">
          <Skeleton className="h-4 w-4 rounded" />
          <div className="flex-1 space-y-1">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  );
}

/**
 * Error state with retry button.
 */
function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="p-4">
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription className="flex items-center justify-between">
          <span>{error}</span>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} className="ml-2">
              <RefreshCw className="h-3 w-3 mr-1" />
              Retry
            </Button>
          )}
        </AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * Empty state when no models match filters.
 */
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
      <p>No models match your filters.</p>
      <p className="text-sm mt-1">Try adjusting your search or clearing filters.</p>
    </div>
  );
}

/**
 * Model list with recent models section and all models.
 */
export function ModelList({
  models,
  recentModelIds,
  onSelect,
  selectedModelId,
  isLoading,
  error,
  onRetry,
}: ModelListProps) {
  if (isLoading) {
    return <ModelListSkeleton />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={onRetry} />;
  }

  if (models.length === 0) {
    return <EmptyState />;
  }

  // Split into recent and all models
  const recentModels = recentModelIds
    .map((id) => models.find((m) => m.id === id))
    .filter((m): m is ModelInfo => m !== undefined);

  const hasRecentModels = recentModels.length > 0;

  // Filter out recent models from all models section to avoid duplicates
  const recentIdSet = new Set(recentModelIds);
  const nonRecentModels = models.filter((m) => !recentIdSet.has(m.id));

  return (
    <ScrollArea className="flex-1">
      <div className="divide-y divide-border/30">
        {/* Recent models section */}
        {hasRecentModels && (
          <div>
            <div className="px-3 py-2 bg-muted/30">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Recent
              </span>
            </div>
            {recentModels.map((model) => (
              <ModelListItem
                key={`recent-${model.id}`}
                model={model}
                onSelect={onSelect}
                isSelected={selectedModelId === model.id}
              />
            ))}
            <Separator />
          </div>
        )}

        {/* All models section */}
        <div>
          {hasRecentModels && (
            <div className="px-3 py-2 bg-muted/30">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                All Models
              </span>
            </div>
          )}
          {nonRecentModels.map((model) => (
            <ModelListItem
              key={model.id}
              model={model}
              onSelect={onSelect}
              isSelected={selectedModelId === model.id}
            />
          ))}
        </div>
      </div>
    </ScrollArea>
  );
}
