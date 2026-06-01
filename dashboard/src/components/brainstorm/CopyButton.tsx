import { cn } from "@/lib/utils";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCopyFeedback } from "@/hooks/useCopyFeedback";

interface CopyButtonProps {
  content: string;
  className?: string;
}

/**
 * Compact copy button for message bubbles.
 *
 * - Shows on hover on desktop
 * - Always visible on touch devices (mobile/iOS)
 * - Uses iOS-compatible clipboard handling
 */
export function CopyButton({ content, className }: CopyButtonProps) {
  const { copied, handleCopy } = useCopyFeedback(content);

  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn(
        "h-6 w-6 shrink-0",
        "text-muted-foreground/50 hover:text-muted-foreground",
        "hover:bg-muted/50 transition-colors",
        // Desktop: show on hover via group-hover
        // Mobile: always visible (touch devices don't have hover)
        "opacity-0 group-hover:opacity-100 touch:opacity-100",
        className
      )}
      onClick={handleCopy}
      aria-label={copied ? "Copied" : "Copy message"}
    >
      {copied ? (
        <Check className="h-3 w-3 text-emerald-500" />
      ) : (
        <Copy className="h-3 w-3" />
      )}
    </Button>
  );
}
