import { useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, X, Paperclip, FileText, Loader2 } from "lucide-react";

export default function ComposerInput({
  value, onChange, onSend, onStop, streaming, disabled,
  onAttach, attachments = [], onRemoveAttachment, uploading,
}) {
  const ref = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!streaming) onSend();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-5 pt-1">
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2" data-testid="composer-attachments">
          {attachments.map((a) => (
            <div key={a.id} className="flex items-center gap-1.5 rounded-lg border border-[#262C3E] bg-[#171B26] px-2.5 py-1.5 text-xs">
              {a.status === "processing" ? <Loader2 className="h-3 w-3 animate-spin text-amber-400" /> : <FileText className="h-3 w-3 text-primary" />}
              <span className="max-w-[160px] truncate text-foreground">{a.filename}</span>
              <button onClick={() => onRemoveAttachment?.(a.id)} data-testid={`remove-attachment-${a.id}`} className="text-muted-foreground hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="rounded-2xl border border-[#222738] bg-[#11141D] p-2 shadow-[0_8px_40px_rgba(0,0,0,0.4)] transition-colors focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/40">
        <textarea
          ref={ref}
          data-testid="message-composer-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Message RADHA…"
          className="radha-scroll max-h-[200px] w-full resize-none bg-transparent px-3 py-2 text-[0.95rem] text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        <div className="flex items-center justify-between px-1 pt-1">
          <div className="flex items-center gap-1">
            {onAttach && (
              <>
                <input ref={fileRef} type="file" className="hidden" data-testid="composer-file-input"
                  accept=".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.markdown,.json,.log"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) onAttach(f); if (fileRef.current) fileRef.current.value = ""; }} />
                <button onClick={() => fileRef.current?.click()} disabled={uploading || disabled} data-testid="composer-attach-button" title="Attach a document"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-[#171B26] hover:text-foreground disabled:opacity-50">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </button>
              </>
            )}
            {value && !streaming && (
              <button onClick={() => onChange("")} data-testid="clear-composer-button"
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
            <span className="ml-1 hidden text-[11px] text-muted-foreground sm:inline">
              <span className="rounded border border-border bg-secondary px-1 py-0.5 font-mono text-[10px]">Enter</span> to send
            </span>
          </div>
          {streaming ? (
            <Button size="icon" variant="secondary" onClick={onStop} data-testid="stop-generation-button" className="h-9 w-9 rounded-xl">
              <Square className="h-4 w-4" />
            </Button>
          ) : (
            <Button size="icon" onClick={onSend} disabled={!value.trim() || disabled} data-testid="send-message-button"
              className="h-9 w-9 rounded-xl shadow-[0_0_20px_rgba(99,102,241,0.4)]">
              <ArrowUp className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-muted-foreground">RADHA can make mistakes. Verify important information.</p>
    </div>
  );
}
