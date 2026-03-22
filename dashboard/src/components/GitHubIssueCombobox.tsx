/**
 * @fileoverview Combobox for selecting GitHub issues from a profile's repository.
 *
 * Uses shadcn/ui Popover + Command for a searchable dropdown.
 * Fetches issues via GET /api/github/issues and supports debounced search.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronsUpDown, Check, X } from 'lucide-react';

import { api } from '@/api/client';
import type { GitHubIssueSummary } from '@/types';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface GitHubIssueComboboxProps {
  id?: string;
  profile: string;
  onSelect: (issue: GitHubIssueSummary) => void;
  value?: { number: number; title: string } | null;
  onClear?: () => void;
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 30) return `${diffDays}d ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

const _MAX_TRIGGER_TITLE_LENGTH = 40;

function truncateTitle(title: string): string {
  if (title.length <= _MAX_TRIGGER_TITLE_LENGTH) return title;
  return title.slice(0, _MAX_TRIGGER_TITLE_LENGTH) + '...';
}

export function GitHubIssueCombobox({ id, profile, onSelect, value, onClear }: GitHubIssueComboboxProps) {
  const [open, setOpen] = useState(false);
  const [issues, setIssues] = useState<GitHubIssueSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();

  const fetchIssues = useCallback(
    async (query?: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      try {
        const response = await api.getGitHubIssues(
          profile,
          query || undefined,
          controller.signal,
        );
        setIssues(response.issues);
      } catch {
        if (!controller.signal.aborted) {
          setIssues([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [profile],
  );

  // Fetch on mount and when profile changes
  useEffect(() => {
    fetchIssues();
    return () => {
      abortRef.current?.abort();
      clearTimeout(debounceRef.current);
    };
  }, [fetchIssues]);

  const handleSearchChange = (val: string) => {
    setSearch(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchIssues(val);
    }, 300);
  };

  const handleSelect = (issue: GitHubIssueSummary) => {
    onSelect(issue);
    setOpen(false);
    setSearch('');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label="Select issue"
          className="w-full justify-between"
        >
          {value ? (
            <span className="truncate">
              #{value.number} — {truncateTitle(value.title)}
            </span>
          ) : (
            'Select GitHub issue...'
          )}
          <span className="ml-2 flex items-center gap-1 shrink-0">
            {value && onClear && (
              <span
                role="button"
                aria-label="Clear issue selection"
                data-testid="clear-issue-btn"
                className="h-4 w-4 opacity-70 hover:opacity-100 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  onClear();
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation();
                    onClear();
                  }
                }}
                tabIndex={0}
              >
                <X className="h-4 w-4" />
              </span>
            )}
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search issues..."
            value={search}
            onValueChange={handleSearchChange}
          />
          <CommandList>
            {loading ? (
              <div className="p-2 space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : (
              <>
                <CommandEmpty>No issues found</CommandEmpty>
                <CommandGroup>
                  {issues.map((issue) => (
                    <CommandItem
                      key={issue.number}
                      value={String(issue.number)}
                      onSelect={() => handleSelect(issue)}
                      className="flex items-center gap-2"
                    >
                      <Check
                        className={cn(
                          'h-4 w-4 shrink-0',
                          issue.number === value?.number ? 'opacity-100' : 'opacity-0',
                        )}
                      />
                      <span className="text-muted-foreground text-xs font-mono shrink-0">
                        #{issue.number}
                      </span>
                      <span className="truncate">{issue.title}</span>
                      <div className="ml-auto flex items-center gap-2 shrink-0">
                        {issue.labels.map((label) => (
                          <Badge
                            key={label.name}
                            variant="outline"
                            className="text-xs px-1 py-0"
                            style={{
                              borderColor: `#${label.color}`,
                              color: `#${label.color}`,
                            }}
                          >
                            {label.name}
                          </Badge>
                        ))}
                        {issue.assignee && (
                          <span className="text-muted-foreground text-xs">
                            {issue.assignee}
                          </span>
                        )}
                        <span className="text-muted-foreground text-xs">
                          {formatRelativeTime(issue.created_at)}
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
