# Failure Report: TC-03

## Test Failure: TC-03 - Search for uploaded document content and verify results

### What Failed

**Test:** Search for uploaded document content and verify results

**Expected:**
- Search results appear as cards below the search input
- At least one result card shows content from the uploaded document
- Each result card displays:
  - A heading path or "Document root"
  - A similarity percentage badge
  - The chunk text content
  - The document name matching what was uploaded
  - Tags ("testing", "sample") shown as badges
  - Token count
- The document name in results matches the document uploaded in TC-01

**Actual:**
- API returned empty array: `[]`
- Search executed with query: "semantic search"
- HTTP 200 status (no error), but zero results
- Documents exist in database with status "ready"
- Chunks exist with embeddings (10 total chunks, both documents have 6 and 4 chunks respectively)
- Search UI likely showing "No results found" empty state

### Root Cause

**Critical finding:** The dev server was started BEFORE the pgvector codec registration was added to the codebase.

Investigation revealed:
1. Running dev server PIDs: 86523, 86653, 87093 (started hours before test)
2. This PR added `await register_vector(conn)` to `Database._init_connection()` in `amelia/server/database/connection.py`
3. The pre-existing server doesn't have pgvector codec registered, causing vector similarity operations (`<=>`) to fail or return incorrect results
4. The search implementation uses: `1 - (dc.embedding <=> $1) AS similarity` which requires pgvector codec
5. Similarity threshold is hardcoded to 0.7 in `knowledge_search()` function

### Evidence

Database verification:
- Documents table has 2 ready documents (sample-knowledge.md, Test Document)
- document_chunks table has 10 chunks with embeddings
- Sample document has 6 chunks, 220 tokens
- Test document has 4 chunks, 120 tokens
- All chunks confirmed to have embeddings (not NULL)

API verification:
```bash
curl -X POST 'http://localhost:8420/api/knowledge/search' \
  -H 'Content-Type: application/json' \
  -d '{"query": "semantic search"}'
# Response: []

curl -s 'http://localhost:8420/api/knowledge/documents'
# Shows both documents with status "ready" and correct chunk counts
```

Screenshots:
- `docs/testing/evidence/tc-03-results.png` - Shows empty search results

### Relevant Changes in This PR

**Key files related to failure:**
- `amelia/server/database/connection.py` (lines 11, 113) - Added pgvector codec registration
- `amelia/knowledge/search.py` (lines 16, 33-40) - New search module with 0.7 threshold
- `amelia/knowledge/repository.py` (lines 221-317) - search_chunks implementation using vector similarity
- `amelia/server/routes/knowledge.py` (lines 183-207) - Search endpoint
- `dashboard/src/pages/KnowledgePage.tsx` - Frontend search UI

**Critical change:**
```diff
+from pgvector.asyncpg import register_vector

 @staticmethod
 async def _init_connection(conn: asyncpg.Connection) -> None:
-    """Register JSON/JSONB codecs for automatic encoding/decoding."""
+    """Register JSON/JSONB and pgvector codecs for automatic encoding/decoding."""
     await conn.set_type_codec(...)
+    await register_vector(conn)
```

### Suggested Investigation

1. **Restart the dev server** to pick up pgvector codec registration:
   ```bash
   # Kill old server
   lsof -ti:8420 | xargs kill

   # Start fresh server
   uv run amelia dev
   ```

2. **Verify pgvector codec is registered** by checking if vector queries work after restart

3. **Consider lowering similarity threshold** from 0.7 to 0.5 for testing to see actual similarity scores:
   - Edit `amelia/knowledge/search.py:16` to change default threshold
   - Or expose `similarity_threshold` in SearchRequest model
   - Log actual similarity scores to understand what's realistic

4. **Add integration test** that verifies search works after ingestion:
   - Upload document → wait for ready → search → assert results found
   - Would have caught this codec registration issue

### Debug Session Prompt

Copy this to start a new Claude session:

---
I'm debugging a test failure in branch `feat/knowledge-search-ui`.

**Test:** TC-03 - Search for uploaded document content and verify results
**Error:** Search API returning empty array despite documents being ingested with embeddings

The Knowledge Library feature has:
- Document upload and ingestion working (documents reach "ready" status with chunks)
- Database has 10 chunks with embeddings
- Search API returns `[]` with HTTP 200

**Root cause:** Dev server was started before `register_vector(conn)` was added to database connection initialization, so vector similarity operations aren't working properly.

Relevant files:
- amelia/server/database/connection.py (added pgvector codec registration)
- amelia/knowledge/search.py (new search implementation with 0.7 threshold)
- amelia/knowledge/repository.py (search_chunks with vector similarity query)

Help me:
1. Verify the fix (restart server with pgvector codec registered)
2. Determine if 0.7 similarity threshold is too high for realistic queries
3. Add logging of actual similarity scores for debugging
4. Consider whether to expose similarity_threshold as API parameter
---
