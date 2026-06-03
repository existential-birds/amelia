/**
 * @fileoverview Profile detail page — full-width profile configuration.
 *
 * Shared by `/settings/profiles/new` (create) and `/settings/profiles/:id`
 * (edit). Owns a `useProfileForm` hook and composes the four configuration
 * sections behind a `SectionRail`. The save flow, navigation, and the
 * dirty-change guard are wired in later tasks; here the Save button validates
 * only, keeping the shell (header, rail, sections, set-active) in place.
 */
import { useState } from 'react';
import { useLoaderData } from 'react-router-dom';
import { Cpu, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useProfileForm } from '@/components/settings/profile-form/useProfileForm';
import { IdentitySection } from '@/components/settings/profile-form/IdentitySection';
import { AgentsSection } from '@/components/settings/profile-form/AgentsSection';
import { SandboxSection } from '@/components/settings/profile-form/SandboxSection';
import { AutoFixSection } from '@/components/settings/profile-form/AutoFixSection';
import { SectionRail } from '@/components/settings/profile-form/SectionRail';
import type { SectionId } from '@/components/settings/profile-form/types';
import { activateProfile } from '@/api/settings';
import { profileDetailLoader } from '@/loaders';
import * as toast from '@/components/Toast';

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'identity', label: 'Identity' },
  { id: 'agents', label: 'Agents' },
  { id: 'sandbox', label: 'Sandbox' },
  { id: 'autofix', label: 'Auto-Fix' },
];

/**
 * Renders the profile configuration page for create or edit.
 *
 * @returns The profile detail page UI.
 */
export default function ProfileDetailPage() {
  const { profile } = useLoaderData<typeof profileDetailLoader>();
  const isEditMode = profile !== null;
  const form = useProfileForm(profile);

  const [activeSection, setActiveSection] = useState<SectionId>('identity');

  const handleActivate = async () => {
    if (!profile) return;
    try {
      await activateProfile(profile.id);
      toast.success(`Profile "${profile.id}" is now active`);
    } catch {
      toast.error('Failed to activate profile');
    }
  };

  // Save flow (API call + navigation) is wired in Task 9; validate only for now.
  const handleSave = () => {
    form.validate();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-border/30 bg-background/95 px-6 py-4 backdrop-blur">
        <div className="flex items-center gap-2 min-w-0">
          <Cpu className="h-5 w-5 shrink-0 text-muted-foreground" />
          <h1 className="font-heading text-xl tracking-wide truncate">
            {isEditMode ? profile.id : 'Create Profile'}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {isEditMode && (
            <Button
              type="button"
              variant="outline"
              onClick={handleActivate}
              disabled={profile.is_active}
            >
              <Star
                className={profile.is_active ? 'h-4 w-4 fill-current text-primary' : 'h-4 w-4'}
              />
              {profile.is_active ? 'Active' : 'Set active'}
            </Button>
          )}
          <Button type="button" variant="outline">
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} className="min-w-[120px]">
            {isEditMode ? 'Save Changes' : 'Create Profile'}
          </Button>
        </div>
      </div>

      {/* Body: section rail + active section */}
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6 md:flex-row">
        <aside className="md:w-48 md:shrink-0">
          <SectionRail
            sections={SECTIONS}
            active={activeSection}
            onSelect={setActiveSection}
            errorSections={form.sectionErrors}
          />
        </aside>

        <div className="min-w-0 flex-1">
          {activeSection === 'identity' && (
            <IdentitySection
              formData={form.formData}
              errors={form.errors}
              isEditMode={isEditMode}
              onField={form.setField}
              onBlur={(field) => form.handleBlur(field as 'id' | 'repo_root', form.formData[field as 'id' | 'repo_root'])}
            />
          )}
          {activeSection === 'agents' && (
            <AgentsSection
              agents={form.formData.agents}
              errors={form.errors}
              onAgentChange={form.setAgent}
              onBulkApply={form.bulkApplyAgents}
            />
          )}
          {activeSection === 'sandbox' && (
            <SandboxSection
              sandbox={form.formData.sandbox}
              errors={form.errors}
              onField={form.setSandboxField}
              onHosts={form.setHosts}
            />
          )}
          {activeSection === 'autofix' && (
            <AutoFixSection config={form.formData.pr_autofix} onChange={form.setPrAutofix} />
          )}
        </div>
      </div>
    </div>
  );
}
