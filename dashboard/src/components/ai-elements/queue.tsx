/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Queue UI components for displaying task lists and messages.
 *
 * Compound components for building queue interfaces with items,
 * collapsible sections, attachments, and todo-style task lists.
 */
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { ChevronDownIcon, PaperclipIcon } from "lucide-react";
import type { ComponentProps } from "react";

/**
 * Represents a part of a queue message.
 * @property type - Content type identifier
 * @property text - Optional text content
 * @property url - Optional URL for links/media
 * @property filename - Optional filename for attachments
 * @property mediaType - Optional MIME type
 */
export type QueueMessagePart = {
  type: string;
  text?: string;
  url?: string;
  filename?: string;
  mediaType?: string;
};

/**
 * Represents a complete queue message.
 * @property id - Unique message identifier
 * @property parts - Array of message parts
 */
export type QueueMessage = {
  id: string;
  parts: QueueMessagePart[];
};

/**
 * Represents a todo item in the queue.
 * @property id - Unique todo identifier
 * @property title - Todo title text
 * @property description - Optional description
 * @property status - Todo completion status
 */
export type QueueTodo = {
  id: string;
  title: string;
  description?: string;
  status?: "pending" | "completed";
};

/** Props for QueueItem component. */
export type QueueItemProps = ComponentProps<"li">;

/** List item container for queue entries with hover effects. */
export const QueueItem = ({ className, ...props }: QueueItemProps) => (
  <li
    className={cn(
      "group flex flex-col gap-1 rounded-md px-3 py-1 text-sm transition-colors hover:bg-muted",
      className
    )}
    {...props}
  />
);

/**
 * Props for QueueItemIndicator component.
 * @property completed - Whether the item is marked as complete
 */
export type QueueItemIndicatorProps = ComponentProps<"span"> & {
  completed?: boolean;
};

/** Circular indicator showing completion status. */
export const QueueItemIndicator = ({
  completed = false,
  className,
  ...props
}: QueueItemIndicatorProps) => (
  <span
    className={cn(
      "mt-0.5 inline-block size-2.5 rounded-full border",
      completed
        ? "border-muted-foreground/20 bg-muted-foreground/10"
        : "border-muted-foreground/50",
      className
    )}
    {...props}
  />
);

/**
 * Props for QueueItemContent component.
 * @property completed - Whether to show strikethrough style
 */
export type QueueItemContentProps = ComponentProps<"span"> & {
  completed?: boolean;
};

/** Text content for queue items with completion styling. */
export const QueueItemContent = ({
  completed = false,
  className,
  ...props
}: QueueItemContentProps) => (
  <span
    className={cn(
      "line-clamp-1 grow break-words",
      completed
        ? "text-muted-foreground/50 line-through"
        : "text-muted-foreground",
      className
    )}
    {...props}
  />
);

/**
 * Props for QueueItemDescription component.
 * @property completed - Whether to show completed styling
 */
export type QueueItemDescriptionProps = ComponentProps<"div"> & {
  completed?: boolean;
};

/** Secondary description text for queue items. */
export const QueueItemDescription = ({
  completed = false,
  className,
  ...props
}: QueueItemDescriptionProps) => (
  <div
    className={cn(
      "ml-6 text-xs",
      completed
        ? "text-muted-foreground/40 line-through"
        : "text-muted-foreground",
      className
    )}
    {...props}
  />
);

/** Props for QueueItemActions container. */
export type QueueItemActionsProps = ComponentProps<"div">;

/** Container for queue item action buttons. */
export const QueueItemActions = ({
  className,
  ...props
}: QueueItemActionsProps) => (
  <div className={cn("flex gap-1", className)} {...props} />
);

/** Props for QueueItemAction button. */
export type QueueItemActionProps = Omit<
  ComponentProps<typeof Button>,
  "variant" | "size"
>;

/** Ghost button for queue item actions, visible on hover. */
export const QueueItemAction = ({
  className,
  ...props
}: QueueItemActionProps) => (
  <Button
    className={cn(
      "size-auto rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted-foreground/10 hover:text-foreground group-hover:opacity-100",
      className
    )}
    size="icon"
    type="button"
    variant="ghost"
    {...props}
  />
);

/** Props for QueueItemAttachment container. */
export type QueueItemAttachmentProps = ComponentProps<"div">;

/** Container for file/image attachments on queue items. */
export const QueueItemAttachment = ({
  className,
  ...props
}: QueueItemAttachmentProps) => (
  <div className={cn("mt-1 flex flex-wrap gap-2", className)} {...props} />
);

/** Props for QueueItemImage thumbnail. */
export type QueueItemImageProps = ComponentProps<"img">;

/** Image thumbnail for attachment preview. */
export const QueueItemImage = ({
  className,
  ...props
}: QueueItemImageProps) => (
  <img
    alt=""
    className={cn("h-8 w-8 rounded border object-cover", className)}
    height={32}
    width={32}
    {...props}
  />
);

/** Props for QueueItemFile badge. */
export type QueueItemFileProps = ComponentProps<"span">;

/** File attachment badge with paperclip icon. */
export const QueueItemFile = ({
  children,
  className,
  ...props
}: QueueItemFileProps) => (
  <span
    className={cn(
      "flex items-center gap-1 rounded border bg-muted px-2 py-1 text-xs",
      className
    )}
    {...props}
  >
    <PaperclipIcon size={12} />
    <span className="max-w-[100px] truncate">{children}</span>
  </span>
);

/** Props for QueueList scrollable container. */
export type QueueListProps = ComponentProps<typeof ScrollArea>;

/** Scrollable list container for queue items. */
export const QueueList = ({
  children,
  className,
  ...props
}: QueueListProps) => (
  <ScrollArea className={cn("-mb-1 mt-2", className)} {...props}>
    <div className="max-h-40 pr-4">
      <ul>{children}</ul>
    </div>
  </ScrollArea>
);

/** Props for QueueSection collapsible container. */
export type QueueSectionProps = ComponentProps<typeof Collapsible>;

/** Collapsible section container for grouping queue items. */
export const QueueSection = ({
  className,
  defaultOpen = true,
  ...props
}: QueueSectionProps) => (
  <Collapsible className={cn(className)} defaultOpen={defaultOpen} {...props} />
);

/** Props for QueueSectionTrigger button. */
export type QueueSectionTriggerProps = ComponentProps<"button">;

/** Button trigger for collapsing/expanding queue sections. */
export const QueueSectionTrigger = ({
  children,
  className,
  ...props
}: QueueSectionTriggerProps) => (
  <CollapsibleTrigger asChild>
    <button
      className={cn(
        "group flex w-full items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-left font-medium text-muted-foreground text-sm transition-colors hover:bg-muted",
        className
      )}
      type="button"
      {...props}
    >
      {children}
    </button>
  </CollapsibleTrigger>
);

/**
 * Props for QueueSectionLabel component.
 * @property count - Item count to display
 * @property label - Label text
 * @property icon - Optional icon element
 */
export type QueueSectionLabelProps = ComponentProps<"span"> & {
  count?: number;
  label: string;
  icon?: React.ReactNode;
};

/** Label with chevron, optional icon, and count for section headers. */
export const QueueSectionLabel = ({
  count,
  label,
  icon,
  className,
  ...props
}: QueueSectionLabelProps) => (
  <span className={cn("flex items-center gap-2", className)} {...props}>
    <ChevronDownIcon className="group-data-[state=closed]:-rotate-90 size-4 transition-transform" />
    {icon}
    <span>
      {count} {label}
    </span>
  </span>
);

/** Props for QueueSectionContent area. */
export type QueueSectionContentProps = ComponentProps<
  typeof CollapsibleContent
>;

/** Collapsible content area for section items. */
export const QueueSectionContent = ({
  className,
  ...props
}: QueueSectionContentProps) => (
  <CollapsibleContent className={cn(className)} {...props} />
);

/** Props for Queue root container. */
export type QueueProps = ComponentProps<"div">;

/** Root container for queue UI with border and shadow. */
export const Queue = ({ className, ...props }: QueueProps) => (
  <div
    className={cn(
      "flex flex-col gap-2 rounded-xl border border-border bg-background px-3 pt-2 pb-2 shadow-xs",
      className
    )}
    {...props}
  />
);
