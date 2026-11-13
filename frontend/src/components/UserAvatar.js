import { useState } from "react";

// Soft two-tone gradients; each person always gets the same one (picked from their name or email).
const TONES = [
  "from-indigo-500 via-violet-500 to-fuchsia-500",
  "from-sky-500 via-blue-500 to-indigo-600",
  "from-emerald-400 via-teal-500 to-cyan-600",
  "from-amber-400 via-orange-500 to-rose-500",
  "from-rose-400 via-pink-500 to-purple-600",
  "from-cyan-400 via-sky-500 to-violet-600",
];
const RINGS = {
  pro: "ring-2 ring-indigo-400/70 ring-offset-2 ring-offset-background dark:ring-indigo-300/60",
  max: "ring-2 ring-amber-400/80 ring-offset-2 ring-offset-background dark:ring-amber-300/70",
};

function initialsOf(name, email) {
  const words = (name || "").trim().split(/\s+/).filter((w) => /\p{L}|\p{N}/u.test(w));
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  if (words.length === 1) return [...words[0]].slice(0, 2).join("").toUpperCase();
  return (email || "U")[0].toUpperCase();
}

function toneOf(key) {
  let h = 0;
  for (const ch of key || "") h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return TONES[h % TONES.length];
}

/** The person's picture: their Google photo, or their initials on a glossy gradient. Pro and Max get a coloured ring. */
export default function UserAvatar({ user, className = "h-9 w-9 text-[13px]", ring = false }) {
  const [broken, setBroken] = useState(false);
  const photo = user?.picture && !broken ? user.picture : null;
  const planRing = ring ? RINGS[user?.plan] || "" : "";
  return (
    <span data-testid="user-avatar"
      className={`relative inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full font-semibold tracking-tight text-white shadow-[0_2px_8px_-2px_rgba(15,23,42,0.35)] ${planRing} ${className}`}>
      {photo ? (
        <img src={photo} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <>
          <span className={`absolute inset-0 bg-gradient-to-br ${toneOf(user?.email || user?.name)}`} />
          {/* A soft light from the top left and a thin inner edge make it read as a polished chip, not a flat dot. */}
          <span className="absolute inset-0 bg-[radial-gradient(circle_at_30%_22%,rgba(255,255,255,0.45),transparent_55%)]" />
          <span className="relative drop-shadow-[0_1px_1px_rgba(0,0,0,0.25)]">{initialsOf(user?.name, user?.email)}</span>
        </>
      )}
      <span className="pointer-events-none absolute inset-0 rounded-full ring-1 ring-inset ring-white/25" />
    </span>
  );
}
