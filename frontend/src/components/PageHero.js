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
      className={`kb-hero radha-fade-up rounded-[1.75rem] text-left ${compact ? "px-4 pb-4 pt-3" : `px-5 pt-4 sm:px-9 sm:pt-8 ${overlap ? "pb-16 sm:pb-20" : "pb-5 sm:pb-8"}`}`}>
      <div className="kb-blobs" aria-hidden="true"><i /><i /><i /></div>
      <div className="kb-grid" aria-hidden="true" />
      <div className="kb-shine" aria-hidden="true" />
      <div className={`grid items-center ${compact ? "gap-1" : "gap-2 md:grid-cols-[1fr_1.05fr] md:gap-6"}`}>
        {scene && <PageScene name={scene} className={compact ? "mx-auto max-w-[300px]" : "max-md:mx-auto max-md:max-w-[380px] md:order-last"} />}
        <div className="min-w-0">
          {Icon && (
            <span className="kb-pill inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold">
              <Icon className="h-3.5 w-3.5" /> Krish {title}
            </span>
          )}
          <h1 className={`kb-title ${compact ? "mt-2 text-3xl" : "mt-3 text-4xl sm:mt-4 sm:text-[3.4rem]"}`}>{title}</h1>
          {subtitle && <p className={`mt-2 max-w-md leading-relaxed text-white/80 ${compact ? "text-[13px]" : "text-sm sm:mt-3 sm:text-[15px]"}`}>{subtitle}</p>}
          {children && <div className="mt-4 flex flex-wrap gap-2">{children}</div>}
        </div>
      </div>
    </div>
  );
}
