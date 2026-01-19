import { useState, useCallback, useRef, useEffect } from "react";
import { cn, copyToClipboard } from "@/lib/utils";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

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
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    const success = await copyToClipboard(content);
    if (success) {
      setCopied(true);
      // Clear any existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => setCopied(false), 2000);
    }
  }, [content]);

  // Clean up timeout on unmount to prevent memory leak
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

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
