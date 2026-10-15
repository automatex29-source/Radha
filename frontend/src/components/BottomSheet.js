import * as Dialog from "@radix-ui/react-dialog";

/** A panel that slides up from the bottom of a phone screen, within thumb reach (menus on phones). */
export default function BottomSheet({ open, onOpenChange, title, children, testId }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="krish-fade-in fixed inset-0 z-50 bg-slate-950/45 backdrop-blur-[2px]" />
        <Dialog.Content data-testid={testId} aria-describedby={undefined} onOpenAutoFocus={(e) => e.preventDefault()}
          className="krish-sheet-in fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] overflow-y-auto rounded-t-[28px] border-t border-border bg-background px-5 pb-[calc(env(safe-area-inset-bottom)+20px)] pt-2.5 shadow-[0_-12px_40px_rgba(15,23,42,0.18)] outline-none">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-border" aria-hidden="true" />
          <Dialog.Title className={title ? "mb-3 font-heading text-lg font-semibold text-foreground" : "sr-only"}>{title || "Menu"}</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
