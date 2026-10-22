import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

// Google's own "Sign in with Google" button (Google Identity Services), shown only when the server has a
// GOOGLE_CLIENT_ID. Google gives back a signed token, which the server checks (backend/google_signin.py).
let gisScript;
function loadGoogle() {
  if (window.google?.accounts?.id) return Promise.resolve();
  gisScript = gisScript || new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = resolve;
    s.onerror = () => { gisScript = null; reject(new Error("Google sign-in couldn't load")); };
    document.head.appendChild(s);
  });
  return gisScript;
}

export default function GoogleButton({ clientId, onCredential, text = "continue_with" }) {
  const box = useRef(null);
  const handler = useRef(onCredential);
  handler.current = onCredential;
  const { resolvedTheme } = useTheme();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let gone = false;
    loadGoogle().then(() => {
      if (gone || !box.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (res) => res?.credential && handler.current(res.credential),
        ux_mode: "popup",
        use_fedcm_for_prompt: true,
      });
      box.current.innerHTML = "";
      window.google.accounts.id.renderButton(box.current, {
        type: "standard", theme: resolvedTheme === "dark" ? "filled_black" : "outline", size: "large",
        text, shape: "pill", logo_alignment: "center", width: Math.min(400, box.current.offsetWidth || 320),
      });
    }).catch(() => !gone && setFailed(true));
    return () => { gone = true; };
  }, [clientId, resolvedTheme, text]);

  if (failed) return null;
  return <div ref={box} className="flex min-h-[44px] w-full justify-center" data-testid="google-signin-button" />;
}
