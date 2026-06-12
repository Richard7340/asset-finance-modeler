import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { animate, motionEnabled } from "../anim";

type Props = {
  children: ReactNode;
  /** Delay before the rise begins (ms). Use for manual sequencing. */
  delay?: number;
  /** Duration of the rise (ms). */
  duration?: number;
  className?: string;
  /** Render as a different element (e.g. "tr", "section"). */
  as?: keyof React.JSX.IntrinsicElements;
  /** Translate distance in px. */
  y?: number;
};

/**
 * Fade + rise an element into place on mount. Degrades to plain (already
 * visible) content when motion is unavailable — the `.rise` class defaults to
 * the visible state, and we only "arm" the hidden state when we know we can
 * animate, so tests never see hidden content.
 */
export default function Reveal({
  children,
  delay = 0,
  duration = 380,
  className = "",
  as = "div",
  y = 8,
}: Props) {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !motionEnabled()) return;
    el.style.opacity = "0";
    el.style.transform = `translateY(${y}px)`;
    const anim = animate(el, {
      opacity: [0, 1],
      translateY: [y, 0],
      duration,
      delay,
      ease: "out(3)",
    });
    return () => {
      anim.pause();
      el.style.opacity = "";
      el.style.transform = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const Tag = as as React.ElementType;
  return (
    <Tag ref={ref} className={className}>
      {children}
    </Tag>
  );
}

/**
 * Stagger-reveal direct children of a container on mount. Attaches to the
 * container ref and animates its element children with a stagger.
 */
export function useStaggerReveal<T extends HTMLElement>(
  deps: unknown[] = [],
  opts: { y?: number; duration?: number; gap?: number; selector?: string } = {},
) {
  const ref = useRef<T | null>(null);
  const { y = 8, duration = 360, gap = 45, selector } = opts;

  useEffect(() => {
    const el = ref.current;
    if (!el || !motionEnabled()) return;
    const children = Array.from(
      selector ? el.querySelectorAll(selector) : el.children,
    ) as HTMLElement[];
    if (children.length === 0) return;

    const anim = animate(children, {
      opacity: [0, 1],
      translateY: [y, 0],
      duration,
      delay: (_: unknown, i: number) => i * gap,
      ease: "out(3)",
    });
    return () => {
      anim.pause();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}
