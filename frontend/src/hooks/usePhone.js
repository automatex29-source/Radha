import { useEffect, useState } from "react";

const QUERY = "(max-width: 639px)";

/** True on phone-width screens, kept up to date when the window is resized or the phone is turned. */
export function usePhone() {
  const get = () => typeof window !== "undefined" && !!window.matchMedia?.(QUERY).matches;
  const [phone, setPhone] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia?.(QUERY);
    if (!mq) return undefined;
    const on = () => setPhone(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return phone;
}
