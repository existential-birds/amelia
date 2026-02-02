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
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    return (
      <div
        className={cn(
          'flex h-4 w-4 items-center justify-center rounded-sm bg-muted text-[10px] font-medium uppercase text-muted-foreground',
          className
        )}
      >
        {provider.charAt(0)}
      </div>
    );
  }

  return (
    <img
      src={`https://models.dev/logos/${provider}.svg`}
      alt={provider}
      className={cn('h-4 w-4 rounded-sm', className)}
      onError={() => setHasError(true)}
    />
  );
}
