/**
 * @fileoverview Settings page for managing profiles.
 *
 * Features a "Mission Control" aesthetic with:
 * - First-time setup flow when no profiles exist
 * - Filterable profile grid with driver badges
 * - Responsive layout for mobile devices
 */
import { useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Plus,
  Search,
  Cpu,
  Terminal,
  Cloud,
  Sparkles,
  Brain,
  Code,
  Search as SearchIcon,
  ArrowRight,
} from 'lucide-react';
import { ProfileCard } from '@/components/settings/ProfileCard';
import { ProfileEditModal } from '@/components/settings/ProfileEditModal';
import { deleteProfile, activateProfile } from '@/api/settings';
import type { Profile } from '@/api/settings';
import * as toast from '@/components/Toast';

interface LoaderData {
  profiles: Profile[];
}

type DriverFilter = 'all' | 'api' | 'cli';

/**
 * Empty state component for first-time setup.
 * Guides users through creating their first profile with visual appeal.
 */
function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="relative flex flex-col items-center justify-center py-16 px-6"
    >
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-radial from-primary/5 via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      {/* Main content */}
      <div className="relative z-10 max-w-md text-center space-y-8">
        {/* Icon cluster */}
        <div className="relative flex items-center justify-center">
          <motion.div
            initial={{ scale: 0, rotate: -10 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
            className="absolute -left-8 -top-2"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/50 border border-border/50 shadow-lg">
              <Brain className="h-6 w-6 text-accent" />
            </div>
          </motion.div>

          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.1, type: 'spring', stiffness: 200 }}
            className="relative z-10"
          >
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 border border-primary/30 shadow-xl shadow-primary/10">
              <Cpu className="h-10 w-10 text-primary" />
            </div>
          </motion.div>

          <motion.div
            initial={{ scale: 0, rotate: 10 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: 0.3, type: 'spring', stiffness: 200 }}
            className="absolute -right-8 -top-2"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/50 border border-border/50 shadow-lg">
              <Code className="h-6 w-6 text-accent" />
            </div>
          </motion.div>

          <motion.div
            initial={{ scale: 0, rotate: -5 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: 0.4, type: 'spring', stiffness: 200 }}
            className="absolute -bottom-4 -right-4"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted/50 border border-border/50 shadow-lg">
              <SearchIcon className="h-5 w-5 text-muted-foreground" />
            </div>
          </motion.div>
        </div>

        {/* Text content */}
        <div className="space-y-3">
          <h2 className="font-heading text-2xl font-semibold tracking-wide">
            Configure Your Agent Team
          </h2>
          <p className="text-muted-foreground leading-relaxed">
            Profiles define how your agents work together. Configure drivers, models,
            and settings for each agent in your orchestration workflow.
          </p>
        </div>

        {/* Feature highlights */}
        <div className="grid grid-cols-3 gap-4 text-xs">
          <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-card/30 border border-border/30">
            <Terminal className="h-5 w-5 text-yellow-500" />
            <span className="text-muted-foreground">Claude CLI</span>
          </div>
          <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-card/30 border border-border/30">
            <Cloud className="h-5 w-5 text-blue-500" />
            <span className="text-muted-foreground">OpenRouter</span>
          </div>
          <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-card/30 border border-border/30">
            <Sparkles className="h-5 w-5 text-primary" />
            <span className="text-muted-foreground">7 Agents</span>
          </div>
        </div>

        {/* CTA button */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <Button
            size="lg"
            className="group gap-2 px-6"
            onClick={onCreateClick}
          >
            <Plus className="h-4 w-4" />
            Create Your First Profile
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </Button>
        </motion.div>
      </div>
    </motion.div>
  );
}

/**
 * No results state when search/filter yields nothing.
 */
function NoResults({ onClearFilters }: { onClearFilters: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Search className="h-12 w-12 text-muted-foreground/30 mb-4" />
      <h3 className="font-heading text-lg font-medium mb-1">No profiles found</h3>
      <p className="text-sm text-muted-foreground mb-4">
        Try adjusting your search or filter criteria.
      </p>
      <Button variant="outline" size="sm" onClick={onClearFilters}>
        Clear filters
      </Button>
    </div>
  );
}

export default function SettingsProfilesPage() {
  const { profiles } = useLoaderData() as LoaderData;
  const { revalidate } = useRevalidator();

  const [search, setSearch] = useState('');
  const [driverFilter, setDriverFilter] = useState<DriverFilter>('all');
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deletingProfile, setDeletingProfile] = useState<Profile | null>(null);

  /**
   * Get the primary driver from a profile's agents configuration.
   */
  const getPrimaryDriver = (profile: Profile): string | undefined => {
    return profile.agents?.architect?.driver;
  };

  // Filter profiles
  const filteredProfiles = profiles.filter((p) => {
    if (search && !p.id.toLowerCase().includes(search.toLowerCase())) {
      return false;
    }
    const driver = getPrimaryDriver(p);
    if (driverFilter === 'api' && !driver?.startsWith('api:')) {
      return false;
    }
    if (driverFilter === 'cli' && !driver?.startsWith('cli:')) {
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

  const handleDeleteRequest = (profile: Profile) => {
    setDeletingProfile(profile);
  };

  const handleDeleteConfirm = async () => {
    if (!deletingProfile) return;
    try {
      await deleteProfile(deletingProfile.id);
      toast.success('Profile deleted');
      revalidate();
    } catch {
      toast.error('Failed to delete profile');
    } finally {
      setDeletingProfile(null);
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

  const handleCreateClick = () => {
    setEditingProfile(null);
    setIsModalOpen(true);
  };

  const handleClearFilters = () => {
    setSearch('');
    setDriverFilter('all');
  };

  // Show empty state if no profiles exist
  if (profiles.length === 0) {
    return (
      <div className="container mx-auto py-6 px-4">
        <EmptyState onCreateClick={handleCreateClick} />
        <ProfileEditModal
          open={isModalOpen}
          onOpenChange={setIsModalOpen}
          profile={editingProfile}
          onSaved={revalidate}
        />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-wide">Profiles</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure agent teams for different projects or workflows
          </p>
        </div>
        <Button onClick={handleCreateClick} className="gap-2 shrink-0">
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">Create Profile</span>
          <span className="sm:hidden">New</span>
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <ToggleGroup
          type="single"
          value={driverFilter}
          onValueChange={(v) => v && setDriverFilter(v as DriverFilter)}
          className="justify-start"
        >
          <ToggleGroupItem value="all" className="text-xs px-3">
            All
          </ToggleGroupItem>
          <ToggleGroupItem value="cli" className="text-xs px-3 gap-1.5">
            <Terminal className="h-3 w-3" />
            CLI
          </ToggleGroupItem>
          <ToggleGroupItem value="api" className="text-xs px-3 gap-1.5">
            <Cloud className="h-3 w-3" />
            API
          </ToggleGroupItem>
        </ToggleGroup>

        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search profiles..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 bg-background/50"
          />
        </div>

        {/* Results count */}
        <div className="text-xs text-muted-foreground">
          {filteredProfiles.length} of {profiles.length} profiles
        </div>
      </div>

      {/* Profile grid */}
      {sortedProfiles.length === 0 ? (
        <NoResults onClearFilters={handleClearFilters} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence mode="popLayout">
            {sortedProfiles.map((profile) => (
              <ProfileCard
                key={profile.id}
                profile={profile}
                onEdit={handleEdit}
                onDelete={handleDeleteRequest}
                onActivate={handleActivate}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Edit Modal */}
      <ProfileEditModal
        open={isModalOpen}
        onOpenChange={setIsModalOpen}
        profile={editingProfile}
        onSaved={revalidate}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={deletingProfile !== null} onOpenChange={(open) => !open && setDeletingProfile(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Profile</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete profile "{deletingProfile?.id}"? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConfirm}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
