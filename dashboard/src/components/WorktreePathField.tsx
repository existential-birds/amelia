/**
 * @fileoverview Enhanced Worktree Path field with validation and smart selection.
 *
 * A "mission control" styled path selector that prevents engineers from
 * accidentally targeting wrong directories by providing:
 * - Real-time path validation with git repo detection
 * - Visual status indicators (valid, warning, error)
 * - Recent paths dropdown for quick selection
 * - Breadcrumb-style path display for easy scanning
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Check,
  AlertTriangle,
  XCircle,
  ChevronDown,
  GitBranch,
  Folder,
  Clock,
  MapPin,
  Loader2,
} from 'lucide-react';
import { api, ApiError } from '@/api/client';
import type { PathValidationResponse } from '@/types';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

/**
 * A recent path entry with metadata.
 */
interface RecentPath {
  /** Full path string. */
  path: string;
  /** Display label (repo name or folder). */
  label: string;
  /** When this path was last used. */
  lastUsed?: Date;
  /** Whether this is the server's working_dir. */
  isServerDefault?: boolean;
}

interface WorktreePathFieldProps {
  /** Current path value. */
  value: string;
  /** Callback when path changes. */
  onChange: (value: string) => void;
  /** Field error message from form validation. */
  error?: string;
  /** Whether the field is disabled. */
  disabled?: boolean;
  /** Server working_dir for default suggestion. */
  serverWorkingDir?: string;
  /** Recent worktree paths from workflow history. */
  recentPaths?: string[];
  /** ID for accessibility. */
  id?: string;
}

type ValidationStatus = 'idle' | 'validating' | 'valid' | 'warning' | 'error';

/**
 * Status icons mapped by validation state.
 * Defined outside component to avoid re-creation on each render.
 */
const statusIcons = {
  validating: <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />,
  valid: <Check className="h-4 w-4 text-status-completed" />,
  warning: <AlertTriangle className="h-4 w-4 text-primary" />,
  error: <XCircle className="h-4 w-4 text-destructive" />,
  idle: <Folder className="h-4 w-4 text-muted-foreground" />,
} as const;

/**
 * Extracts the repo/folder name from a path.
 */
function getPathLabel(path: string): string {
  const segments = path.split('/').filter(Boolean);
  return segments[segments.length - 1] || path;
}

/**
 * Splits a path into displayable segments.
 */
function getPathSegments(path: string): string[] {
  if (!path) return [];
  // For absolute paths, keep the leading slash context
  const segments = path.split('/').filter(Boolean);
  // Show last 3 segments max for readability
  if (segments.length > 3) {
    return ['...', ...segments.slice(-3)];
  }
  return segments;
}

/**
 * Enhanced Worktree Path field component.
 *
 * Features:
 * - Real-time validation with debounce
 * - Git repository detection and branch display
 * - Visual status indicators with color-coded states
 * - Recent paths dropdown for quick selection
 * - Breadcrumb-style path segments for scanning
 */
export function WorktreePathField({
  value,
  onChange,
  error,
  disabled,
  serverWorkingDir,
  recentPaths = [],
  id = 'worktree_path',
}: WorktreePathFieldProps) {
  const [status, setStatus] = useState<ValidationStatus>('idle');
  const [validation, setValidation] = useState<PathValidationResponse | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const inputRef = useRef<HTMLInputElement>(null);

  // Build the list of path suggestions
  const suggestions: RecentPath[] = [];

  // Add server working_dir as primary suggestion
  if (serverWorkingDir) {
    suggestions.push({
      path: serverWorkingDir,
      label: getPathLabel(serverWorkingDir),
      isServerDefault: true,
    });
  }

  // Add unique recent paths (excluding server default)
  const seen = new Set(suggestions.map((s) => s.path));
  for (const path of recentPaths) {
    if (!seen.has(path)) {
      suggestions.push({
        path,
        label: getPathLabel(path),
      });
      seen.add(path);
    }
  }

  /**
   * Validates the path against the server.
   * @param pathToValidate - The path to validate.
   * @param signal - Optional AbortSignal to cancel the request on unmount.
   */
  const validatePath = useCallback(async (pathToValidate: string, signal?: AbortSignal) => {
    if (!pathToValidate || !pathToValidate.startsWith('/')) {
      setStatus('idle');
      setValidation(null);
      return;
    }

    setStatus('validating');

    try {
      const result = await api.validatePath(pathToValidate, signal);
      // Check if aborted before updating state
      if (signal?.aborted) return;
      setValidation(result);

      if (!result.exists) {
        setStatus('error');
      } else if (!result.is_git_repo) {
        setStatus('warning');
      } else {
        setStatus('valid');
      }
    } catch (err) {
      // Don't update state if the request was aborted
      if (signal?.aborted) return;
      // API endpoint might not exist yet - fall back to basic validation
      if (err instanceof ApiError && err.status === 404) {
        // Endpoint doesn't exist, show as unvalidated
        setStatus('idle');
        setValidation(null);
      } else {
        setStatus('error');
        setValidation({
          exists: false,
          is_git_repo: false,
          message: 'Could not validate path',
        });
      }
    }
  }, []);

  // Debounced validation on value change with cleanup to prevent memory leaks
  useEffect(() => {
    const controller = new AbortController();

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      validatePath(value, controller.signal);
    }, 500);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      controller.abort();
    };
  }, [value, validatePath]);

  /**
   * Handles selecting a path from the dropdown.
   */
  const handleSelectPath = (path: string) => {
    onChange(path);
    setIsDropdownOpen(false);
    // Validation handled by useEffect with proper AbortSignal
  };

  // Get the status icon from the pre-defined lookup
  const statusIcon = statusIcons[status];

  /**
   * Gets status-specific border color class.
   */
  const getStatusBorderClass = () => {
    switch (status) {
      case 'valid':
        return 'border-status-completed/50 focus-within:border-status-completed';
      case 'warning':
        return 'border-primary/50 focus-within:border-primary';
      case 'error':
        return 'border-destructive/50 focus-within:border-destructive';
      default:
        return 'border-input focus-within:border-primary';
    }
  };

  const pathSegments = getPathSegments(value);
  const hasError = !!error || status === 'error';

  return (
    <div className="space-y-2">
      {/* Field Label with Enhanced Styling */}
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="text-xs font-heading uppercase tracking-wider text-muted-foreground flex items-center gap-2"
        >
          <MapPin className="h-3 w-3" />
          Worktree Path
          <span className="text-primary">*</span>
        </Label>

        {/* Quick Select Dropdown */}
        {suggestions.length > 0 && (
          <DropdownMenu open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs font-heading uppercase tracking-wide text-muted-foreground hover:text-foreground"
                disabled={disabled}
              >
                <Clock className="h-3 w-3 mr-1" />
                Recent
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80">
              <DropdownMenuLabel className="text-xs font-heading uppercase tracking-wider text-muted-foreground">
                Select Worktree
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {suggestions.map((suggestion) => (
                <DropdownMenuItem
                  key={suggestion.path}
                  onClick={() => handleSelectPath(suggestion.path)}
                  className={cn(
                    'flex flex-col items-start gap-0.5 cursor-pointer',
                    suggestion.isServerDefault && 'bg-primary/5'
                  )}
                >
                  <div className="flex items-center gap-2 w-full">
                    {suggestion.isServerDefault ? (
                      <MapPin className="h-3 w-3 text-primary shrink-0" />
                    ) : (
                      <Folder className="h-3 w-3 text-muted-foreground shrink-0" />
                    )}
                    <span className="font-medium truncate">{suggestion.label}</span>
                    {suggestion.isServerDefault && (
                      <span className="ml-auto text-[10px] font-heading uppercase tracking-wider text-primary">
                        Server Default
                      </span>
                    )}
                    {!suggestion.isServerDefault &&
                      suggestion === suggestions.find((s) => !s.isServerDefault) && (
                        <span className="ml-auto text-[10px] font-heading uppercase tracking-wider text-muted-foreground">
                          Last Used
                        </span>
                      )}
                  </div>
                  <span className="text-xs font-mono text-muted-foreground truncate w-full pl-5">
                    {suggestion.path}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Path Breadcrumbs Display (when path exists) */}
      {pathSegments.length > 0 && (
        <div className="flex items-center gap-1 text-[10px] font-mono overflow-hidden">
          {pathSegments.map((segment, index) => (
            <span key={`segment-${index}-${segment}`} className="flex items-center">
              {index > 0 && (
                <span className="text-muted-foreground/50 mx-0.5">/</span>
              )}
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded',
                  index === pathSegments.length - 1
                    ? 'bg-primary/20 text-primary font-medium'
                    : 'text-muted-foreground'
                )}
              >
                {segment}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Enhanced Input Container */}
      <div
        className={cn(
          'relative rounded-lg border-2 transition-all duration-normal',
          'bg-background/50',
          getStatusBorderClass(),
          hasError && 'border-destructive',
          disabled && 'opacity-50'
        )}
      >
        {/* Actual Input */}
        <Input
          ref={inputRef}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="/Users/me/projects/my-repo"
          disabled={disabled}
          aria-invalid={hasError}
          aria-describedby={hasError ? `${id}-error` : validation ? `${id}-status` : undefined}
          className={cn(
            'border-0 bg-transparent font-mono text-sm',
            'focus-visible:ring-0 focus-visible:ring-offset-0',
            'placeholder:text-muted-foreground/50'
          )}
        />

        {/* Status Indicator */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          {statusIcon}
        </div>
      </div>

      {/* Validation Status Message */}
      {validation && status !== 'idle' && (
        <div
          id={`${id}-status`}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-md text-xs',
            'border',
            status === 'valid' && 'bg-status-completed/10 border-status-completed/30 text-status-completed',
            status === 'warning' && 'bg-primary/10 border-primary/30 text-primary',
            status === 'error' && 'bg-destructive/10 border-destructive/30 text-destructive'
          )}
        >
          {statusIcon}
          <span className="flex-1">{validation.message}</span>

          {/* Git info when valid */}
          {status === 'valid' && validation.branch && (
            <span className="flex items-center gap-1 font-mono text-[10px] bg-background/50 px-2 py-0.5 rounded">
              <GitBranch className="h-3 w-3" />
              {validation.branch}
              {validation.has_changes && (
                <span className="text-primary ml-1" title="Uncommitted changes">•</span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Form Error */}
      {error && (
        <p id={`${id}-error`} className="text-xs text-destructive flex items-center gap-1">
          <XCircle className="h-3 w-3" />
          {error}
        </p>
      )}

      {/* Help Text */}
      {!validation && !error && (
        <p className="text-[10px] text-muted-foreground/70 font-mono">
          Absolute path to git repository where agents will operate
        </p>
      )}
    </div>
  );
}
