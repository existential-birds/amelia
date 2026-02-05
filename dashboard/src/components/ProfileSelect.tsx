/**
 * @fileoverview Profile selection dropdown for Quick Shot modal.
 *
 * Fetches available profiles and displays them in a styled dropdown
 * with active indicator and tracker type information.
 */

import { useState, useEffect } from 'react';
import { getProfiles, type Profile } from '@/api/settings';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/**
 * Props for the ProfileSelect component.
 */
interface ProfileSelectProps {
  /** Current selected profile ID. */
  value: string;
  /** Callback when profile selection changes. */
  onChange: (profileId: string) => void;
  /** Error message to display. */
  error?: string;
  /** Whether the select is disabled. */
  disabled?: boolean;
  /** ID for accessibility. */
  id?: string;
}

/**
 * Profile selection dropdown component.
 *
 * Fetches profiles from the API and displays them with:
 * - Active profile indicator
 * - Tracker type as secondary info
 * - "None" option for clearing selection
 */
export function ProfileSelect({
  value,
  onChange,
  error,
  disabled,
  id = 'profile',
}: ProfileSelectProps) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function fetchProfiles() {
      try {
        const result = await getProfiles();
        if (mounted) {
          setProfiles(result);
          setFetchError(null);
        }
      } catch (err) {
        if (mounted) {
          console.error('Failed to fetch profiles:', err);
          setFetchError('Failed to load profiles');
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    fetchProfiles();

    return () => {
      mounted = false;
    };
  }, []);

  /**
   * Handles selection change from the Select component.
   * Maps "__none__" sentinel value to empty string.
   */
  const handleValueChange = (newValue: string) => {
    onChange(newValue === '__none__' ? '' : newValue);
  };

  // Map empty string to sentinel value for Radix Select
  const selectValue = value === '' ? '__none__' : value;

  return (
    <div className="relative">
      <Label
        htmlFor={id}
        className="absolute -top-2 left-3 bg-card px-1 text-[11px] font-heading uppercase tracking-wider text-muted-foreground z-10"
      >
        Profile
      </Label>
      <Select
        value={selectValue}
        onValueChange={handleValueChange}
        disabled={disabled || isLoading}
      >
        <SelectTrigger
          id={id}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(
            'mt-1 w-full font-mono text-sm bg-background border-input',
            'focus:border-primary focus:ring-primary/15 focus:ring-[3px]',
            error && 'border-destructive'
          )}
        >
          <SelectValue
            placeholder={isLoading ? 'Loading...' : fetchError || 'Select profile'}
          />
        </SelectTrigger>
        <SelectContent>
          {/* None option */}
          <SelectItem value="__none__">
            <span className="text-muted-foreground">None (use server default)</span>
          </SelectItem>
          {profiles.length > 0 && <SelectSeparator />}

          {/* Profile options */}
          {profiles.map((profile) => (
            <SelectItem key={profile.id} value={profile.id}>
              <div className="flex items-center gap-2">
                <span>{profile.id}</span>
                {profile.is_active && (
                  <span className="text-status-completed text-xs">(active)</span>
                )}
                <span className="text-muted-foreground text-xs">
                  {profile.tracker}
                </span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
