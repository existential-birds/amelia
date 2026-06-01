import { useCallback, useEffect, useRef, useState } from "react";
import { copyToClipboard } from "@/lib/utils";

/**
 * Copies text to the clipboard and exposes a `copied` flag that stays true for
 * `resetMs` after a successful copy, then resets. Clears its pending timeout on
 * unmount to avoid setting state on an unmounted component.
 */
export function useCopyFeedback(content: string, resetMs = 2000) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    const success = await copyToClipboard(content);
    if (success) {
      setCopied(true);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => setCopied(false), resetMs);
    }
  }, [content, resetMs]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return { copied, handleCopy };
}
