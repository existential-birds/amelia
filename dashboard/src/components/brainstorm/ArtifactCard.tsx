import { CheckCircle2, FileText, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import type { BrainstormArtifact } from "@/types/api";

interface ArtifactCardProps {
  artifact: BrainstormArtifact;
  onHandoff: (artifact: BrainstormArtifact) => void;
  isHandingOff?: boolean;
}

export function ArtifactCard({
  artifact,
  onHandoff,
  isHandingOff = false,
}: ArtifactCardProps) {
  return (
    <Card className="border-l-4 border-l-status-completed">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2 text-status-completed">
          <CheckCircle2 className="h-4 w-4" />
          <span className="text-sm font-medium">Design document created</span>
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        {artifact.title && (
          <p className="font-medium mb-1">{artifact.title}</p>
        )}
        <div className="flex items-center gap-2 text-muted-foreground">
          <FileText className="h-4 w-4 shrink-0" />
          <code className="text-xs bg-muted px-1.5 py-0.5 rounded truncate">
            {artifact.path}
          </code>
        </div>
      </CardContent>
      <CardFooter className="gap-2">
        <Button variant="secondary" size="sm" asChild>
          <a
            href={`/api/files/${encodeURIComponent(artifact.path)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            View Document
          </a>
        </Button>
        <Button
          size="sm"
          onClick={() => onHandoff(artifact)}
          disabled={isHandingOff}
          aria-label="Hand off to Implementation"
        >
          {isHandingOff ? (
            "Handing off..."
          ) : (
            <>
              Hand off to Implementation
              <ArrowRight className="h-4 w-4 ml-1" />
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
