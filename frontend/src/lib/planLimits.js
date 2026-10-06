import { toast } from "sonner";

/** Messages the server sent with status 402 (a plan limit). A toast showing one gets a "See plans" button. */
const seen = new Set();

export function rememberPlanLimit(message) {
  if (typeof message === "string" && message) seen.add(message);
}

let installed = false;

/** Wrap toast.error once so every plan-limit message, wherever it is shown, links to the Plans page. */
export function installPlanLimitToasts() {
  if (installed) return;
  installed = true;
  const original = toast.error;
  toast.error = (message, options) => {
    if (typeof message !== "string" || !seen.has(message)) return original(message, options);
    return original(message, {
      duration: 8000,
      ...options,
      id: "plan-limit",
      action: { label: "See plans", onClick: () => window.location.assign("/plans") },
    });
  };
}
