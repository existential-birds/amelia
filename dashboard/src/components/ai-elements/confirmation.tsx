/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Compound component for tool approval confirmations.
 *
 * Provides a set of components for displaying tool approval requests,
 * accepted states, rejected states, and action buttons within the AI SDK.
 */
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ToolUIPart } from "ai";
import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useContext,
} from "react";

/**
 * Union type representing tool approval state.
 * Can be pending (no decision), approved, or rejected with optional reason.
 */
type ToolUIPartApproval =
  | {
      id: string;
      approved?: never;
      reason?: never;
    }
  | {
      id: string;
      approved: boolean;
      reason?: string;
    }
  | {
      id: string;
      approved: true;
      reason?: string;
    }
  | {
      id: string;
      approved: true;
      reason?: string;
    }
  | {
      id: string;
      approved: false;
      reason?: string;
    }
  | undefined;

/** Context value for confirmation state sharing. */
type ConfirmationContextValue = {
  approval: ToolUIPartApproval;
  state: ToolUIPart["state"];
};

/** Context for sharing confirmation state between compound components. */
const ConfirmationContext = createContext<ConfirmationContextValue | null>(
  null
);

/**
 * Hook to access confirmation context.
 * @throws Error if used outside of Confirmation component
 * @returns Confirmation context value
 */
const useConfirmation = () => {
  const context = useContext(ConfirmationContext);

  if (!context) {
    throw new Error("Confirmation components must be used within Confirmation");
  }

  return context;
};

/**
 * Props for the Confirmation component.
 * @property approval - Current approval state
 * @property state - Tool UI state from AI SDK
 */
export type ConfirmationProps = ComponentProps<typeof Alert> & {
  approval?: ToolUIPartApproval;
  state: ToolUIPart["state"];
};

/**
 * Container component for tool approval confirmations.
 * Provides context to child components. Hidden during streaming states.
 */
export const Confirmation = ({
  className,
  approval,
  state,
  ...props
}: ConfirmationProps) => {
  if (!approval || state === "input-streaming" || state === "input-available") {
    return null;
  }

  return (
    <ConfirmationContext.Provider value={{ approval, state }}>
      <Alert className={cn("flex flex-col gap-2", className)} {...props} />
    </ConfirmationContext.Provider>
  );
};

/** Props for the ConfirmationTitle component. */
export type ConfirmationTitleProps = ComponentProps<typeof AlertDescription>;

/** Title/description text for the confirmation alert. */
export const ConfirmationTitle = ({
  className,
  ...props
}: ConfirmationTitleProps) => (
  <AlertDescription className={cn("inline", className)} {...props} />
);

/** Props for the ConfirmationRequest component. */
export type ConfirmationRequestProps = {
  children?: ReactNode;
};

/** Shows children only when approval is requested (awaiting decision). */
export const ConfirmationRequest = ({ children }: ConfirmationRequestProps) => {
  const { state } = useConfirmation();

  // Only show when approval is requested
  // @ts-expect-error state only available in AI SDK v6
  if (state !== "approval-requested") {
    return null;
  }

  return children;
};

/** Props for the ConfirmationAccepted component. */
export type ConfirmationAcceptedProps = {
  children?: ReactNode;
};

/** Shows children only when approval was accepted. */
export const ConfirmationAccepted = ({
  children,
}: ConfirmationAcceptedProps) => {
  const { approval, state } = useConfirmation();

  // Only show when approved and in response states
  if (
    !approval?.approved ||
        // @ts-expect-error state only available in AI SDK v6
    (state !== "approval-responded" &&
        // @ts-expect-error state only available in AI SDK v6
      state !== "output-denied" &&
      state !== "output-available")
  ) {
    return null;
  }

  return children;
};

/** Props for the ConfirmationRejected component. */
export type ConfirmationRejectedProps = {
  children?: ReactNode;
};

/** Shows children only when approval was rejected. */
export const ConfirmationRejected = ({
  children,
}: ConfirmationRejectedProps) => {
  const { approval, state } = useConfirmation();

  // Only show when rejected and in response states
  if (
    approval?.approved !== false ||
        // @ts-expect-error state only available in AI SDK v6
    (state !== "approval-responded" &&
        // @ts-expect-error state only available in AI SDK v6
      state !== "output-denied" &&
      state !== "output-available")
  ) {
    return null;
  }

  return children;
};

/** Props for the ConfirmationActions component. */
export type ConfirmationActionsProps = ComponentProps<"div">;

/** Container for action buttons, visible only when approval is requested. */
export const ConfirmationActions = ({
  className,
  ...props
}: ConfirmationActionsProps) => {
  const { state } = useConfirmation();

  // Only show when approval is requested
  // @ts-expect-error state only available in AI SDK v6
  if (state !== "approval-requested") {
    return null;
  }

  return (
    <div
      className={cn("flex items-center justify-end gap-2 self-end", className)}
      {...props}
    />
  );
};

/** Props for the ConfirmationAction button. */
export type ConfirmationActionProps = ComponentProps<typeof Button>;

/** Action button for approve/reject actions. */
export const ConfirmationAction = (props: ConfirmationActionProps) => (
  <Button className="h-8 px-3 text-sm" type="button" {...props} />
);
