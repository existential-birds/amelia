/**
 * Settings page for server configuration.
 */
import { useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { ServerSettingsForm } from '@/components/settings/ServerSettingsForm';
import { updateServerSettings } from '@/api/settings';
import type { ServerSettings } from '@/api/settings';
import * as toast from '@/components/Toast';

interface LoaderData {
  serverSettings: ServerSettings;
}

export default function SettingsServerPage() {
  const { serverSettings } = useLoaderData() as LoaderData;
  const { revalidate } = useRevalidator();
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async (updates: Partial<ServerSettings>) => {
    setIsSaving(true);
    try {
      await updateServerSettings(updates);
      toast.success('Settings saved');
      revalidate();
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="container mx-auto py-6 px-4 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Server Settings</h1>
      <ServerSettingsForm
        settings={serverSettings}
        onSave={handleSave}
        isSaving={isSaving}
      />
    </div>
  );
}
