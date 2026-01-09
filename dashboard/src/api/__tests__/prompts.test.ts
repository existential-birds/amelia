import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../client';

// Mock fetch globally
global.fetch = vi.fn();

// ============================================================================
// Test Helpers
// ============================================================================

function mockFetchSuccess<T>(data: T) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: true,
    json: async () => data,
  });
}

function mockFetchError(status: number, error: string, code: string) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: false,
    status,
    json: async () => ({ error, code }),
  });
}

// ============================================================================
// Tests
// ============================================================================

describe('Prompts API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getPrompts', () => {
    it('should fetch prompts list', async () => {
      const mockPrompts = [
        {
          id: 'architect.system',
          agent: 'architect',
          name: 'System Prompt',
          description: 'Main system prompt',
          current_version_id: 'v-123',
          current_version_number: 1,
        },
      ];

      mockFetchSuccess({ prompts: mockPrompts });

      const prompts = await api.getPrompts();

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(prompts).toHaveLength(1);
      expect(prompts[0]!.id).toBe('architect.system');
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(500, 'Internal server error', 'INTERNAL_ERROR');

      await expect(api.getPrompts()).rejects.toThrow('Internal server error');
    });
  });

  describe('getPrompt', () => {
    it('should fetch single prompt by ID', async () => {
      const mockPrompt = {
        id: 'architect.system',
        agent: 'architect',
        name: 'System Prompt',
        description: 'Main system prompt',
        current_version_id: 'v-123',
        versions: [
          {
            id: 'v-123',
            version_number: 1,
            created_at: '2025-12-01T10:00:00Z',
            change_note: 'Initial version',
          },
        ],
      };

      mockFetchSuccess(mockPrompt);

      const prompt = await api.getPrompt('architect.system');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(prompt.id).toBe('architect.system');
      expect(prompt.versions).toHaveLength(1);
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Prompt not found', 'NOT_FOUND');

      await expect(api.getPrompt('nonexistent')).rejects.toThrow('Prompt not found');
    });
  });

  describe('getPromptVersions', () => {
    it('should fetch versions for a prompt', async () => {
      const mockVersions = [
        {
          id: 'v-123',
          version_number: 1,
          created_at: '2025-12-01T10:00:00Z',
          change_note: 'Initial version',
        },
        {
          id: 'v-456',
          version_number: 2,
          created_at: '2025-12-02T10:00:00Z',
          change_note: 'Updated prompt',
        },
      ];

      mockFetchSuccess({ versions: mockVersions });

      const versions = await api.getPromptVersions('architect.system');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/versions',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(versions).toHaveLength(2);
      expect(versions[0]!.version_number).toBe(1);
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Prompt not found', 'NOT_FOUND');

      await expect(api.getPromptVersions('nonexistent')).rejects.toThrow('Prompt not found');
    });
  });

  describe('getPromptVersion', () => {
    it('should fetch a specific version by ID', async () => {
      const mockVersion = {
        id: 'v-123',
        prompt_id: 'architect.system',
        version_number: 1,
        content: 'Full prompt content here...',
        created_at: '2025-12-01T10:00:00Z',
        change_note: 'Initial version',
      };

      mockFetchSuccess(mockVersion);

      const version = await api.getPromptVersion('architect.system', 'v-123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/versions/v-123',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(version.id).toBe('v-123');
      expect(version.content).toBe('Full prompt content here...');
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Version not found', 'NOT_FOUND');

      await expect(api.getPromptVersion('architect.system', 'nonexistent')).rejects.toThrow(
        'Version not found'
      );
    });
  });

  describe('createPromptVersion', () => {
    it('should create new version with correct payload', async () => {
      const mockVersion = {
        id: 'v-789',
        prompt_id: 'architect.system',
        version_number: 2,
        content: 'New content',
        created_at: '2025-12-03T10:00:00Z',
        change_note: 'Test note',
      };

      mockFetchSuccess(mockVersion);

      const version = await api.createPromptVersion('architect.system', 'New content', 'Test note');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/versions',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: 'New content', change_note: 'Test note' }),
          signal: expect.any(AbortSignal),
        })
      );
      expect(version.id).toBe('v-789');
      expect(version.version_number).toBe(2);
    });

    it('should handle null change note', async () => {
      const mockVersion = {
        id: 'v-789',
        prompt_id: 'architect.system',
        version_number: 2,
        content: 'New content',
        created_at: '2025-12-03T10:00:00Z',
        change_note: null,
      };

      mockFetchSuccess(mockVersion);

      await api.createPromptVersion('architect.system', 'New content', null);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/versions',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: 'New content', change_note: null }),
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(400, 'Validation error', 'VALIDATION_ERROR');

      await expect(api.createPromptVersion('architect.system', '', null)).rejects.toThrow(
        'Validation error'
      );
    });
  });

  describe('resetPromptToDefault', () => {
    it('should POST to reset endpoint', async () => {
      mockFetchSuccess({ status: 'ok' });

      await api.resetPromptToDefault('architect.system');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/reset',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Prompt not found', 'NOT_FOUND');

      await expect(api.resetPromptToDefault('nonexistent')).rejects.toThrow('Prompt not found');
    });
  });

  describe('getPromptDefault', () => {
    it('should fetch default content for a prompt', async () => {
      const mockDefault = {
        prompt_id: 'architect.system',
        content: 'Default prompt content...',
        name: 'System Prompt',
        description: 'Main system prompt for the architect agent',
      };

      mockFetchSuccess(mockDefault);

      const defaultContent = await api.getPromptDefault('architect.system');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/prompts/architect.system/default',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(defaultContent.prompt_id).toBe('architect.system');
      expect(defaultContent.content).toBe('Default prompt content...');
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Prompt not found', 'NOT_FOUND');

      await expect(api.getPromptDefault('nonexistent')).rejects.toThrow('Prompt not found');
    });
  });
});
