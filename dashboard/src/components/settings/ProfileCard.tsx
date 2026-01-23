/**
 * @fileoverview Card component displaying a profile with agent configuration summary.
 *
 * Shows primary agent configuration at a glance with visual indicators for
 * driver type and model tier. Supports activation, editing, and deletion.
 */
import { motion } from 'motion/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Pencil,
  Trash2,
  Star,
  Folder,
  Terminal,
  Cloud,
  Brain,
  Code,
  Search,
  MoreHorizontal,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { Profile } from '@/api/settings';

interface ProfileCardProps {
  profile: Profile;
  onEdit: (profile: Profile) => void;
  onDelete: (profile: Profile) => void;
  onActivate: (profile: Profile) => void;
}

/** Agent display metadata */
const AGENT_ICONS = {
  architect: Brain,
  developer: Code,
  reviewer: Search,
} as const;

const AGENT_LABELS = {
  architect: 'Arch',
  developer: 'Dev',
  reviewer: 'Rev',
} as const;

/** Model tier colors for visual hierarchy */
const MODEL_COLORS = {
  opus: 'text-primary',
  sonnet: 'text-accent',
  haiku: 'text-muted-foreground',
} as const;

/** Get driver icon component */
const getDriverIcon = (driver: string) => {
  return driver.startsWith('cli:') ? Terminal : Cloud;
};

/** Get model display color */
const getModelColor = (model: string): string => {
  // Check for known tiers
  if (model.includes('opus') || model.includes('gpt-4')) return MODEL_COLORS.opus;
  if (model.includes('sonnet') || model.includes('gpt-3.5')) return MODEL_COLORS.sonnet;
  // Default to haiku styling for unknown models
  return MODEL_COLORS.haiku as string;
};

/** Truncate model name for display */
const formatModel = (model: string): string => {
  // Handle OpenRouter model names like "qwen/qwen3-coder-flash"
  if (model.includes('/')) {
    const parts = model.split('/');
    const lastPart = parts[parts.length - 1];
    return lastPart ? lastPart.slice(0, 12) : model;
  }
  return model;
};

export function ProfileCard({ profile, onEdit, onDelete, onActivate }: ProfileCardProps) {
  // Get primary agents configuration
  const primaryAgents = ['architect', 'developer', 'reviewer'] as const;
  const agentConfigs = primaryAgents.map(key => ({
    key,
    driver: profile.agents?.[key]?.driver ?? 'cli:claude',
    model: profile.agents?.[key]?.model ?? 'unknown',
  }));

  // Count utility agents for badge
  const utilityAgentCount = Object.keys(profile.agents ?? {}).filter(
    k => !primaryAgents.includes(k as typeof primaryAgents[number])
  ).length;

  // Check if all agents use the same driver
  // Note: agentConfigs always has 3 elements (architect, developer, reviewer)
  const firstConfig = agentConfigs[0]!;
  const allSameDriver = agentConfigs.every(a => a.driver === firstConfig.driver);
  const primaryDriver = firstConfig.driver;
  const DriverIcon = getDriverIcon(primaryDriver);

  const handleCardClick = () => {
    if (!profile.is_active) {
      onActivate(profile);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ' ') && !profile.is_active) {
      if (e.key === ' ') {
        e.preventDefault();
      }
      onActivate(profile);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <Card
        data-testid="profile-card"
        onClick={handleCardClick}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        role="button"
        aria-pressed={profile.is_active}
        aria-label={`${profile.is_active ? 'Active profile' : 'Activate profile'} ${profile.id}`}
        className={`
          group relative cursor-pointer overflow-hidden transition-all duration-200
          hover:translate-y-[-2px] hover:shadow-lg hover:shadow-primary/5
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
          ${profile.is_active ? 'border-primary shadow-md shadow-primary/10' : 'border-border/50'}
        `}
      >
        {/* Active indicator accent line */}
        {profile.is_active && (
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary" />
        )}

        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2 min-w-0">
            <CardTitle className="text-sm font-medium truncate">{profile.id}</CardTitle>
            {profile.is_active && (
              <Badge variant="secondary" className="text-xs shrink-0">
                <Star className="mr-1 h-3 w-3" /> Active
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
              aria-label={`Edit profile ${profile.id}`}
              onClick={(e) => {
                e.stopPropagation();
                onEdit(profile);
              }}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
              aria-label={`Delete profile ${profile.id}`}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(profile);
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* Driver badge */}
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={`text-xs ${
                primaryDriver.startsWith('cli:')
                  ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30'
                  : 'bg-blue-500/10 text-blue-500 border-blue-500/30'
              }`}
            >
              <DriverIcon className="mr-1 h-3 w-3" />
              {primaryDriver}
            </Badge>
            {!allSameDriver && (
              <span className="text-[10px] text-muted-foreground">mixed</span>
            )}
          </div>

          {/* Agent configuration grid */}
          <TooltipProvider delayDuration={300}>
            <div className="grid grid-cols-3 gap-1.5">
              {agentConfigs.map(({ key, driver, model }) => {
                const Icon = AGENT_ICONS[key];
                const AgentDriverIcon = getDriverIcon(driver);
                const modelColor = getModelColor(model);

                return (
                  <Tooltip key={key}>
                    <TooltipTrigger asChild>
                      <div className="flex flex-col items-center gap-1 rounded-md bg-muted/30 p-2 transition-colors hover:bg-muted/50">
                        <div className="flex items-center gap-1">
                          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                            {AGENT_LABELS[key]}
                          </span>
                        </div>
                        <div className="flex items-center gap-0.5">
                          <AgentDriverIcon className="h-2.5 w-2.5 text-muted-foreground/60" />
                          <span className={`text-xs font-medium ${modelColor}`}>
                            {formatModel(model)}
                          </span>
                        </div>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-xs">
                      <div className="space-y-1">
                        <div className="font-medium capitalize">{key}</div>
                        <div className="text-muted-foreground">
                          {driver} / {model}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </TooltipProvider>

          {/* Utility agents count */}
          {utilityAgentCount > 0 && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <MoreHorizontal className="h-3 w-3" />
              <span>+{utilityAgentCount} utility agents</span>
            </div>
          )}

          {/* Working directory */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground truncate">
            <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
            <span className="truncate" title={profile.working_dir}>
              {profile.working_dir}
            </span>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
