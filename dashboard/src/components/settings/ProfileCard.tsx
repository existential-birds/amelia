/**
 * @fileoverview Card component displaying a profile with actions.
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MoreHorizontal, Pencil, Trash2, Star } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Profile } from '@/api/settings';

interface ProfileCardProps {
  profile: Profile;
  onEdit: (profile: Profile) => void;
  onDelete: (profile: Profile) => void;
  onActivate: (profile: Profile) => void;
}

export function ProfileCard({ profile, onEdit, onDelete, onActivate }: ProfileCardProps) {
  const driverColor = profile.driver.startsWith('cli:')
    ? 'bg-yellow-500/10 text-yellow-500'
    : 'bg-blue-500/10 text-blue-500';

  return (
    <Card className={profile.is_active ? 'border-primary' : ''}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">{profile.id}</CardTitle>
          {profile.is_active && (
            <Badge variant="secondary" className="text-xs">
              <Star className="mr-1 h-3 w-3" /> Active
            </Badge>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(profile)}>
              <Pencil className="mr-2 h-4 w-4" /> Edit
            </DropdownMenuItem>
            {!profile.is_active && (
              <DropdownMenuItem onClick={() => onActivate(profile)}>
                <Star className="mr-2 h-4 w-4" /> Set Active
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={() => onDelete(profile)}
              variant="destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={driverColor}>
              {profile.driver}
            </Badge>
            <span>{profile.model}</span>
          </div>
          <div className="truncate">{profile.working_dir}</div>
        </div>
      </CardContent>
    </Card>
  );
}
