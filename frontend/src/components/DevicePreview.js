// The page drawn at real laptop and phone sizes and shrunk to fit, like screenshots that stay live. The user's own
// browser draws them, so they cost nothing to run. Tapping the card opens the full preview.

function MiniScreen({ url, srcDoc, reloadKey, width, height, scale, label, className }) {
  return (
    <figure className="flex flex-col items-center gap-1">
      <div className={`overflow-hidden border-2 border-border-strong bg-white shadow-sm ${className}`}
        style={{ width: width * scale + 4, height: height * scale + 4 }}>
        {/* No allow-same-origin: the page can't touch Krish AI's storage or session. */}
        <iframe key={reloadKey} src={url} srcDoc={srcDoc} title={`${label} preview`} loading="lazy" tabIndex={-1}
          aria-hidden="true" sandbox="allow-scripts allow-forms" scrolling="no"
          style={{ width, height, transform: `scale(${scale})`, transformOrigin: "0 0", pointerEvents: "none", border: 0 }} />
      </div>
      <figcaption className="text-[10px] text-muted-foreground">{label}</figcaption>
    </figure>
  );
}

export default function DevicePreview({ url, srcDoc, reloadKey = 0, onOpen, className = "" }) {
  const screen = { url, srcDoc, reloadKey, height: 800, scale: 0.16 };
  return (
    <button onClick={onOpen} title="Open the preview" data-testid="device-preview"
      className={`flex items-end gap-3 rounded-xl border border-border bg-card p-3 text-left hover:border-primary/50 ${className}`}>
      <MiniScreen {...screen} width={1280} label="Laptop" className="rounded-md" />
      <MiniScreen {...screen} width={390} label="Phone" className="rounded-xl" />
    </button>
  );
}
