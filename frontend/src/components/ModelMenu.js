import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronDown, Crown } from "lucide-react";
import BottomSheet from "@/components/BottomSheet";
import { usePhone } from "@/hooks/usePhone";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { modelIcon } from "@/lib/models";

function Row({ m, selected, ready, locked, onPick }) {
  const Icon = modelIcon(m.id);
  return (
    <DropdownMenuItem data-testid={`model-option-${m.id}`} disabled={!ready} onSelect={() => onPick(m)}
      className={`group/model my-0.5 cursor-pointer gap-3 rounded-xl px-2.5 py-2 transition-all focus:bg-[#F2650F]/[0.07] ${selected ? "bg-[#F2650F]/[0.09] ring-1 ring-[#F2650F]/25" : ""}`}>
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 group-hover/model:scale-110 group-focus/model:scale-110 ${
        selected ? "bg-gradient-to-br from-[#FFB547] via-[#FF8A1E] to-[#F2650F] text-white shadow-sm shadow-[#FF8A1E]/40" : "bg-[#F2650F]/10 text-[#F2650F]"}`}>
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-foreground">{m.label}</span>
          {m.pro && ready && (
            <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[9px] font-bold uppercase tracking-wide ${
              locked ? "border border-[#F2650F]/40 text-[#F2650F]" : "bg-[#F2650F]/15 text-[#F2650F]"}`}>
              <Crown className="h-2.5 w-2.5" /> Pro
            </span>
          )}
          {!ready && <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Soon</span>}
        </span>
        <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">{m.description}</span>
      </span>
      <Check className={`h-4 w-4 shrink-0 text-[#F2650F] transition-opacity ${selected ? "opacity-100" : "opacity-0"}`} />
    </DropdownMenuItem>
  );
}

/** The chat's model picker: Krish names, an icon and one plain line each, with Pro models grouped below. */
export default function ModelMenu({ models, model, setModel, caps, label }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const paidPlan = user?.plan === "pro" || user?.plan === "max";
  const current = models.find((m) => m.id === model);
  const Icon = modelIcon(model);
  const ready = (m) => !caps || !!caps.agent?.[m.id];
  const pick = (m) => (m.pro && !paidPlan ? navigate("/plans") : setModel(m.id));
  const groups = [["Everyday", models.filter((m) => !m.pro)], ["Pro models", models.filter((m) => m.pro)]].filter(([, list]) => list.length);
  const phone = usePhone();
  const [open, setOpen] = useState(false);

  if (phone) {
    const available = models.filter(ready);
    const soon = models.filter((m) => !ready(m));
    return (
      <>
        <button onClick={() => setOpen(true)} data-testid="model-selector-dropdown" aria-haspopup="dialog"
          className="flex h-9 min-w-0 items-center gap-1.5 rounded-full bg-surface px-3.5 text-[15px] font-semibold text-foreground active:scale-[0.98]">
          <span className="h-2 w-2 shrink-0 rounded-full bg-gradient-to-br from-[#FFB547] to-[#F2650F]" />
          <span className="truncate">{current?.label || label}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
        <BottomSheet open={open} onOpenChange={setOpen} title="Choose a model" testId="model-sheet">
          <div className="space-y-2.5">
            {available.map((m) => {
              const MIcon = modelIcon(m.id);
              const selected = m.id === model;
              const locked = m.pro && !paidPlan;
              return (
                <button key={m.id} role="menuitemradio" aria-checked={selected} data-testid={`model-option-${m.id}`}
                  onClick={() => { setOpen(false); pick(m); }}
                  className={`flex w-full items-center gap-3.5 rounded-2xl border p-3.5 text-left transition-colors ${
                    selected ? "border-2 border-primary bg-primary/[0.06]" : "border-border"}`}>
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#FFB547] via-[#FF8A1E] to-[#F2650F] text-white shadow-sm shadow-[#FF8A1E]/40">
                    <MIcon className="h-5 w-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-base font-semibold text-foreground">
                      {m.label}
                      {m.pro && <span className="inline-flex items-center gap-0.5 rounded-full bg-[#F2650F]/15 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-[#F2650F]"><Crown className="h-2.5 w-2.5" /> Pro</span>}
                    </span>
                    <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">{locked ? "Upgrade to use this model" : m.description}</span>
                  </span>
                  {selected && <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"><Check className="h-3.5 w-3.5" /></span>}
                </button>
              );
            })}
          </div>
          {soon.length > 0 && (
            <details className="group/soon mt-1.5" data-testid="model-sheet-soon">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-1 py-3 text-sm text-muted-foreground">
                <span className="truncate"><b className="font-semibold text-foreground">Coming soon</b> · {soon.map((m) => m.label.replace(/^Krish\s+/, "")).join(", ")}</span>
                <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open/soon:rotate-180" />
              </summary>
              <div className="space-y-1 pb-1">
                {soon.map((m) => {
                  const MIcon = modelIcon(m.id);
                  return (
                    <div key={m.id} className="flex items-center gap-3 rounded-xl px-2 py-2 opacity-60">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F2650F]/10 text-[#F2650F]"><MIcon className="h-4 w-4" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-foreground">{m.label}</span>
                        <span className="block text-xs text-muted-foreground">{m.description}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </details>
          )}
          {!paidPlan && (
            <button onClick={() => { setOpen(false); navigate("/plans"); }} data-testid="model-sheet-upgrade"
              className="mt-2 flex w-full items-center justify-between gap-3 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 px-4 py-3.5 text-left text-white shadow-[0_10px_24px_rgba(99,102,241,0.35)]">
              <span>
                <span className="block font-semibold">Krish Pro</span>
                <span className="block text-[13px] text-white/85">Smarter models, more chats</span>
              </span>
              <span className="rounded-full bg-white px-3.5 py-1.5 text-[13px] font-semibold text-indigo-600">Upgrade</span>
            </button>
          )}
        </BottomSheet>
      </>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" data-testid="model-selector-dropdown"
          className="group h-9 gap-2 rounded-full border-white/80 bg-white/80 pl-1.5 pr-3 shadow-sm backdrop-blur transition-all hover:border-[#F2650F]/40 hover:shadow-md data-[state=open]:border-[#F2650F]/50 data-[state=open]:ring-2 data-[state=open]:ring-[#F2650F]/15 dark:border-border dark:bg-card sm:h-10">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#F2650F]/12 text-[#F2650F] sm:h-7 sm:w-7">
            <Icon className="h-3.5 w-3.5" />
          </span>
          <span className="max-w-[92px] truncate text-xs font-semibold sm:max-w-none">{current?.label || label}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl p-1.5 shadow-xl">
        {groups.map(([title, list], i) => (
          <div key={title}>
            {i > 0 && <DropdownMenuSeparator className="my-1.5" />}
            <DropdownMenuLabel className="px-2.5 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{title}</DropdownMenuLabel>
            {list.map((m) => (
              <Row key={m.id} m={m} selected={m.id === model} ready={ready(m)} locked={m.pro && !paidPlan} onPick={pick} />
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
