import { Sun, CloudSun, Cloud, CloudFog, CloudDrizzle, CloudRain, CloudSnow, CloudLightning, Droplets, Wind, TrendingUp, TrendingDown } from "lucide-react";

// Live answer cards, like Perplexity's: weather (Open-Meteo) and stock prices (Yahoo Finance).

function weatherIcon(code) {
  if (code === 0 || code === 1) return Sun;
  if (code === 2) return CloudSun;
  if (code === 3) return Cloud;
  if (code === 45 || code === 48) return CloudFog;
  if (code >= 51 && code <= 57) return CloudDrizzle;
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return CloudRain;
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return CloudSnow;
  if (code >= 95) return CloudLightning;
  return CloudSun;
}

const dayName = (iso, i) => (i === 0 ? "Today"
  : new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" }));

export function WeatherCard({ card }) {
  const Icon = weatherIcon(card.code);
  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-border bg-card" data-testid="weather-card">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 bg-gradient-to-br from-sky-500/15 via-indigo-500/10 to-transparent px-4 py-4">
        <div className="flex items-center gap-3">
          <Icon className="h-12 w-12 text-sky-500 dark:text-sky-300" strokeWidth={1.5} />
          <div>
            <p className="text-4xl font-semibold leading-none tabular-nums text-foreground">{card.temp}°<span className="text-xl text-muted-foreground">C</span></p>
            <p className="mt-1 text-sm text-muted-foreground">{card.label}</p>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{card.place}</p>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>Feels like {card.feels}°</span>
            {card.humidity != null && <span className="flex items-center gap-1"><Droplets className="h-3 w-3" /> {card.humidity}%</span>}
            {card.wind != null && <span className="flex items-center gap-1"><Wind className="h-3 w-3" /> {Math.round(card.wind)} km/h</span>}
          </p>
        </div>
      </div>
      {card.days?.length > 0 && (
        <div className="grid grid-cols-5 divide-x divide-border border-t border-border">
          {card.days.slice(0, 5).map((d, i) => {
            const DayIcon = weatherIcon(d.code);
            return (
              <div key={d.date} className="flex flex-col items-center gap-1 px-1 py-2.5 text-center" title={d.label}>
                <span className="text-[11px] font-medium text-muted-foreground">{dayName(d.date, i)}</span>
                <DayIcon className="h-5 w-5 text-sky-500 dark:text-sky-300" strokeWidth={1.75} />
                <span className="text-xs tabular-nums text-foreground">{d.max}° <span className="text-muted-foreground">{d.min}°</span></span>
                {d.rain != null && <span className="text-[10px] tabular-nums text-sky-600 dark:text-sky-300">{d.rain}%</span>}
              </div>
            );
          })}
        </div>
      )}
      <p className="border-t border-border px-4 py-1.5 text-[10px] text-muted-foreground">Weather from Open-Meteo</p>
    </div>
  );
}

function Sparkline({ points, up }) {
  if (!points || points.length < 2) return null;
  const w = 320, h = 80, pad = 4;
  const lo = Math.min(...points), hi = Math.max(...points);
  const span = hi - lo || 1;
  const xy = points.map((p, i) => [pad + (i * (w - 2 * pad)) / (points.length - 1), pad + (1 - (p - lo) / span) * (h - 2 * pad)]);
  const line = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${xy[xy.length - 1][0].toFixed(1)} ${h} L${xy[0][0].toFixed(1)} ${h} Z`;
  const color = up ? "rgb(16 185 129)" : "rgb(244 63 94)";
  const [ex, ey] = xy[xy.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-20 w-full" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={`spark-${up ? "up" : "down"}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${up ? "up" : "down"})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={ex} cy={ey} r="3" fill={color} />
    </svg>
  );
}

const money = (n, currency) => {
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : undefined, currency ? { style: "currency", currency, maximumFractionDigits: 2 } : { maximumFractionDigits: 2 }).format(n);
  } catch { return n.toLocaleString(); }
};

export function StockCard({ card }) {
  const up = card.change >= 0;
  const Trend = up ? TrendingUp : TrendingDown;
  return (
    <a href={card.url} target="_blank" rel="noopener noreferrer" data-testid="stock-card"
      className="mb-3 block overflow-hidden rounded-2xl border border-border bg-card px-4 pt-3.5 transition-colors hover:border-primary/40">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{card.name}</p>
          <p className="text-[11px] text-muted-foreground">{[card.symbol, card.exchange].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold tabular-nums text-foreground">{money(card.price, card.currency)}</p>
          <p className={`flex items-center justify-end gap-1 text-xs font-semibold tabular-nums ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
            <Trend className="h-3.5 w-3.5" /> {up ? "+" : ""}{card.change} ({up ? "+" : ""}{card.changePct}%) today
          </p>
        </div>
      </div>
      <Sparkline points={card.points} up={card.points?.length > 1 ? card.points[card.points.length - 1] >= card.points[0] : up} />
      <p className="flex justify-between border-t border-border py-1.5 text-[10px] text-muted-foreground">
        <span>Last month</span><span>Yahoo Finance · may be delayed</span>
      </p>
    </a>
  );
}

export function LiveCards({ items }) {
  if (!items?.length) return null;
  return items.map((c, i) => (c.type === "weather" ? <WeatherCard key={i} card={c} /> : c.type === "stock" ? <StockCard key={i} card={c} /> : null));
}
