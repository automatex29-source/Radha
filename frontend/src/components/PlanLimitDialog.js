import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Crown } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PLAN_LIMIT_EVENT } from "@/lib/planLimits";

/** Pops up by itself when the user runs out of something on their plan, with a way to see the plans. */
export default function PlanLimitDialog() {
  const navigate = useNavigate();
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const onLimit = (e) => setMessage(e.detail);
    window.addEventListener(PLAN_LIMIT_EVENT, onLimit);
    return () => window.removeEventListener(PLAN_LIMIT_EVENT, onLimit);
  }, []);

  return (
    <Dialog open={!!message} onOpenChange={(o) => !o && setMessage(null)}>
      <DialogContent className="max-w-[22rem] rounded-3xl p-7 max-sm:w-[calc(100%-2rem)]" data-testid="plan-limit-dialog">
        <DialogHeader className="items-center text-center sm:text-center">
          <div className="mb-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-[0_10px_30px_-8px_rgba(99,102,241,0.6)]">
            <Crown className="h-6 w-6 text-white" />
          </div>
          <DialogTitle className="text-[1.35rem] font-extrabold tracking-tight">You've reached your limit</DialogTitle>
          <DialogDescription className="pt-1 text-[0.9rem] leading-relaxed">{message}</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex flex-col gap-2">
          <Button onClick={() => { setMessage(null); navigate("/plans"); }} data-testid="plan-limit-see-plans"
            className="h-11 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 font-semibold text-white hover:opacity-95">
            See plans
          </Button>
          <Button variant="ghost" onClick={() => setMessage(null)} className="h-10 rounded-xl text-muted-foreground">Maybe later</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
