import { useCallback, useRef, useState } from "react";

type Props = {
  /** Current width (px) of the panel to the LEFT of this divider. */
  width: number;
  /** Commit a new width while dragging (clamped by the consumer/hook). */
  onResize: (px: number) => void;
  /** Accessible label, e.g. "Redimensionar navegador". */
  label: string;
};

/**
 * A thin draggable vertical divider sitting between two columns. Dragging it
 * resizes the column immediately to its left. Uses pointer events with pointer
 * capture so the drag keeps tracking even if the cursor outruns the handle.
 *
 * Visual: a 1px hairline that gains an accent line on hover/active, with a
 * `col-resize` cursor. Width changes flow up via `onResize` (state only — no
 * model recalc). Only meaningful in the `lg:` three-column layout; hidden when
 * the grid stacks (the parent renders it inside `hidden lg:flex`).
 */
export default function ResizeDivider({ width, onResize, label }: Props) {
  const [active, setActive] = useState(false);
  const start = useRef<{ x: number; w: number } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      start.current = { x: e.clientX, w: width };
      setActive(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [width],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!start.current) return;
      const dx = e.clientX - start.current.x;
      onResize(start.current.w + dx);
    },
    [onResize],
  );

  const end = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    start.current = null;
    setActive(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // capture may already be gone
    }
  }, []);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      className="group relative z-10 flex w-1.5 shrink-0 cursor-col-resize touch-none select-none items-stretch"
    >
      {/* Hairline base + accent on hover/active. */}
      <span
        aria-hidden
        className={`mx-auto h-full w-px transition-colors ${
          active
            ? "w-0.5 bg-accent-500"
            : "bg-slate-200 group-hover:w-0.5 group-hover:bg-accent-400"
        }`}
      />
    </div>
  );
}
