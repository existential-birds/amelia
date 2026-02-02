import { cn } from '@/lib/utils';

interface ProviderLogoProps {
  provider: string;
  className?: string;
}

/**
 * Provider logo from models.dev CDN.
 */
export function ProviderLogo({ provider, className }: ProviderLogoProps) {
  return (
    <img
      src={`https://models.dev/logos/${provider}.svg`}
      alt={provider}
      className={cn('h-4 w-4 rounded-sm', className)}
      onError={(e) => {
        // Preserve layout space but hide broken image
        (e.target as HTMLImageElement).style.visibility = 'hidden';
      }}
    />
  );
}
