import { toast } from "sonner";
import { bannerShown, setLimit } from "@/lib/limitState";

/** Plan limits: the server answers 402 (or streams a plan_limit event) when a user runs out.
 *  showPlanLimit opens the upgrade popup (PlanLimitDialog); the same message is not also shown as a toast. */
const seen = new Set();
export const PLAN_LIMIT_EVENT = "krish:plan-limit";

export function showPlanLimit(message) {
  if (typeof message !== "string" || !message) return;
  seen.add(message);
  if (/automation/i.test(message)) {
    window.dispatchEvent(new CustomEvent(PLAN_LIMIT_EVENT, { detail: message }));
    return;
  }
  // The meter is used up: the chat shows it as a banner and a card (with when it refills); elsewhere, the popup.
  const popup = () => window.dispatchEvent(new CustomEvent(PLAN_LIMIT_EVENT, { detail: message }));
  import("@/lib/api").then(({ api }) => api.get("/usage")).then(({ data }) => {
    const meter = data?.meter;
    const daily = !!meter?.today && meter.today.used >= meter.today.limit;
    const week = !daily && !!meter && meter.week.used >= meter.week.limit;
    const resetsAt = meter && (daily ? meter.today.resetsAt : week ? meter.week.resetsAt : meter.session.resetsAt);
    if (resetsAt) {
      const span = daily ? 86400 : week ? 7 * 86400 : (meter.session.hours || 5) * 3600;
      setLimit({ kind: "plan", resetsAt, since: resetsAt - span, week, daily, plan: data.plan });
    }
    if (!bannerShown()) popup();
  }).catch(popup);
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
