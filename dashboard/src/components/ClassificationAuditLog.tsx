/**
 * @fileoverview Classification audit log table for PR auto-fix decisions.
 * Shows per-comment classification records with expandable body text.
 */
import { useEffect, useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ChevronRight } from 'lucide-react';
import { api } from '@/api/client';
import { DataTable } from '@/components/ui/data-table';
import { DataTableColumnHeader } from '@/components/ui/data-table-column-header';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ClassificationRecord } from '@/types';

interface ClassificationAuditLogProps {
  /** Current date preset for filtering. */
  preset: string;
}

/**
 * Format an ISO date string for display.
 */
function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Truncate a prompt hash for display.
 */
function truncateHash(hash: string | null): string {
  if (!hash) return '--';
  return hash.slice(0, 8);
}

/**
 * Classification audit log with expandable rows for comment body text.
 * Fetches classification data on mount and when preset changes.
 */
export function ClassificationAuditLog({ preset }: ClassificationAuditLogProps) {
  const [records, setRecords] = useState<ClassificationRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    api
      .getClassifications({ preset, limit: 50 })
      .then((data) => {
        if (!cancelled) {
          setRecords(data.classifications);
          setTotal(data.total);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [preset]);

  const columns: ColumnDef<ClassificationRecord>[] = useMemo(
    () => [
      {
        id: 'expander',
        header: () => null,
        cell: ({ row }) => (
          <button
            onClick={(e) => {
              e.stopPropagation();
              row.toggleExpanded();
            }}
            className="p-1 hover:bg-muted rounded transition-colors"
            aria-label={row.getIsExpanded() ? 'Collapse row' : 'Expand row'}
          >
            <ChevronRight
              className={cn(
                'size-4 text-muted-foreground transition-transform',
                row.getIsExpanded() && 'rotate-90'
              )}
            />
          </button>
        ),
        size: 32,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Date" align="left" />
        ),
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs tabular-nums">
            {formatDate(row.getValue('created_at'))}
          </span>
        ),
      },
      {
        accessorKey: 'category',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Category" align="left" />
        ),
        cell: ({ row }) => (
          <Badge variant="outline" className="text-xs font-mono">
            {row.getValue('category')}
          </Badge>
        ),
      },
      {
        accessorKey: 'confidence',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Confidence" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right tabular-nums text-muted-foreground">
            {((row.getValue('confidence') as number) * 100).toFixed(0)}%
          </div>
        ),
      },
      {
        accessorKey: 'actionable',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Actionable" align="center" />
        ),
        cell: ({ row }) => {
          const actionable = row.getValue('actionable') as boolean;
          return (
            <div className="text-center">
              <Badge
                variant="outline"
                className={cn(
                  'text-xs',
                  actionable
                    ? 'border-green-500/50 text-green-400'
                    : 'border-muted-foreground/30 text-muted-foreground'
                )}
              >
                {actionable ? 'Yes' : 'No'}
              </Badge>
            </div>
          );
        },
      },
      {
        accessorKey: 'aggressiveness_level',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Aggressiveness" align="left" />
        ),
        cell: ({ row }) => (
          <span className="text-sm">{row.getValue('aggressiveness_level')}</span>
        ),
      },
      {
        accessorKey: 'prompt_hash',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Prompt Hash" align="left" />
        ),
        cell: ({ row }) => (
          <span className="font-mono text-xs text-muted-foreground">
            {truncateHash(row.getValue('prompt_hash'))}
          </span>
        ),
      },
    ],
    []
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        Loading classifications...
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        No classification records found for this period.
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
          CLASSIFICATION AUDIT LOG
        </h3>
        <span className="text-xs text-muted-foreground">
          Showing {records.length} of {total}
        </span>
      </div>
      <DataTable
        columns={columns}
        data={records}
        renderSubComponent={({ row }) => (
          <div className="px-10 py-3 bg-muted/30 text-sm text-muted-foreground">
            <p className="font-mono text-xs whitespace-pre-wrap break-words">
              {row.original.body_snippet}
            </p>
          </div>
        )}
      />
    </div>
  );
}
