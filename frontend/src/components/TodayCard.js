import { useEffect, useState } from "react";
import { Flame, Newspaper, Sparkles, Sunrise } from "lucide-react";
import { api } from "@/lib/api";
import { askText } from "@/components/TopStories";

// Aaj (Today): a small card on the home screen. Today's tithi and festival, the Gita line of the day, one
// headline and the days-in-a-row count (backend: GET /api/today, no AI used). Each part starts a chat about it.
const KEY = "krish.today";

function cached() {
  try {
    const hit = JSON.parse(sessionStorage.getItem(KEY) || "null");
    return hit && hit.date === new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }) ? hit : null;
  } catch { return null; }
}

export default function TodayCard({ onPick }) {
  const [day, setDay] = useState(cached);
  useEffect(() => {
    if (day) return;
    let live = true;
    api.get("/today").then(({ data }) => {
      if (!live || !data) return;
      setDay(data);
      try { sessionStorage.setItem(KEY, JSON.stringify(data)); } catch { /* shown, just not kept */ }
    }).catch(() => { /* the home screen works without it */ });
    return () => { live = false; };
  }, [day]);

  if (!day) return <div className="mt-3 h-[68px] rounded-2xl border border-border bg-card/40 sm:h-[60px]" aria-hidden="true" />;
  const p = day.panchang;
  const festival = p?.festivals?.[0];
  const streak = day.streak?.days || 0;
  const askDay = () => onPick(festival
    ? `Aaj ${festival} hai. Tell me its story, why we celebrate it and how, in short.`
    : `Today is ${p?.tithi} in ${p?.month}. What is special about this day and is there anything I should do?`);

  return (
    <div data-testid="today-card" className="radha-fade-up mt-3 overflow-hidden rounded-2xl border border-border bg-card/70 shadow-sm backdrop-blur-sm">
      <div className="flex items-stretch divide-x divide-border max-sm:flex-col max-sm:divide-x-0 max-sm:divide-y">
        <button onClick={askDay} data-testid="today-panchang" disabled={!p}
          className="flex min-w-0 shrink-0 items-center gap-2.5 px-3.5 py-2.5 text-left transition hover:bg-muted/50 sm:max-w-[45%]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 text-white">
            <Sunrise className="h-[18px] w-[18px]" />
          </span>
          <span className="min-w-0">
            <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Aaj · {day.weekday}, {day.dateLabel}
            </span>
            <span className="block truncate text-[13px] font-semibold text-foreground">
              {festival ? <span className="text-orange-600 dark:text-orange-300">🪔 {festival}</span>
                : p ? <>{p.tithi}<span className="font-normal text-muted-foreground"> · {p.month}</span></> : "Have a good day"}
            </span>
          </span>
          {streak > 1 && (
            <span data-testid="today-streak" title={`You've opened Krish ${streak} days in a row`}
              className="ml-auto flex shrink-0 items-center gap-0.5 rounded-full bg-orange-500/10 px-2 py-0.5 text-[11px] font-bold text-orange-600 dark:text-orange-300 sm:hidden">
              <Flame className="h-3 w-3" /> {streak}
            </span>
          )}
        </button>
        <button onClick={() => onPick(`Explain Bhagavad Gita ${day.verse.ref} simply: "${day.verse.text}" How can I use it in my life today?`)}
          data-testid="today-verse" className="flex min-w-0 flex-1 items-center gap-2 px-3.5 py-2.5 text-left transition hover:bg-muted/50">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
          <span className="line-clamp-2 text-[12.5px] leading-snug text-muted-foreground">
            <span className="text-foreground">{day.verse.text}</span> <span className="whitespace-nowrap font-medium">Gita {day.verse.ref}</span>
          </span>
        </button>
        {day.news && (
          <button onClick={() => onPick(askText(day.news))} data-testid="today-news"
            className="flex min-w-0 flex-1 items-center gap-2 px-3.5 py-2.5 text-left transition hover:bg-muted/50 max-lg:hidden">
            <Newspaper className="h-3.5 w-3.5 shrink-0 text-sky-500" />
            <span className="line-clamp-2 text-[12.5px] leading-snug text-foreground">{day.news.title}</span>
          </button>
        )}
        {streak > 1 && (
          <div data-testid="today-streak-wide" title={`You've opened Krish ${streak} days in a row. Best: ${day.streak.best}`}
            className="flex shrink-0 flex-col items-center justify-center px-3 max-sm:hidden">
            <span className="flex items-center gap-0.5 text-sm font-bold text-orange-600 dark:text-orange-300"><Flame className="h-4 w-4" />{streak}</span>
            <span className="text-[10px] text-muted-foreground">days</span>
          </div>
        )}
      </div>
    </div>
  );
}
