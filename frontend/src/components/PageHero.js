import PageScene from "@/components/PageScene";
import "@/lib/page-scenes.css";

// Each page's two accent colours: its banner, animation, main button and sidebar button use them.
const ACCENTS = {
  chat: ["#6366F1", "#8B5CF6"],
  docs: ["#6366F1", "#8B5CF6"],
  decks: ["#F43F5E", "#FB923C"],
  apps: ["#3B82F6", "#06B6D4"],
  automations: ["#10B981", "#84CC16"],
  projects: ["#D946EF", "#A855F7"],
  discover: ["#F59E0B", "#F97316"],
  counsellor: ["#14B8A6", "#38BDF8"],
};

/** Put on a page's outer box so everything inside (the banner, `kb-btn` buttons) gets the page's colours. */
export const accentStyle = (scene) => {
  const [a, b] = ACCENTS[scene] || ACCENTS.docs;
  return { "--ka1": a, "--ka2": b };
};

/**
 * The page banner: deep colour in the page's accents with drifting light, a big title, and a
 * looping animation of what the page does (see PageScene). `overlap` leaves room at the bottom
 * for a `kb-float` card that sits over the banner's lower edge.
 */
export default function PageHero({ icon: Icon, title, subtitle, children, scene, overlap = false, compact = false, testid }) {
  return (
    <div data-testid={testid} style={accentStyle(scene)}
      className={`kb-hero radha-fade-up rounded-3xl text-left ${compact ? "px-4 py-3" : `px-4 pt-4 sm:px-7 sm:pt-5 ${overlap ? "pb-12 sm:pb-14" : "pb-4 sm:pb-5"}`}`}>
      <div className="kb-blobs" aria-hidden="true"><i /><i /><i /></div>
      <div className="kb-grid" aria-hidden="true" />
      <div className="kb-shine" aria-hidden="true" />
      <div className="flex items-center gap-3 sm:gap-6">
        <div className="min-w-0 flex-1">
          {Icon && (
            <span className={`kb-pill items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${compact ? "hidden" : "hidden sm:inline-flex"}`}>
              <Icon className="h-3.5 w-3.5" /> Krish {title}
            </span>
          )}
          <h1 className={`kb-title ${compact ? "text-2xl" : "text-[1.7rem] sm:mt-2 sm:text-[2.4rem]"}`}>{title}</h1>
          {subtitle && <p className={`mt-1.5 max-w-md leading-snug text-white/80 ${compact ? "line-clamp-2 text-xs" : "line-clamp-2 text-[13px] sm:line-clamp-none sm:text-sm"}`}>{subtitle}</p>}
          {children && <div className="mt-3 flex flex-wrap gap-2">{children}</div>}
        </div>
        {scene && <PageScene name={scene} className={`shrink-0 ${compact ? "!w-[120px]" : "!w-[128px] sm:!w-[230px] md:!w-[280px]"}`} />}
      </div>
    </div>
  );
}
