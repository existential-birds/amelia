/**
 * Reusable toggle field component for settings forms.
 */
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

interface ToggleFieldProps {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

export function ToggleField({ id, label, description, checked, onCheckedChange }: ToggleFieldProps) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
