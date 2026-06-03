/**
 * @fileoverview Chip-style input for entering and managing a list of allowed hostnames.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HostChipInputProps {
  hosts: string[];
  onChange: (hosts: string[]) => void;
}

export function HostChipInput({ hosts, onChange }: HostChipInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const isValidHostname = (host: string): boolean => {
    return /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$/.test(host);
  };

  const addHost = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (!trimmed) return;

    if (!isValidHostname(trimmed)) {
      setError('Invalid hostname');
      return;
    }
    if (hosts.includes(trimmed)) {
      setError('Host already added');
      return;
    }

    onChange([...hosts, trimmed]);
    setInputValue('');
    setError(null);
  };

  const removeHost = (host: string) => {
    onChange(hosts.filter((h) => h !== host));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addHost();
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 min-h-[32px]">
        {hosts.map((host) => (
          <Badge
            key={host}
            variant="secondary"
            className="text-xs font-mono gap-1 pl-2 pr-1"
          >
            {host}
            <button
              type="button"
              onClick={() => removeHost(host)}
              className="ml-0.5 rounded-sm hover:bg-muted-foreground/20 p-0.5"
              aria-label={`Remove ${host}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={handleKeyDown}
          placeholder="api.example.com"
          className={cn(
            'bg-background/50 font-mono text-sm flex-1',
            error && 'border-destructive focus-visible:ring-destructive'
          )}
        />
        <Button type="button" variant="outline" size="sm" onClick={addHost}>
          Add
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
