import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { Download, Copy, Share2, Pencil, Sparkles, X, ChevronLeft, ChevronRight, Maximize2, ArrowUp } from "lucide-react";
import { mediaUrl } from "@/lib/api";

/**
 * Pictures Krish made, shown big in the chat: the picture fades in from a blur with a saffron line passing over it
 * (only the first time, right after it is made), a quiet row of actions under it, one-tap changes on the newest
 * reply, and a full screen viewer with every picture from the chat in a strip.
 */

const INLINE_IMAGE = /^image\/(png|jpe?g|gif|webp)$/;
export const isPicture = (m) => INLINE_IMAGE.test(m?.contentType || "");
export const isMadePicture = (m) => isPicture(m) && m.kind === "generated";

// Pictures seen while being made in this session: these get the reveal, older ones just show.
const fresh = new Set();
const revealed = new Set();
export function markFresh(items) { (items || []).forEach((m) => { if (!revealed.has(m.id)) fresh.add(m.id); }); }

// One-tap changes. Each sends a normal message, so it shows in the chat and Krish redraws.
const CHANGES = [
  ["Make it night", "Make this picture at night, with warm lights and a calm mood."],
  ["Add a title", "Add a short, stylish title to this picture that suits it."],
  ["Story size 9:16", "Make the same picture in tall 9:16 story size (1024x1536) for Instagram and WhatsApp status."],
  ["Wide 16:9", "Make the same picture wide (1536x1024) for YouTube and slides."],
  ["Painting style", "Make the same picture as a rich painting."],
  ["Cinematic", "Make the same picture more cinematic, with dramatic light and depth."],
  ["More colourful", "Make this picture brighter and more colourful."],
  ["3D style", "Make the same picture in a clean, premium 3D style."],
];
function changesFor(id) {
  let h = 0; for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  const out = []; for (let i = 0; out.length < 4; i++) { const c = CHANGES[(h + i * 3) % CHANGES.length]; if (!out.includes(c)) out.push(c); }
  return out;
}

async function pictureBlob(item) {
  const res = await fetch(mediaUrl(item.url));
  if (!res.ok) throw new Error("download failed");
  return res.blob();
}

async function copyPicture(item) {
  try {
    let blob = await pictureBlob(item);
    if (blob.type !== "image/png") { // the clipboard takes PNG everywhere
      const bmp = await createImageBitmap(blob); const cv = document.createElement("canvas");
      cv.width = bmp.width; cv.height = bmp.height; cv.getContext("2d").drawImage(bmp, 0, 0);
      blob = await new Promise((r) => cv.toBlob(r, "image/png"));
    }
    await navigator.clipboard.write([new window.ClipboardItem({ "image/png": blob })]);
    toast.success("Picture copied");
  } catch { toast.error("Couldn't copy this picture. Try Download."); }
}

async function sharePicture(item) {
  try {
    const blob = await pictureBlob(item);
    const file = new File([blob], item.name || "krish-picture.png", { type: blob.type || "image/png" });
    if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: item.name || "Picture from Krish" });
    else { await copyPicture(item); }
  } catch (e) { if (e?.name !== "AbortError") toast.error("Couldn't share this picture."); }
}

const canShare = () => typeof navigator !== "undefined" && !!navigator.share;

function ActionButton({ icon: Icon, label, onClick, href, download, testid, dark = false }) {
  const cls = dark
    ? "flex h-10 w-full items-center gap-2.5 rounded-xl border border-white/10 px-3 text-[13px] text-white/85 hover:border-white/25 hover:bg-white/5 max-md:h-14 max-md:flex-col max-md:justify-center max-md:gap-1 max-md:px-1 max-md:text-[11.5px]"
    : "flex h-8 items-center gap-1.5 rounded-lg px-2 text-[12.5px] text-muted-foreground hover:bg-surface hover:text-foreground max-md:min-h-9";
  const inner = <><Icon className={dark ? "h-4 w-4 text-white/60" : "h-3.5 w-3.5"} />{label}</>;
  if (href) return <a href={href} download={download} className={cls} data-testid={testid}>{inner}</a>;
  return <button type="button" onClick={onClick} className={cls} data-testid={testid}>{inner}</button>;
}

function Picture({ item, onView }) {
  const [state, setState] = useState(() => (fresh.has(item.id) && !revealed.has(item.id) ? "waiting" : "plain"));
  const onLoad = () => { if (state === "waiting") { revealed.add(item.id); fresh.delete(item.id); setState("reveal"); } };
  return (
    <button type="button" onClick={() => onView(item)} title="Open full screen" data-krish-pic={item.id}
      className={`krish-pic group/pic ${state === "reveal" ? "is-reveal" : ""} ${state === "waiting" ? "is-waiting" : ""}`}>
      <img src={mediaUrl(item.url)} alt={item.name || "Picture made by Krish"} onLoad={onLoad} draggable={false}
        className="block h-auto max-h-[34rem] w-auto max-w-full" data-testid={`media-image-${item.id}`} />
      <span className="krish-pic-zoom" aria-hidden="true"><Maximize2 className="h-3.5 w-3.5" /></span>
    </button>
  );
}

export function PictureGallery({ items, onAsk }) {
  const [viewing, setViewing] = useState(null);
  const [editFirst, setEditFirst] = useState(false);
  if (!items?.length) return null;
  const last = items[items.length - 1];
  const open = (m, edit = false) => { setEditFirst(edit); setViewing(m); };
  return (
    <div className="mb-3 mt-1 space-y-2" data-testid="message-pictures">
      <div className={items.length > 1 ? "grid grid-cols-2 gap-2" : ""}>
        {items.map((m) => <Picture key={m.id} item={m} onView={open} />)}
      </div>
      <div className="-ml-2 flex flex-wrap items-center gap-0.5" data-testid="picture-actions">
        <ActionButton icon={Download} label="Download" href={mediaUrl(last.url)} download={last.name || true} testid={`media-download-${last.id}`} />
        <ActionButton icon={Copy} label="Copy" onClick={() => copyPicture(last)} testid="picture-copy" />
        {canShare() && <ActionButton icon={Share2} label="Share" onClick={() => sharePicture(last)} testid="picture-share" />}
        {onAsk && <ActionButton icon={Pencil} label="Edit" onClick={() => open(last, true)} testid="picture-edit" />}
        {onAsk && <ActionButton icon={Sparkles} label="More like this" testid="picture-more"
          onClick={() => onAsk("Make another version of this picture, same idea with a fresh take.")} />}
      </div>
      {viewing && <PictureViewer start={viewing} editFirst={editFirst} onAsk={onAsk} onClose={() => setViewing(null)} />}
    </div>
  );
}

// One-tap changes for the newest picture, shown after Krish's words.
export function PictureChanges({ items, onAsk }) {
  if (!items?.length || !onAsk) return null;
  const last = items[items.length - 1];
  return (
    <div className="mt-3 flex flex-wrap gap-1.5" data-testid="picture-changes">
      {changesFor(last.id).map(([label, ask]) => (
        <button key={label} type="button" onClick={() => onAsk(ask)} className="krish-pic-chip">{label}</button>
      ))}
    </div>
  );
}

// Every made picture in the open chat, oldest first, for the viewer's strip.
function chatPictures(start) {
  const seen = new Set(); const list = [];
  document.querySelectorAll("[data-krish-pic]").forEach((el) => {
    const id = el.getAttribute("data-krish-pic"); const img = el.querySelector("img");
    if (!id || seen.has(id) || !img) return; seen.add(id);
    list.push(id === start.id ? start : { id, url: `/api/media/${id}`, name: img.alt, contentType: "image/png", kind: "generated" });
  });
  return list.length ? list : [start];
}

export function PictureViewer({ start, editFirst = false, onAsk, onClose }) {
  const [list] = useState(() => chatPictures(start));
  const [i, setI] = useState(() => Math.max(0, list.findIndex((m) => m.id === start.id)));
  const [change, setChange] = useState("");
  const input = useRef(null);
  const item = list[i] || start;
  const go = useCallback((d) => setI((x) => (x + d + list.length) % list.length), [list.length]);
  useEffect(() => {
    const key = (e) => {
      if (e.target?.tagName === "INPUT") { if (e.key === "Escape") onClose(); return; }
      if (e.key === "Escape") onClose(); else if (e.key === "ArrowRight") go(1); else if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", key); const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    if (editFirst) setTimeout(() => input.current?.focus(), 50);
    return () => { window.removeEventListener("keydown", key); document.body.style.overflow = prev; };
  }, [go, onClose, editFirst]);
  const send = (e) => {
    e.preventDefault(); const text = change.trim(); if (!text || !onAsk) return;
    onAsk(`Edit the picture ${item.name || ""}: ${text}`.replace("  ", " ")); onClose();
  };
  return createPortal(
    <div className="krish-viewer" role="dialog" aria-modal="true" aria-label="Picture viewer" data-testid="picture-viewer">
      <div className="flex h-14 shrink-0 items-center gap-3 px-4 text-[13px] text-white/60 sm:px-6">
        <span className="truncate font-heading text-[15px] font-semibold text-white">{(item.name || "Picture").replace(/\.\w+$/, "")}</span>
        {list.length > 1 && <span className="shrink-0">{i + 1} of {list.length}</span>}
        <button type="button" onClick={onClose} aria-label="Close" data-testid="picture-viewer-close"
          className="ml-auto flex h-9 w-9 items-center justify-center rounded-full text-white/80 hover:bg-white/10"><X className="h-5 w-5" /></button>
      </div>
      <div className="flex min-h-0 flex-1 gap-6 px-3 max-md:flex-col sm:px-6">
        <div className="relative flex min-h-0 flex-1 items-center justify-center">
          {list.length > 1 && <button type="button" onClick={() => go(-1)} aria-label="Previous" className="krish-viewer-nav left-0"><ChevronLeft className="h-5 w-5" /></button>}
          <img key={item.id} src={mediaUrl(item.url)} alt={item.name || "Picture"} className="krish-viewer-img" />
          {list.length > 1 && <button type="button" onClick={() => go(1)} aria-label="Next" className="krish-viewer-nav right-0"><ChevronRight className="h-5 w-5" /></button>}
        </div>
        <div className="flex shrink-0 flex-col gap-2 md:w-60 max-md:grid max-md:grid-cols-3">
          <ActionButton dark icon={Download} label="Download" href={mediaUrl(item.url)} download={item.name || true} />
          <ActionButton dark icon={Copy} label="Copy" onClick={() => copyPicture(item)} />
          {canShare() ? <ActionButton dark icon={Share2} label="Share" onClick={() => sharePicture(item)} />
            : onAsk && <ActionButton dark icon={Sparkles} label="More" onClick={() => { onAsk(`Make another version of the picture ${item.name || ""}, same idea with a fresh take.`); onClose(); }} />}
          {onAsk && (
            <form onSubmit={send} className="mt-2 max-md:col-span-3 max-md:mt-0">
              <label className="mb-1.5 block text-[12px] text-white/50 max-md:hidden">Change something</label>
              <div className="flex items-center gap-1 rounded-xl border border-white/15 bg-white/5 py-1 pl-3 pr-1 focus-within:border-[#FF8A1E]/70">
                <input ref={input} value={change} onChange={(e) => setChange(e.target.value)} placeholder="e.g. sky ko pink karo"
                  className="min-w-0 flex-1 bg-transparent text-[13.5px] text-white outline-none placeholder:text-white/35" data-testid="picture-viewer-edit" />
                <button type="submit" disabled={!change.trim()} aria-label="Change it"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#FF8A1E] text-white disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
              </div>
            </form>
          )}
        </div>
      </div>
      {list.length > 1 && (
        <div className="flex h-20 shrink-0 items-center justify-center gap-2 overflow-x-auto px-4 sm:h-24">
          {list.map((m, k) => (
            <button key={m.id} type="button" onClick={() => setI(k)} aria-label={`Picture ${k + 1}`}
              className={`h-12 w-12 shrink-0 overflow-hidden rounded-lg border-2 sm:h-14 sm:w-14 ${k === i ? "border-[#FF8A1E]" : "border-transparent opacity-60 hover:opacity-100"}`}>
              <img src={mediaUrl(m.url)} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>,
    document.body,
  );
}
