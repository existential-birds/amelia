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
  const [state, setState] = useState<{ selections: Selections; otherTexts: Record<string, string> }>({
    selections: {},
    otherTexts: {},
  });

  const isDisabled = isSubmitting || answered;

  const handleSelect = useCallback((question: string, label: string, multiSelect: boolean) => {
    if (isDisabled) return;
    setState((prev) => {
      if (multiSelect) {
        const current = (prev.selections[question] as string[] | undefined) ?? [];
        const next = current.includes(label)
          ? current.filter((l) => l !== label)
          : [...current, label];
        return { ...prev, selections: { ...prev.selections, [question]: next } };
      }
      return { ...prev, selections: { ...prev.selections, [question]: label } };
    });
  }, [isDisabled]);

  const handleOtherChange = useCallback((question: string, text: string) => {
    if (isDisabled) return;
    setState((prev) => ({ ...prev, otherTexts: { ...prev.otherTexts, [question]: text } }));
  }, [isDisabled]);

  // Merge selections and "Other" text input into final answers
  // Precedence rule: If "Other" text exists, it takes priority:
  //   - multi-select: append Other to selected options array
  //   - single-select: Other replaces any selected option
  // Only use selections if no Other text is provided
  const answers = useMemo((): Selections => {
    return payload.questions.reduce<Selections>((acc, q) => {
      const selected = state.selections[q.question];
      const other = state.otherTexts[q.question]?.trim();
      if (other) {
        acc[q.question] = q.multi_select
          ? [...((selected as string[] | undefined) ?? []), other]
          : other;
      } else if (selected !== undefined) {
        acc[q.question] = selected;
      }
      return acc;
    }, {});
  }, [payload.questions, state.selections, state.otherTexts]);

  const hasAnswers = Object.keys(answers).length > 0;

  const handleSubmit = () => {
    if (isDisabled) return;
    onAnswer(answers);
  };

  const isSelected = (question: string, label: string, multiSelect: boolean): boolean => {
    const sel = state.selections[question];
    if (multiSelect) return ((sel as string[] | undefined) ?? []).includes(label);
    return sel === label;
  };

  return (
    <div className={cn("flex flex-col gap-4 rounded-lg border p-4", answered && "bg-card/60")}>

      {payload.questions.map((q) => (
        <fieldset key={q.id} className="flex flex-col gap-2" disabled={isDisabled}>
          <legend className="flex items-center gap-2">
            {q.header && (
              <Badge variant="secondary" className="text-xs">
                {q.header}
              </Badge>
            )}
            <span className="text-sm font-medium">{q.question}</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {q.options.map((opt) => (
              <Button
                key={opt.label}
                variant={isSelected(q.question, opt.label, q.multi_select) ? "default" : "outline"}
                size="sm"
                disabled={isDisabled}
                onClick={() => handleSelect(q.question, opt.label, q.multi_select)}
                className="flex flex-col items-start h-auto py-2 px-3"
                aria-pressed={q.multi_select ? isSelected(q.question, opt.label, q.multi_select) : undefined}
                aria-label={`${opt.label}${opt.description ? `: ${opt.description}` : ""}`}
              >
                <span className="font-medium">{opt.label}</span>
                {opt.description && (
                  <span className="text-xs font-normal opacity-70">{opt.description}</span>
                )}
              </Button>
            ))}
          </div>
          <label htmlFor={`other-${q.question}`} className="flex flex-col gap-1 max-w-xs">
            <span className="text-xs text-muted-foreground">Other</span>
            <Input
              id={`other-${q.question}`}
              placeholder="Other..."
              value={state.otherTexts[q.question] ?? ""}
              onChange={(e) => handleOtherChange(q.question, e.target.value)}
              disabled={isDisabled}
              className="text-sm"
              aria-label={`Other answer for: ${q.question}`}
            />
          </label>
        </fieldset>
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
