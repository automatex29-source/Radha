import { useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, X } from "lucide-react";

export default function ComposerInput({ value, onChange, onSend, onStop, streaming, disabled }) {
  const ref = useRef(null);

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
          <div className="flex items-center gap-2">
            {value && !streaming && (
              <button onClick={() => onChange("")} data-testid="clear-composer-button"
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
            <span className="hidden text-[11px] text-muted-foreground sm:inline">
              <span className="rounded border border-border bg-secondary px-1 py-0.5 font-mono text-[10px]">Enter</span> to send ·{" "}
              <span className="rounded border border-border bg-secondary px-1 py-0.5 font-mono text-[10px]">Shift+Enter</span> new line
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
