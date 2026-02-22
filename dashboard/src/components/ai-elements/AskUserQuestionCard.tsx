import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { AskUserQuestionPayload } from "@/types/api";
import { CheckIcon } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

export interface AskUserQuestionCardProps {
  payload: AskUserQuestionPayload;
  onAnswer: (answers: Record<string, string | string[]>) => void;
  isSubmitting?: boolean;
  answered?: boolean;
}

export type Selections = Record<string, string | string[]>;

export function AskUserQuestionCard({
  payload,
  onAnswer,
  isSubmitting = false,
  answered = false,
}: AskUserQuestionCardProps) {
  const [selections, setSelections] = useState<Selections>({});
  const [otherTexts, setOtherTexts] = useState<Record<string, string>>({});

  const isDisabled = isSubmitting || answered;

  const handleSelect = useCallback((question: string, label: string, multiSelect: boolean) => {
    if (isDisabled) return;
    setSelections((prev) => {
      if (multiSelect) {
        const current = (prev[question] as string[] | undefined) ?? [];
        const next = current.includes(label)
          ? current.filter((l) => l !== label)
          : [...current, label];
        return { ...prev, [question]: next };
      }
      return { ...prev, [question]: label };
    });
  }, [isDisabled]);

  const handleOtherChange = useCallback((question: string, text: string) => {
    if (isDisabled) return;
    setOtherTexts((prev) => ({ ...prev, [question]: text }));
  }, [isDisabled]);

  // Merge selections and "Other" text input into final answers
  // Precedence rule: If "Other" text exists, it takes priority:
  //   - multi-select: append Other to selected options array
  //   - single-select: Other replaces any selected option
  // Only use selections if no Other text is provided
  const answers = useMemo((): Selections => {
    const result: Selections = {};
    for (const q of payload.questions) {
      const selected = selections[q.question];
      const other = otherTexts[q.question]?.trim();
      if (other) {
        if (q.multi_select) {
          const arr = (selected as string[] | undefined) ?? [];
          result[q.question] = [...arr, other];
        } else {
          result[q.question] = other;
        }
      } else if (selected !== undefined) {
        result[q.question] = selected;
      }
    }
    return result;
  }, [payload.questions, selections, otherTexts]);

  const hasAnswers = Object.keys(answers).length > 0;

  const handleSubmit = () => {
    if (isDisabled) return;
    onAnswer(answers);
  };

  const isSelected = (question: string, label: string, multiSelect: boolean): boolean => {
    const sel = selections[question];
    if (multiSelect) return ((sel as string[] | undefined) ?? []).includes(label);
    return sel === label;
  };

  return (
    <div className={cn("flex flex-col gap-4 rounded-lg border p-4", answered && "opacity-60")}>
      {payload.questions.map((q) => (
        <div key={q.question} className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            {q.header && (
              <Badge variant="secondary" className="text-xs">
                {q.header}
              </Badge>
            )}
            <span className="text-sm font-medium">{q.question}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {q.options.map((opt) => (
              <Button
                key={opt.label}
                variant={isSelected(q.question, opt.label, q.multi_select) ? "default" : "outline"}
                size="sm"
                disabled={isDisabled}
                onClick={() => handleSelect(q.question, opt.label, q.multi_select)}
                className="flex flex-col items-start h-auto py-2 px-3"
              >
                <span className="font-medium">{opt.label}</span>
                {opt.description && (
                  <span className="text-xs font-normal opacity-70">{opt.description}</span>
                )}
              </Button>
            ))}
          </div>
          <Input
            placeholder="Other..."
            value={otherTexts[q.question] ?? ""}
            onChange={(e) => handleOtherChange(q.question, e.target.value)}
            disabled={isDisabled}
            className="max-w-xs text-sm"
            aria-label={`Other answer for: ${q.question}`}
          />
        </div>
      ))}
      {answered ? (
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <CheckIcon className="h-4 w-4" />
          <span>Answered</span>
        </div>
      ) : (
        <Button
          onClick={handleSubmit}
          disabled={isDisabled || !hasAnswers}
          size="sm"
          className="self-start"
        >
          Submit
        </Button>
      )}
    </div>
  );
}
