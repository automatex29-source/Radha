import { useNavigate } from "react-router-dom";
import { Check, ChevronDown, Crown } from "lucide-react";
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
      className={`group/model my-0.5 cursor-pointer gap-3 rounded-xl px-2.5 py-2 transition-all focus:bg-primary/[0.07] ${selected ? "bg-primary/[0.09] ring-1 ring-primary/25" : ""}`}>
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 group-hover/model:scale-110 group-focus/model:scale-110 ${
        selected ? "bg-primary text-primary-foreground shadow-sm shadow-primary/30" : "bg-primary/10 text-primary"}`}>
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-foreground">{m.label}</span>
          {m.pro && ready && (
            <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[9px] font-bold uppercase tracking-wide ${
              locked ? "border border-primary/40 text-primary" : "bg-primary/15 text-primary"}`}>
              <Crown className="h-2.5 w-2.5" /> Pro
            </span>
          )}
          {!ready && <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Soon</span>}
        </span>
        <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">{m.description}</span>
      </span>
      <Check className={`h-4 w-4 shrink-0 text-primary transition-opacity ${selected ? "opacity-100" : "opacity-0"}`} />
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

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" data-testid="model-selector-dropdown"
          className="group h-9 gap-2 rounded-full border-white/80 bg-white/80 pl-1.5 pr-3 shadow-sm backdrop-blur transition-all hover:border-primary/40 hover:shadow-md data-[state=open]:border-primary/50 data-[state=open]:ring-2 data-[state=open]:ring-primary/15 dark:border-border dark:bg-card sm:h-10">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/12 text-primary sm:h-7 sm:w-7">
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
