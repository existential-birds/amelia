import { useState } from 'react';

import { cn } from '@/lib/utils';

interface ProviderLogoProps {
  provider: string;
  className?: string;
}

/**
 * Provider logo from models.dev CDN with fallback to provider initial.
 */
export function ProviderLogo({ provider, className }: ProviderLogoProps) {
  const [loaded, setLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  const showFallback = hasError || !loaded;

  return (
    <div className={cn('relative h-4 w-4', className)}>
      {/* Fallback shown while loading or on error */}
      {showFallback && (
        <div className="flex h-full w-full items-center justify-center rounded-sm bg-muted text-[10px] font-medium uppercase text-muted-foreground">
          {provider.charAt(0)}
        </div>
      )}
      {/* Image hidden until loaded successfully */}
      {!hasError && (
        <img
          src={`https://models.dev/logos/${provider}.svg`}
          alt={provider}
          className={cn(
            'absolute inset-0 h-full w-full rounded-sm',
            !loaded && 'invisible'
          )}
          onLoad={() => setLoaded(true)}
          onError={() => setHasError(true)}
        />
      )}
    </div>
  );
}
