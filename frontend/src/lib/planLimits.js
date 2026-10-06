import { toast } from "sonner";

/** Plan limits: the server answers 402 (or streams a plan_limit event) when a user runs out.
 *  showPlanLimit opens the upgrade popup (PlanLimitDialog); the same message is not also shown as a toast. */
const seen = new Set();
export const PLAN_LIMIT_EVENT = "krish:plan-limit";

export function showPlanLimit(message) {
  if (typeof message !== "string" || !message) return;
  seen.add(message);
  window.dispatchEvent(new CustomEvent(PLAN_LIMIT_EVENT, { detail: message }));
}

let installed = false;

/** Wrap toast.error once so a plan-limit message, which already opened the popup, isn't shown twice. */
export function installPlanLimitToasts() {
  if (installed) return;
  installed = true;
  const original = toast.error;
  toast.error = (message, options) => {
    if (typeof message === "string" && seen.has(message)) return undefined;
    return original(message, options);
  };
}
