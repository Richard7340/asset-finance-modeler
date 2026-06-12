import { useEffect, useRef, useState } from "react";
import { animate, motionEnabled } from "../anim";

type Props = {
  /** The numeric target value to display. */
  value: number;
  /** Format the (possibly mid-tween) number into display text. */
  format: (n: number) => string;
  /** Animation duration in ms. */
  duration?: number;
  className?: string;
};

/**
 * Count-up number. On mount it tweens from 0 → value; on subsequent value
 * changes it tweens from the previous value → new value, so the user SEES the
 * model move after a recalc / asset switch.
 *
 * In tests / SSR / reduced-motion it renders the final formatted value
 * immediately as plain text (no animation), so assertions can find it.
 */
export default function AnimatedNumber({
  value,
  format,
  duration = 700,
  className,
}: Props) {
  const safeValue = Number.isFinite(value) ? value : 0;
  // Initialise display to the final value so the very first render (and all
  // non-browser renders) already show the correct text.
  const [display, setDisplay] = useState<number>(safeValue);
  const prev = useRef<number>(safeValue);

  useEffect(() => {
    const from = prev.current;
    const to = Number.isFinite(value) ? value : 0;
    prev.current = to;

    if (!motionEnabled() || from === to) {
      setDisplay(to);
      return;
    }

    const obj = { v: from };
    const anim = animate(obj, {
      v: to,
      duration,
      ease: "out(3)",
      onUpdate: () => setDisplay(obj.v),
      onComplete: () => setDisplay(to),
    });
    return () => {
      anim.pause();
      setDisplay(to);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  // Non-finite targets format through the formatter too (e.g. "—").
  const out = Number.isFinite(value) ? format(display) : format(value);
  return <span className={className}>{out}</span>;
}
