/**
 * @fileoverview Knowledge Library page with Search and Documents tabs.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { format } from 'date-fns';
import { Library, Upload, Search, FileText, Trash2, AlertCircle } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { api } from '@/api/client';
import * as Toast from '@/components/Toast';
import { logger } from '@/lib/logger';
import type { KnowledgeLoaderData } from '@/loaders/knowledge';
import type { KnowledgeDocument, SearchResult, DocumentStatus } from '@/types/knowledge';

/**
 * Status badge variant mapping.
 */
function statusBadge(status: DocumentStatus, error?: string | null) {
  switch (status) {
    case 'pending':
      return <Badge variant="secondary">Pending</Badge>;
    case 'processing':
      return <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30">Processing</Badge>;
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
        <div className="flex items-center gap-2">
          <FileText className="size-4 text-muted-foreground shrink-0" />
          <span className="truncate font-medium">{row.original.name}</span>
        </div>
      ),
    },
    {
      accessorKey: 'tags',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Tags" />,
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {row.original.tags.map((tag, index) => (
            <Badge key={`${tag}-${index}`} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>
      ),
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
          onClick={(e) => {
            e.stopPropagation();
            onDelete(row.original.id);
          }}
        >
          <Trash2 className="size-4 text-muted-foreground" />
        </Button>
      ),
    },
  ];
}

export default function KnowledgePage() {
  const { documents } = useLoaderData() as KnowledgeLoaderData;
  const revalidator = useRevalidator();

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState('search');
  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Upload dialog state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadTags, setUploadTags] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const executeSearch = useCallback(async (query: string) => {
    // Cancel any in-flight search request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsSearching(true);
    setSearchError(null);

    try {
      const results = await api.searchKnowledge(query, 5, undefined, abortControllerRef.current.signal);
      setSearchResults(results);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // Silently ignore aborted requests
      }
      setSearchError(error instanceof Error ? error.message : 'Search failed');
    } finally {
      setIsSearching(false);
    }
  }, []);

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
        .filter(Boolean);
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

  // Focus search input when switching to search tab
  useEffect(() => {
    if (activeTab === 'search') {
      searchInputRef.current?.focus();
    }
  }, [activeTab]);

  // Cleanup: abort pending search and clear debounce timer on unmount
  useEffect(() => {
    return () => {
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
                      debounceTimerRef.current = null;
                      void executeSearch(query);
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
                {searchResults.map((result) => (
                  <Card key={result.chunk_id}>
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="text-xs text-muted-foreground">
                          {result.heading_path.length > 0 ? result.heading_path.join(' > ') : 'Document root'}
                        </div>
                        <Badge variant="outline" className="shrink-0 font-mono text-xs">
                          {(result.similarity * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <p className="text-sm mb-3 whitespace-pre-wrap break-words">{result.content}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <FileText className="size-3" />
                          <span>{result.document_name}</span>
                          {result.tags.map((tag, index) => (
                            <Badge key={`${tag}-${index}`} variant="outline" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                        <span className="text-xs text-muted-foreground">
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
