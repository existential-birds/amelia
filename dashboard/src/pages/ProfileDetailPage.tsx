/**
 * @fileoverview Profile detail page — full-width profile configuration.
 *
 * Shared by `/settings/profiles/~new` (create) and `/settings/profiles/:id`
 * (edit). Owns a `useProfileForm` hook and composes the four configuration
 * sections behind a `SectionRail`. A `useBlocker`-based dirty guard intercepts
 * in-app navigation away from an unsaved form and resolves it through the app's
 * `AlertDialog`; a `beforeunload` handler covers hard reload / tab-close with
 * the browser's native prompt (a custom dialog is impossible there by design).
 */
import { useEffect, useState } from 'react';
import { useBlocker, useLoaderData, useNavigate } from 'react-router-dom';
import { Cpu, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import { useProfileForm } from '@/components/settings/profile-form/useProfileForm';
import { IdentitySection } from '@/components/settings/profile-form/IdentitySection';
import { AgentsSection } from '@/components/settings/profile-form/AgentsSection';
import { SandboxSection } from '@/components/settings/profile-form/SandboxSection';
import { AutoFixSection } from '@/components/settings/profile-form/AutoFixSection';
import { SectionRail } from '@/components/settings/profile-form/SectionRail';
import type { SectionId } from '@/components/settings/profile-form/types';
import { activateProfile, createProfile, updateProfile } from '@/api/settings';
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
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState<SectionId>('identity');
  const [isSaving, setIsSaving] = useState(false);
  // Set when a Save attempt fails validation; the effect below jumps to the
  // first section with an error once `sectionErrors` has refreshed.
  const [jumpToError, setJumpToError] = useState(false);
  // Set after a successful save so we navigate only after isDirty has settled
  // to false (markSaved flushes via state, not synchronously).
  const [navigateAfterSave, setNavigateAfterSave] = useState(false);

  useEffect(() => {
    if (!jumpToError) return;
    const firstErrorSection = SECTIONS.find((s) => form.sectionErrors[s.id]);
    if (firstErrorSection) setActiveSection(firstErrorSection.id);
    setJumpToError(false);
  }, [jumpToError, form.sectionErrors]);

  // Intercept in-app navigation away from a dirty form.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      form.isDirty && currentLocation.pathname !== nextLocation.pathname
  );

  // Navigate to the list after a successful save. markSaved() clears isDirty,
  // but react-router can keep the previous (dirty) blocker predicate for one
  // render, so the post-save navigate() may still be intercepted — release it
  // through proceed() if that happens.
  useEffect(() => {
    if (!navigateAfterSave) return;
    if (blocker.state === 'blocked') {
      blocker.proceed();
    } else if (!form.isDirty) {
      navigate('/settings/profiles');
    }
  }, [navigateAfterSave, form.isDirty, blocker, navigate]);

  // Hard reload / tab-close can only trigger the browser's native prompt.
  useEffect(() => {
    if (!form.isDirty) return;
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [form.isDirty]);

  const handleActivate = async () => {
    if (!profile) return;
    try {
      await activateProfile(profile.id);
      toast.success(`Profile "${profile.id}" is now active`);
    } catch {
      toast.error('Failed to activate profile');
    }
  };

  const handleSave = async () => {
    // On validation failure, surface the rail error flags and jump to the first
    // section with an error — never touch the API.
    if (!form.validate()) {
      setJumpToError(true);
      return;
    }

    setIsSaving(true);
    try {
      if (isEditMode) {
        await updateProfile(profile.id, form.toUpdatePayload());
        toast.success('Profile updated');
      } else {
        await createProfile(form.toCreatePayload());
        toast.success('Profile created');
      }
      form.markSaved();
      setNavigateAfterSave(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setIsSaving(false);
    }
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
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/settings/profiles')}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="min-w-[120px]"
          >
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
              onBlur={(field) => form.handleBlur(field, form.formData[field])}
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

      {/* Unsaved-changes guard for in-app navigation */}
      <AlertDialog open={blocker.state === 'blocked'}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard your edits?</AlertDialogTitle>
            <AlertDialogDescription>
              You have unsaved changes. If you leave this page, your edits will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => blocker.reset?.()}>
              Keep editing
            </AlertDialogCancel>
            <AlertDialogAction onClick={() => blocker.proceed?.()}>
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
