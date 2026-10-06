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
      <DialogContent className="max-w-sm" data-testid="plan-limit-dialog">
        <DialogHeader>
          <div className="mx-auto mb-1 flex h-11 w-11 items-center justify-center rounded-full bg-primary/10">
            <Crown className="h-5 w-5 text-primary" />
          </div>
          <DialogTitle className="text-center">You've reached your limit</DialogTitle>
          <DialogDescription className="text-center">{message}</DialogDescription>
        </DialogHeader>
        <div className="mt-2 flex flex-col gap-2">
          <Button onClick={() => { setMessage(null); navigate("/plans"); }} data-testid="plan-limit-see-plans">See plans</Button>
          <Button variant="ghost" onClick={() => setMessage(null)}>Maybe later</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
