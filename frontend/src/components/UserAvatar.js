import { useState } from "react";

function initialsOf(name, email) {
  const words = (name || "").trim().split(/\s+/).filter((w) => /\p{L}|\p{N}/u.test(w));
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  if (words.length === 1) return [...words[0]].slice(0, 2).join("").toUpperCase();
  return (email || "U")[0].toUpperCase();
}

/** The person's picture: their Google photo, or their initials on a plain, flat circle. */
export default function UserAvatar({ user, className = "h-9 w-9 text-[13px]" }) {
  const [broken, setBroken] = useState(false);
  const photo = user?.picture && !broken ? user.picture : null;
  return (
    <span data-testid="user-avatar"
      className={`inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full bg-slate-800 font-medium tracking-wide text-white dark:bg-slate-200 dark:text-slate-900 ${className}`}>
      {photo
        ? <img src={photo} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-cover" />
        : initialsOf(user?.name, user?.email)}
    </span>
  );
}
