import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { animate, motionEnabled } from "../anim";

/**
 * Quick fade/slide whenever `viewKey` changes (e.g. portfolio ↔ detail).
 * Degrades to an instant swap when motion is unavailable.
 */
export default function ViewTransition({
  viewKey,
  children,
}: {
  viewKey: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !motionEnabled()) return;
    const anim = animate(el, {
      opacity: [0, 1],
      translateY: [6, 0],
      duration: 280,
      ease: "out(3)",
    });
    return () => {
      anim.pause();
    };
  }, [viewKey]);

  return (
    <div ref={ref} className="flex min-h-0 flex-1 flex-col">
      {children}
    </div>
  );
}
