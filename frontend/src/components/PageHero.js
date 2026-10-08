/**
 * The animated header used at the top of each page: drifting colour light, a faint dot grid,
 * and a floating icon with dots circling it (the same look as the chat home's hero).
 */
export default function PageHero({ icon: Icon, title, subtitle, children, center = false, compact = false, testid }) {
  return (
    <div data-testid={testid}
      className={`krish-hero radha-fade-up relative overflow-hidden rounded-3xl border border-border bg-card/60 ${compact ? "px-4 py-4" : "px-5 py-5 sm:px-8 sm:py-7"}`}>
      <div className="krish-aurora" aria-hidden="true"><span /><span /><span /></div>
      <div className="krish-hero-grid" aria-hidden="true" />
      <div className={`relative flex gap-4 ${center ? "flex-col items-center text-center" : "flex-col sm:flex-row sm:items-center"}`}>
        {Icon && (
          <div className={`relative shrink-0 ${compact ? "h-12 w-12" : "h-14 w-14 sm:h-16 sm:w-16"}`}>
            <div className="krish-orbit !inset-[-10px]" aria-hidden="true"><i /><i /><i /></div>
            <div className="krish-float relative flex h-full w-full items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-black/10">
              <Icon className={compact ? "h-5 w-5" : "h-6 w-6 sm:h-7 sm:w-7"} />
            </div>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h1 className={`font-semibold tracking-tight text-foreground ${compact ? "text-xl" : "text-2xl sm:text-3xl"}`}>{title}</h1>
          {subtitle && <p className={`mt-1.5 text-sm leading-relaxed text-muted-foreground ${center ? "mx-auto max-w-xl" : "max-w-2xl"}`}>{subtitle}</p>}
        </div>
        {children && <div className="relative shrink-0">{children}</div>}
      </div>
    </div>
  );
}
