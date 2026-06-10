/**
 * Agents section of the profile detail page.
 *
 * Renders the bulk-apply control, the three primary agent rows, and a
 * collapsible holding the four utility agent rows. Each row uses a fixed
 * three-column grid (name / driver-select / model-select) so all ten rows
 * align identically — replacing the old AgentCard flex/fixed-width layout.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { ChevronDown, Copy, Check, Code2, Wand2, Terminal, Cloud } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AGENT_DEFINITIONS, getModelsForDriver, type AgentDefinition } from '@/lib/constants';
import { ApiModelSelect } from '@/components/model-picker';
import type { AgentFormData } from './types';

const PRIMARY_AGENTS = AGENT_DEFINITIONS.filter((a) => a.category === 'primary');
const UTILITY_AGENTS = AGENT_DEFINITIONS.filter((a) => a.category === 'utility');

const DRIVER_OPTIONS = [
  { value: 'claude', label: 'Claude CLI', icon: Terminal },
  { value: 'codex', label: 'Codex CLI', icon: Code2 },
  { value: 'api', label: 'OpenRouter API', icon: Cloud },
];

/** Agent-specific colors matching canvas node styling */
const AGENT_COLORS: Record<string, { line: string; icon: string }> = {
  architect: { line: 'bg-agent-architect', icon: 'text-agent-architect' },
  developer: { line: 'bg-agent-developer', icon: 'text-agent-developer' },
  reviewer: { line: 'bg-agent-reviewer', icon: 'text-agent-reviewer' },
  plan_validator: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  task_reviewer: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  evaluator: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  brainstormer: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
};

interface AgentRowProps {
  agent: AgentDefinition;
  config: AgentFormData;
  error: boolean;
  onChange: (field: 'driver' | 'model', value: string) => void;
}

function AgentRow({ agent, config, error, onChange }: AgentRowProps) {
  const Icon = agent.icon;
  const availableModels = getModelsForDriver(config.driver);
  const colors = AGENT_COLORS[agent.key] ?? { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' };

  return (
    <div className="group grid grid-cols-[1fr_auto_auto] items-start gap-2 rounded-md border border-border/40 bg-card/30 px-3 py-2 transition-all duration-200 hover:border-border/60 hover:bg-card/50">
      {/* Agent icon + name */}
      <div className="flex min-h-7 min-w-0 items-center gap-2">
        <div className={cn('h-6 w-0.5 shrink-0 rounded-full', colors.line)} />
        <Icon className={cn('h-4 w-4 shrink-0', colors.icon)} />
        <span className="truncate font-heading text-sm font-medium tracking-wide">{agent.label}</span>
      </div>

      {/* Driver select */}
      <Select value={config.driver} onValueChange={(v) => onChange('driver', v)}>
        <SelectTrigger className="h-7 w-[130px] bg-background/50 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {DRIVER_OPTIONS.map((opt) => {
            const OptIcon = opt.icon;
            return (
              <SelectItem key={opt.value} value={opt.value}>
                <div className="flex items-center gap-2">
                  <OptIcon className="h-3 w-3" />
                  {opt.label}
                </div>
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>

      {/* Model select - ApiModelSelect for api driver, simple Select otherwise */}
      {config.driver === 'api' ? (
        <ApiModelSelect
          agentKey={agent.key}
          value={config.model}
          onChange={(v) => onChange('model', v)}
          error={error}
          className="h-7 w-[160px]"
        />
      ) : (
        <Select
          key={`${agent.key}-model-${config.driver}`}
          value={config.model}
          onValueChange={(v) => onChange('model', v)}
        >
          <SelectTrigger className="h-7 w-[160px] bg-background/50 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {availableModels.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

interface BulkApplyProps {
  onApply: (driver: string, model: string, targets: 'all' | 'primary' | 'utility') => void;
}

function BulkApply({ onApply }: BulkApplyProps) {
  const [driver, setDriverRaw] = useState('claude');
  const [model, setModel] = useState('sonnet');
  const [showSuccess, setShowSuccess] = useState(false);
  const availableModels = getModelsForDriver(driver);

  const setDriver = (newDriver: string) => {
    setDriverRaw(newDriver);
    if (newDriver === 'api') {
      setModel('');
    } else {
      const models = getModelsForDriver(newDriver);
      setModel((prev) => (models.includes(prev) ? prev : models[0] ?? ''));
    }
  };

  const handleApply = (targets: 'all' | 'primary' | 'utility') => {
    onApply(driver, model, targets);
    setShowSuccess(true);
    setTimeout(() => setShowSuccess(false), 1500);
  };

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md border border-border/30 bg-background/30 px-3 py-2 text-xs font-medium transition-all hover:border-border/50 hover:bg-muted/30">
        <div className="flex items-center gap-2">
          <Copy className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Bulk Configuration</span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 [[data-state=open]>&]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">
        <div className="space-y-3 rounded-lg border border-border/30 bg-card/20 p-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground/70">Driver</Label>
              <Select value={driver} onValueChange={setDriver}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DRIVER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground/70">Model</Label>
              {driver === 'api' ? (
                <ApiModelSelect agentKey="__bulk__" value={model} onChange={setModel} className="h-8 w-full" />
              ) : (
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {availableModels.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 flex-1 text-xs"
              onClick={() => handleApply('all')}
            >
              {showSuccess ? <Check className="mr-1 h-3 w-3" /> : <Wand2 className="mr-1 h-3 w-3" />}
              Apply to All
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => handleApply('primary')}
            >
              Primary Only
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => handleApply('utility')}
            >
              Utility Only
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

interface AgentsSectionProps {
  agents: Record<string, AgentFormData>;
  errors: Record<string, string>;
  onAgentChange: (key: string, field: 'driver' | 'model', value: string) => void;
  onBulkApply: (driver: string, model: string, targets: 'all' | 'primary' | 'utility') => void;
}

export function AgentsSection({ agents, errors, onAgentChange, onBulkApply }: AgentsSectionProps) {
  const [utilityOpen, setUtilityOpen] = useState(false);

  const utilityConfigCount = UTILITY_AGENTS.filter((agent) => agents[agent.key]).length;

  return (
    <div className="space-y-4">
      <BulkApply onApply={onBulkApply} />

      {/* Primary Agents */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">Primary Agents</Label>
          <Badge variant="secondary" className="h-4 px-1.5 py-0 text-[10px]">
            Core workflow
          </Badge>
        </div>
        <div className="grid grid-cols-1 gap-2">
          {PRIMARY_AGENTS.map((agent) => {
            const config = agents[agent.key] ?? { driver: 'claude', model: agent.defaultModel };
            return (
              <AgentRow
                key={agent.key}
                agent={agent}
                config={config}
                error={!!errors[`agent_model_${agent.key}`]}
                onChange={(field, value) => onAgentChange(agent.key, field, value)}
              />
            );
          })}
        </div>
      </div>

      {/* Utility Agents (Collapsible) */}
      <Collapsible open={utilityOpen} onOpenChange={setUtilityOpen}>
        <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border border-border/30 bg-background/30 px-4 py-3 text-sm font-medium transition-all hover:border-border/50 hover:bg-muted/30">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wider">Utility Agents</span>
            <Badge variant="outline" className="h-4 px-1.5 py-0 text-[10px]">
              {utilityConfigCount} configured
            </Badge>
          </div>
          <ChevronDown
            className={cn(
              'size-4 text-muted-foreground transition-transform duration-200',
              utilityOpen && 'rotate-180'
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <div className="grid grid-cols-1 gap-2">
            {UTILITY_AGENTS.map((agent) => {
              const config = agents[agent.key] ?? { driver: 'claude', model: agent.defaultModel };
              return (
                <AgentRow
                  key={agent.key}
                  agent={agent}
                  config={config}
                  error={!!errors[`agent_model_${agent.key}`]}
                  onChange={(field, value) => onAgentChange(agent.key, field, value)}
                />
              );
            })}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
