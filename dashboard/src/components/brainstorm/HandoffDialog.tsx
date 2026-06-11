import { useState, useEffect } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BrainstormArtifact } from "@/types/api";

interface HandoffDialogProps {
  open: boolean;
  artifact: BrainstormArtifact | null;
  onConfirm: (issueTitle: string) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function HandoffDialog({
  open,
  artifact,
  onConfirm,
  onCancel,
  isLoading = false,
}: HandoffDialogProps) {
  const [issueTitle, setIssueTitle] = useState("");

  useEffect(() => {
    if (artifact?.title) {
      setIssueTitle(`Implement ${artifact.title}`);
    } else {
      setIssueTitle("");
    }
  }, [artifact]);

  const handleConfirm = () => {
    onConfirm(issueTitle);
  };

  return (
    <AlertDialog open={open}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Hand off to Implementation</AlertDialogTitle>
          <AlertDialogDescription>
            This will create a new implementation workflow from your design
            document.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4">
          <Label htmlFor="issue-title">Issue title (optional)</Label>
          <Input
            id="issue-title"
            value={issueTitle}
            onChange={(e) => setIssueTitle(e.target.value)}
            placeholder="Implement feature..."
            className="mt-2"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? "Creating..." : "Create Workflow →"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
