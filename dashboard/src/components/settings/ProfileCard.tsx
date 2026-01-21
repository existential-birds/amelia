/**
 * @fileoverview Card component displaying a profile with actions.
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Pencil, Trash2, Star, Folder } from 'lucide-react';
import type { Profile } from '@/api/settings';
import { getDriverStyle } from '@/utils/driver-colors';

interface ProfileCardProps {
  profile: Profile;
  onEdit: (profile: Profile) => void;
  onDelete: (profile: Profile) => void;
  onActivate: (profile: Profile) => void;
}

export function ProfileCard({ profile, onEdit, onDelete, onActivate }: ProfileCardProps) {
  const driverStyle = getDriverStyle(profile.driver);
  const DriverIcon = driverStyle.icon;

  const handleCardClick = () => {
    if (!profile.is_active) {
      onActivate(profile);
    }
  };

  return (
    <Card
      onClick={handleCardClick}
      className={`cursor-pointer transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-primary/5 ${
        profile.is_active ? 'border-primary shadow-md shadow-primary/10' : ''
      }`}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">{profile.id}</CardTitle>
          {profile.is_active && (
            <Badge variant="secondary" className="text-xs">
              <Star className="mr-1 h-3 w-3" /> Active
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
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
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(profile);
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={`${driverStyle.bg} ${driverStyle.text}`}>
              <DriverIcon className="mr-1 h-3 w-3" />
              {profile.driver}
            </Badge>
            <span>{profile.model}</span>
          </div>
          <div className="flex items-center gap-1.5 truncate">
            <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
            <span className="truncate" title={profile.working_dir}>
              {profile.working_dir}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
