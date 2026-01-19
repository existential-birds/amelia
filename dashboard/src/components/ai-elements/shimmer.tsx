/**
 * @fileoverview Animated text shimmer effect component.
 */

import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import {
  type CSSProperties,
  type ElementType,
  type JSX,
  memo,
  useMemo,
} from "react";

/**
 * Props for the Shimmer component.
 * @property children - Text content to animate
 * @property as - HTML element type to render (default: 'p')
 * @property className - Optional additional CSS classes
 * @property duration - Animation duration in seconds (default: 4)
 * @property spread - Shimmer spread factor (default: 2)
 */
export type TextShimmerProps = {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
};

/**
 * Renders text with an animated shimmer highlight effect.
 *
 * Uses Framer Motion to animate a gradient highlight across the text.
 * Spread is calculated based on text length for consistent appearance.
 *
 * @param props - Component props
 * @returns The shimmer text element
 */
const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 4,
  spread = 2,
}: TextShimmerProps) => {
  const MotionComponent = motion.create(
    Component as keyof JSX.IntrinsicElements
  );

  const dynamicSpread = useMemo(
    () => (children?.length ?? 0) * spread,
    [children, spread]
  );

  return (
    <MotionComponent
      animate={{ backgroundPosition: "0% center" }}
      className={cn(
        "relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent",
        "[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-foreground),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]",
        className
      )}
      initial={{ backgroundPosition: "100% center" }}
      style={
        {
          "--spread": `${dynamicSpread}px`,
          backgroundImage:
            "var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))",
        } as CSSProperties
      }
      transition={{
        repeat: Number.POSITIVE_INFINITY,
        duration,
        ease: "linear",
      }}
    >
      {children}
    </MotionComponent>
  );
};

/** Memoized shimmer text component for performance. */
export const Shimmer = memo(ShimmerComponent);
