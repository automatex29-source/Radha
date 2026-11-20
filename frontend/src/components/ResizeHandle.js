import { useCallback, useEffect, useRef, useState } from "react";

/** A width in pixels that is remembered in this browser (per `key`), kept between `min` and `max`. */
export function useStoredWidth(key, initial, min, max) {
  const clamp = useCallback((w) => Math.round(Math.min(Math.max(w, min), typeof max === "function" ? max() : max)), [min, max]);
  const [width, setWidth] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      return saved > 0 ? saved : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback((w) => {
    const next = clamp(w);
    setWidth(next);
    try { localStorage.setItem(key, String(next)); } catch { /* private window: the width just isn't remembered */ }
  }, [key, clamp]);
  // A smaller window (or a remembered width from a bigger screen) still leaves room for the other side.
  useEffect(() => {
    const fit = () => setWidth((w) => clamp(w));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [clamp]);
  return [width, set];
}

/**
 * A drag handle between two panes (laptops and tablets; phones show one pane at a time).
 * `side` is where the resized pane is: "left" (the handle is on its right edge) or "right" (on its left edge).
 * Drag it, use the arrow keys, or double-click it to go back to `initial`.
 */
export default function ResizeHandle({ width, onWidth, side = "left", initial, label = "Drag to resize", className = "" }) {
  const start = useRef(null);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    start.current = { x: e.clientX, width };
    setDragging(true);
  };
  useEffect(() => {
    if (!dragging) return undefined;
    const move = (e) => {
      const dx = e.clientX - start.current.x;
      onWidth(start.current.width + (side === "left" ? dx : -dx));
    };
    const up = () => setDragging(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [dragging, onWidth, side]);

  const onKeyDown = (e) => {
    const step = e.shiftKey ? 80 : 24;
    if (e.key === "ArrowLeft") { e.preventDefault(); onWidth(width + (side === "left" ? -step : step)); }
    if (e.key === "ArrowRight") { e.preventDefault(); onWidth(width + (side === "left" ? step : -step)); }
  };

  return (
    <>
      <div role="separator" aria-orientation="vertical" aria-label={label} aria-valuenow={width} tabIndex={0} title={label}
        onPointerDown={onPointerDown} onKeyDown={onKeyDown} onDoubleClick={() => initial && onWidth(initial)}
        data-testid="resize-handle"
        className={`group relative z-20 w-0 shrink-0 cursor-col-resize select-none focus:outline-none max-md:hidden ${className}`}>
        {/* A wide invisible grip around a thin line that lights up on hover and while dragging. */}
        <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
        <span className={`pointer-events-none absolute inset-y-0 -left-px w-[3px] transition-colors ${dragging ? "bg-primary" : "bg-transparent group-hover:bg-primary/60 group-focus-visible:bg-primary"}`} />
        <span className={`pointer-events-none absolute left-1/2 top-1/2 h-9 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-border bg-card shadow-sm transition-opacity ${dragging ? "opacity-100" : "opacity-70 group-hover:opacity-100"}`} />
      </div>
      {/* While dragging, a cover over the page keeps the preview's iframe from swallowing the mouse. */}
      {dragging && <div className="fixed inset-0 z-[60] cursor-col-resize" />}
    </>
  );
}
