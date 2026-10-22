import { Component } from "react";
import { reportError } from "@/lib/crashReport";

const RELOADED = "krish.chunkReload";

// After a new deploy, an open tab still asks for the old page files, which no longer exist.
function isStaleBuild(error) {
  const msg = String(error?.message || error || "");
  return /dynamically imported module|Importing a module script failed|Loading chunk|ChunkLoadError|error loading dynamically/i.test(msg);
}

/** Shows a friendly "Reload" screen instead of a blank page when something crashes.
 *  When the crash is an old tab missing files after a new deploy, it reloads once by itself. */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    if (isStaleBuild(error)) {
      try {
        if (!sessionStorage.getItem(RELOADED)) {
          sessionStorage.setItem(RELOADED, "1");
          window.location.reload();
          return;
        }
      } catch { /* optional */ }
    }
    console.error(error);
    reportError(error, info?.componentStack || "");
  }

  componentDidMount() {
    try { setTimeout(() => sessionStorage.removeItem(RELOADED), 10000); } catch { /* optional */ }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground" data-testid="crash-screen">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="max-w-sm text-sm text-muted-foreground">Krish AI hit a problem showing this page. Your chats are saved. Reload to carry on.</p>
        <button type="button" onClick={() => window.location.reload()}
          className="rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white">Reload</button>
      </div>
    );
  }
}
