/**
 * @fileoverview Knowledge Library page with Search and Documents tabs.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { format } from 'date-fns';
import { Library, Upload, Search, FileText, Trash2, AlertCircle, Loader2, Tag } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { DataTableColumnHeader } from '@/components/ui/data-table-column-header';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from '@/components/ui/empty';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { api, ApiError } from '@/api/client';
import * as Toast from '@/components/Toast';
import { logger } from '@/lib/logger';
import type { KnowledgeLoaderData } from '@/loaders/knowledge';
import type { KnowledgeDocument, SearchResult, DocumentStatus } from '@/types/knowledge';

/**
 * Tag color palette - organic, forest-inspired colors.
 * Each tag gets a deterministic color based on its name hash.
 */
const TAG_COLORS = [
  // Moss & lichen greens
  { bg: 'oklch(45% 0.08 140 / 0.15)', border: 'oklch(55% 0.10 140 / 0.3)', text: 'oklch(75% 0.12 140)' },
  // Amber & honey
  { bg: 'oklch(70% 0.12 80 / 0.15)', border: 'oklch(75% 0.14 80 / 0.3)', text: 'oklch(85% 0.14 80)' },
  // Sage & eucalyptus
  { bg: 'oklch(60% 0.08 160 / 0.15)', border: 'oklch(65% 0.10 160 / 0.3)', text: 'oklch(78% 0.10 160)' },
  // Lavender & twilight
  { bg: 'oklch(60% 0.10 280 / 0.15)', border: 'oklch(65% 0.12 280 / 0.3)', text: 'oklch(75% 0.12 280)' },
  // Coral & sunset
  { bg: 'oklch(65% 0.12 40 / 0.15)', border: 'oklch(70% 0.14 40 / 0.3)', text: 'oklch(80% 0.14 40)' },
  // Mint & frost
  { bg: 'oklch(65% 0.08 180 / 0.15)', border: 'oklch(70% 0.10 180 / 0.3)', text: 'oklch(80% 0.10 180)' },
  // Sky & dawn
  { bg: 'oklch(60% 0.10 230 / 0.15)', border: 'oklch(65% 0.12 230 / 0.3)', text: 'oklch(75% 0.12 230)' },
  // Rose & dusk
  { bg: 'oklch(60% 0.12 350 / 0.15)', border: 'oklch(65% 0.14 350 / 0.3)', text: 'oklch(75% 0.14 350)' },
] as const;

/**
 * Simple string hash function for deterministic color assignment.
 */
function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

/**
 * Get a deterministic color for a tag based on its name.
 */
function getTagColor(tag: string) {
  const index = hashString(tag) % TAG_COLORS.length;
  return TAG_COLORS[index]!; // Safe: modulo ensures valid index
}

/**
 * TagBadge component - a single tag with organic color styling.
 */
function TagBadge({ tag, className }: { tag: string; className?: string }) {
  const color = getTagColor(tag);
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium border transition-colors',
        className
      )}
      style={{
        backgroundColor: color.bg,
        borderColor: color.border,
        color: color.text,
      }}
    >
      {tag}
    </span>
  );
}

/**
 * TagStack component - displays tags as layered, stacked cards.
 * Shows first 3 tags clearly, hints at more with visual depth.
 */
function TagStack({ tags }: { tags: string[] }) {
  const [isOpen, setIsOpen] = useState(false);
  const visibleCount = 3;
  const hasMore = tags.length > visibleCount;
  const visibleTags = tags.slice(0, visibleCount);
  const hiddenCount = tags.length - visibleCount;

  if (tags.length === 0) {
    return <span className="text-muted-foreground text-xs">No tags</span>;
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button
          className="flex items-center gap-1.5 flex-wrap"
          onClick={(e) => e.stopPropagation()}
        >
          {visibleTags.map((tag) => (
            <TagBadge key={tag} tag={tag} />
          ))}
          {hasMore && (
            <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-secondary/50 text-secondary-foreground border border-border">
              +{hiddenCount}
            </span>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent
        className="w-96 p-4"
        align="start"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b">
            <Tag className="size-4 text-muted-foreground" />
            <h4 className="font-semibold text-sm">Document Tags</h4>
            <span className="text-xs text-muted-foreground ml-auto">
              {tags.length} total
            </span>
          </div>

          <div className="flex flex-wrap gap-2 max-h-60 overflow-y-auto">
            {tags.map((tag) => (
              <TagBadge key={tag} tag={tag} />
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Status badge variant mapping.
 */
function statusBadge(status: DocumentStatus, error?: string | null) {
  switch (status) {
    case 'pending':
      return <Badge variant="secondary">Pending</Badge>;
    case 'processing':
      return (
        <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 gap-1">
          <Loader2 className="size-3 animate-spin" />
          Processing
        </Badge>
      );
    case 'ready':
      return <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">Ready</Badge>;
    case 'failed':
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="destructive" className="cursor-help gap-1">
              <AlertCircle className="size-3" />
              Failed
            </Badge>
          </TooltipTrigger>
          <TooltipContent>{error || 'Unknown error'}</TooltipContent>
        </Tooltip>
      );
  }
}

/**
 * Document table columns for the Documents tab.
 */
function getDocumentColumns(onDelete: (id: string) => void): ColumnDef<KnowledgeDocument>[] {
  return [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => (
        <div className="flex items-center gap-3 py-1">
          <div className="size-9 shrink-0 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
            <FileText className="size-4 text-primary" />
          </div>
          <span className="truncate font-semibold text-sm">{row.original.name}</span>
        </div>
      ),
    },
    {
      accessorKey: 'tags',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Tags" />,
      cell: ({ row }) => <TagStack tags={row.original.tags} />,
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => statusBadge(row.original.status, row.original.error),
    },
    {
      accessorKey: 'chunk_count',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Chunks" align="right" />,
      cell: ({ row }) => (
        <div className="text-right font-mono text-sm">{row.original.chunk_count}</div>
      ),
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Uploaded" />,
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">
          {format(new Date(row.original.created_at), 'MMM d, yyyy')}
        </span>
      ),
    },
    {
      id: 'actions',
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="icon-sm"
          data-testid="delete-document"
          aria-label="Delete document"
          className="text-destructive hover:text-destructive-foreground hover:bg-destructive/10"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(row.original.id);
          }}
        >
          <Trash2 className="size-4" />
        </Button>
      ),
    },
  ];
}

export default function KnowledgePage() {
  const loaderData = useLoaderData() as KnowledgeLoaderData;
  const revalidator = useRevalidator();

  // Local state: merge loader data with real-time updates from WebSocket
  const [documents, setDocuments] = useState<KnowledgeDocument[]>(loaderData.documents);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState('search');
  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);

  // Upload dialog state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadTags, setUploadTags] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const executeSearch = useCallback(
    async (query: string) => {
      // Cancel any in-flight search request
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsSearching(true);
      setSearchError(null);

      try {
        const results = await api.searchKnowledge(query, 5, undefined, controller.signal);
        setSearchResults(results);
      } catch (error) {
        if (
          (error instanceof DOMException && error.name === 'AbortError') ||
          (error instanceof ApiError && error.code === 'ABORTED')
        ) {
          return; // Silently ignore aborted requests
        }
        setSearchError(error instanceof Error ? error.message : 'Search failed');
      } finally {
        // Only clear loading state if this request is still the current one
        if (abortControllerRef.current === controller) {
          setIsSearching(false);
        }
      }
    },
    [] // Stable: only uses refs and stable state setters
  );

  const handleSearch = useCallback(async () => {
    const query = searchQuery.trim();
    if (!query) return;

    // Clear any pending debounced search
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    await executeSearch(query);
  }, [searchQuery, executeSearch]);

  const handleSearchKeyDown = useCallback(
    async (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        const query = searchQuery.trim();
        if (!query) return;

        // Clear any pending debounced search
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current);
          debounceTimerRef.current = null;
        }

        await executeSearch(query);
      }
    },
    [searchQuery, executeSearch]
  );

  const handleUpload = useCallback(async () => {
    if (!uploadFile || !uploadName.trim()) return;

    setIsUploading(true);
    try {
      const tags = uploadTags
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);
      await api.uploadKnowledgeDocument(uploadFile, uploadName.trim(), tags);
      setUploadOpen(false);
      setUploadFile(null);
      setUploadName('');
      setUploadTags('');
      revalidator.revalidate();
    } catch (error) {
      logger.error('Upload failed', error);
      Toast.error(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  }, [uploadFile, uploadName, uploadTags, revalidator]);

  const handleDelete = useCallback(
    async (documentId: string) => {
      try {
        await api.deleteKnowledgeDocument(documentId);
        revalidator.revalidate();
      } catch (error) {
        logger.error('Delete failed', error);
        Toast.error(error instanceof Error ? error.message : 'Delete failed');
      }
    },
    [revalidator]
  );

  const columns = getDocumentColumns(handleDelete);

  // Sync local state when loader data changes
  useEffect(() => {
    setDocuments(loaderData.documents);
  }, [loaderData.documents]);

  // Listen for knowledge domain events from WebSocket
  useEffect(() => {
    const handleKnowledgeEvent = (event: Event) => {
      const customEvent = event as CustomEvent<import('../types').WorkflowEvent>;
      const { domain, workflow_id: documentId, event_type, data } = customEvent.detail;

      // Only handle knowledge domain events
      if (domain !== 'knowledge') return;

      switch (event_type) {
        case 'document_ingestion_started':
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === documentId ? { ...doc, status: 'processing' as const } : doc
            )
          );
          break;

        case 'document_ingestion_progress':
          // Could update progress percentage here if needed
          break;

        case 'document_ingestion_completed':
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === documentId
                ? {
                    ...doc,
                    status: 'ready' as const,
                    chunk_count: (data?.chunk_count as number) || doc.chunk_count,
                    token_count: (data?.token_count as number) || doc.token_count,
                    error: null,
                  }
                : doc
            )
          );
          break;

        case 'document_ingestion_failed':
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === documentId
                ? {
                    ...doc,
                    status: 'failed' as const,
                    error: (data?.error as string) || 'Ingestion failed',
                  }
                : doc
            )
          );
          break;
      }
    };

    window.addEventListener('workflow-event', handleKnowledgeEvent);
    return () => {
      window.removeEventListener('workflow-event', handleKnowledgeEvent);
    };
  }, []);

  // Focus search input when switching to search tab
  useEffect(() => {
    if (activeTab === 'search') {
      searchInputRef.current?.focus();
    }
  }, [activeTab]);

  // Cleanup: abort pending search and clear debounce timer on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return (
    <div className="flex flex-col h-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>KNOWLEDGE</PageHeader.Label>
          <PageHeader.Title>Library</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Label>DOCUMENTS</PageHeader.Label>
          <PageHeader.Value>{documents.length}</PageHeader.Value>
        </PageHeader.Center>
        <PageHeader.Right>
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="size-4 mr-1.5" />
            Upload
          </Button>
        </PageHeader.Right>
      </PageHeader>

      <Tabs defaultValue="search" className="flex flex-col flex-1 min-h-0" onValueChange={setActiveTab}>
        <div className="px-6 pt-4">
          <TabsList>
            <TabsTrigger value="search">
              <Search className="size-4 mr-1.5" />
              Search
            </TabsTrigger>
            <TabsTrigger value="documents">
              <FileText className="size-4 mr-1.5" />
              Documents
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Search Tab */}
        <TabsContent value="search" className="flex-1 min-h-0 p-6 pt-4">
          <div className="flex flex-col gap-4 h-full">
            {/* Search input */}
            <div className="flex gap-2">
              <Input
                ref={searchInputRef}
                placeholder="Search documentation..."
                value={searchQuery}
                onChange={(e) => {
                  const newValue = e.target.value;
                  setSearchQuery(newValue);

                  // Debounce: clear any pending search and abort in-flight requests
                  if (debounceTimerRef.current) {
                    clearTimeout(debounceTimerRef.current);
                  }
                  abortControllerRef.current?.abort();

                  // Debounce delay of 300ms
                  const query = newValue.trim();
                  if (query) {
                    debounceTimerRef.current = setTimeout(() => {
                      if (!isMountedRef.current) return;
                      executeSearch(query).catch((error) => {
                        logger.error('Debounced search failed', error);
                      });
                      debounceTimerRef.current = null;
                    }, 300);
                  }
                }}
                onKeyDown={handleSearchKeyDown}
                className="flex-1"
              />
              <Button onClick={handleSearch} disabled={isSearching || !searchQuery.trim()}>
                <Search className="size-4 mr-1.5" />
                {isSearching ? 'Searching...' : 'Search'}
              </Button>
            </div>

            {/* Search results */}
            {searchError ? (
              <Empty className="flex-1">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <AlertCircle />
                  </EmptyMedia>
                  <EmptyTitle>Search failed</EmptyTitle>
                  <EmptyDescription>{searchError}</EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : searchResults === null ? (
              <Empty className="flex-1">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Search />
                  </EmptyMedia>
                  <EmptyTitle>Search your knowledge library</EmptyTitle>
                  <EmptyDescription>
                    Enter a query to find relevant documentation chunks using semantic search.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : searchResults.length === 0 ? (
              <Empty className="flex-1">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Search />
                  </EmptyMedia>
                  <EmptyTitle>No results found</EmptyTitle>
                  <EmptyDescription>
                    Try a different query or upload more documents.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="flex flex-col gap-3 overflow-auto">
                {searchResults.map((result, index) => (
                  <Card
                    key={result.chunk_id}
                    className="hover:shadow-lg hover:shadow-primary/5 transition-all duration-200 hover:border-primary/30"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="text-xs text-muted-foreground font-medium">
                          {result.heading_path.length > 0 ? result.heading_path.join(' › ') : 'Document root'}
                        </div>
                        <div className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/15 border border-primary/30">
                          <div className="size-1.5 rounded-full bg-primary animate-pulse" />
                          <span className="text-xs font-mono font-semibold text-primary">
                            {(result.similarity * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <p className="text-sm mb-4 whitespace-pre-wrap break-words leading-relaxed">{result.content}</p>
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                          <FileText className="size-3 shrink-0" />
                          <span className="shrink-0">{result.document_name}</span>
                          {result.tags.map((tag) => (
                            <TagBadge key={tag} tag={tag} />
                          ))}
                        </div>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {result.token_count} tokens
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Documents Tab */}
        <TabsContent value="documents" className="flex-1 min-h-0 p-6 pt-4">
          {documents.length === 0 ? (
            <Empty className="h-full">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Library />
                </EmptyMedia>
                <EmptyTitle>No documents</EmptyTitle>
                <EmptyDescription>
                  Upload PDF or Markdown files to build your knowledge library.
                </EmptyDescription>
              </EmptyHeader>
              <Button variant="outline" onClick={() => setUploadOpen(true)}>
                <Upload className="size-4 mr-1.5" />
                Upload Document
              </Button>
            </Empty>
          ) : (
            <DataTable columns={columns} data={documents} />
          )}
        </TabsContent>
      </Tabs>

      {/* Upload Dialog */}
      <Dialog
        open={uploadOpen}
        onOpenChange={(open) => {
          setUploadOpen(open);
          if (!open) {
            setUploadFile(null);
            setUploadName('');
            setUploadTags('');
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a PDF or Markdown file to add to your knowledge library.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="file">File</Label>
              <Input
                id="file"
                type="file"
                accept=".pdf,.md"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  setUploadFile(file);
                  if (file && !uploadName) {
                    setUploadName(file.name.replace(/\.(pdf|md)$/i, ''));
                  }
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                placeholder="Document name"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="tags">Tags</Label>
              <Input
                id="tags"
                placeholder="react, hooks, frontend (comma-separated)"
                value={uploadTags}
                onChange={(e) => setUploadTags(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={isUploading || !uploadFile || !uploadName.trim()}
            >
              {isUploading ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
