/**
 * @fileoverview Settings page for managing profiles.
 */
import { useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Search } from 'lucide-react';
import { ProfileCard } from '@/components/settings/ProfileCard';
import { ProfileEditModal } from '@/components/settings/ProfileEditModal';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { deleteProfile, activateProfile } from '@/api/settings';
import type { Profile } from '@/api/settings';
import * as toast from '@/components/Toast';

interface LoaderData {
  profiles: Profile[];
}

type DriverFilter = 'all' | 'api' | 'cli';

export default function SettingsProfilesPage() {
  const { profiles } = useLoaderData() as LoaderData;
  const { revalidate } = useRevalidator();

  const [search, setSearch] = useState('');
  const [driverFilter, setDriverFilter] = useState<DriverFilter>('all');
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Filter profiles
  const filteredProfiles = profiles.filter((p) => {
    if (search && !p.id.toLowerCase().includes(search.toLowerCase())) {
      return false;
    }
    if (driverFilter === 'api' && !p.driver.startsWith('api:')) {
      return false;
    }
    if (driverFilter === 'cli' && !p.driver.startsWith('cli:')) {
      return false;
    }
    return true;
  });

  // Sort: active first, then by name
  const sortedProfiles = [...filteredProfiles].sort((a, b) => {
    if (a.is_active && !b.is_active) return -1;
    if (!a.is_active && b.is_active) return 1;
    return a.id.localeCompare(b.id);
  });

  const handleEdit = (profile: Profile) => {
    setEditingProfile(profile);
    setIsModalOpen(true);
  };

  const handleDelete = async (profile: Profile) => {
    if (!confirm(`Delete profile "${profile.id}"?`)) return;
    try {
      await deleteProfile(profile.id);
      toast.success('Profile deleted');
      revalidate();
    } catch {
      toast.error('Failed to delete profile');
    }
  };

  const handleActivate = async (profile: Profile) => {
    try {
      await activateProfile(profile.id);
      toast.success(`Profile "${profile.id}" is now active`);
      revalidate();
    } catch {
      toast.error('Failed to activate profile');
    }
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Profiles</h1>
        <Button onClick={() => { setEditingProfile(null); setIsModalOpen(true); }}>
          <Plus className="mr-2 h-4 w-4" /> Create Profile
        </Button>
      </div>

      <div className="flex items-center gap-4">
        <ToggleGroup
          type="single"
          value={driverFilter}
          onValueChange={(v) => v && setDriverFilter(v as DriverFilter)}
        >
          <ToggleGroupItem value="all">All</ToggleGroupItem>
          <ToggleGroupItem value="api">API</ToggleGroupItem>
          <ToggleGroupItem value="cli">CLI</ToggleGroupItem>
        </ToggleGroup>

        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search profiles..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      {sortedProfiles.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          {profiles.length === 0 ? (
            <p>No profiles configured. Create one to get started.</p>
          ) : (
            <p>No profiles match your search.</p>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sortedProfiles.map((profile) => (
            <ProfileCard
              key={profile.id}
              profile={profile}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onActivate={handleActivate}
            />
          ))}
        </div>
      )}

      <ProfileEditModal
        open={isModalOpen}
        onOpenChange={setIsModalOpen}
        profile={editingProfile}
        onSaved={revalidate}
      />
    </div>
  );
}
