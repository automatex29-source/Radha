import { useRef, useState } from "react";
import { MapPin, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export const PIN_COLOR = "#8b5cf6";

/**
 * Tap a picture to drop numbered pins, each with a note ("make this bigger", "use my logo here").
 * The App Builder draws the pins onto the picture before sending it, so the AI sees the numbers
 * exactly where the person put them, and the notes go into the message as "1) ... 2) ...".
 */
export default function PictureMarkup({ image, onDone, onClose }) {
  const [pins, setPins] = useState(image.pins || []);
  const [active, setActive] = useState(null);
  const boxRef = useRef(null);
  const noteRefs = useRef({});

  const drop = (e) => {
    const r = boxRef.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    setPins((list) => {
      if (list.length >= 9) return list;
      const next = [...list, { x, y, note: "" }];
      setActive(next.length - 1);
      setTimeout(() => noteRefs.current[next.length - 1]?.focus(), 30);
      return next;
    });
  };

  const setNote = (i, note) => setPins((list) => list.map((p, n) => (n === i ? { ...p, note } : p)));
  const remove = (i) => setPins((list) => list.filter((_, n) => n !== i));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm" data-testid="picture-markup"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex max-h-[94vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <MapPin className="h-4 w-4 text-primary" />
          <p className="flex-1 text-sm font-semibold">Tap the picture to point at what you mean</p>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-3 md:flex-row">
          <div className="flex min-h-0 flex-1 items-start justify-center">
            <div ref={boxRef} onClick={drop} className="relative inline-block cursor-crosshair select-none" data-testid="picture-markup-canvas">
              <img src={image.url} alt={image.name} draggable={false} className="block max-h-[62vh] max-w-full rounded-lg border border-border" />
              {pins.map((p, i) => (
                <button key={i} onClick={(e) => { e.stopPropagation(); setActive(i); noteRefs.current[i]?.focus(); }}
                  style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%`, background: PIN_COLOR }}
                  className={`absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white text-xs font-bold text-white shadow-lg transition-transform ${active === i ? "scale-125" : ""}`}>
                  {i + 1}
                </button>
              ))}
            </div>
          </div>
          <div className="w-full shrink-0 space-y-2 md:w-72">
            {pins.length === 0 && (
              <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                Tap anywhere on the picture to add pin 1, then write what you want there. You can add up to 9 pins.
              </p>
            )}
            {pins.map((p, i) => (
              <div key={i} className={`flex items-start gap-2 rounded-lg border p-2 ${active === i ? "border-primary/60" : "border-border"}`}>
                <span style={{ background: PIN_COLOR }} className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white">{i + 1}</span>
                <textarea ref={(el) => { noteRefs.current[i] = el; }} value={p.note} rows={2} onFocus={() => setActive(i)}
                  onChange={(e) => setNote(i, e.target.value)} placeholder="What should change here?" data-testid={`picture-pin-note-${i + 1}`}
                  className="min-w-0 flex-1 resize-none bg-transparent text-xs focus:outline-none" />
                <button onClick={() => remove(i)} aria-label={`Remove pin ${i + 1}`} className="rounded p-1 text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-2.5">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => onDone(pins)} data-testid="picture-markup-done">Done</Button>
        </div>
      </div>
    </div>
  );
}

/** The picture with its pins drawn on, as a JPEG blob (at most 1600px wide), for the AI to see. */
export async function drawPins(url, pins) {
  const img = await new Promise((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = reject;
    el.src = url;
  });
  const scale = Math.min(1, 1600 / img.naturalWidth);
  const w = Math.round(img.naturalWidth * scale);
  const h = Math.round(img.naturalHeight * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const g = canvas.getContext("2d");
  g.drawImage(img, 0, 0, w, h);
  const r = Math.max(14, Math.round(Math.min(w, h) / 32));
  pins.forEach((p, i) => {
    const x = p.x * w;
    const y = p.y * h;
    g.beginPath();
    g.arc(x, y, r, 0, Math.PI * 2);
    g.fillStyle = PIN_COLOR;
    g.fill();
    g.lineWidth = Math.max(2, r / 5);
    g.strokeStyle = "#ffffff";
    g.stroke();
    g.fillStyle = "#ffffff";
    g.font = `700 ${Math.round(r * 1.1)}px system-ui, sans-serif`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(String(i + 1), x, y + 1);
  });
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
}
