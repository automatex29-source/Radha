import "@/App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import AuthPage from "@/components/AuthPage";
import Workspace from "@/pages/Workspace";
const ProjectsPage = lazy(() => import("@/pages/ProjectsPage"));
const ProjectView = lazy(() => import("@/pages/ProjectView"));
const AppsPage = lazy(() => import("@/pages/AppsPage"));
const AppBuilder = lazy(() => import("@/pages/AppBuilder"));
const AutomationsPage = lazy(() => import("@/pages/AutomationsPage"));
const DecksPage = lazy(() => import("@/pages/DecksPage"));
const DeckEditor = lazy(() => import("@/pages/DeckEditor"));
const HelpPage = lazy(() => import("@/pages/HelpPage"));
const AssistantInvite = lazy(() => import("@/pages/AssistantInvite"));
const DocsPage = lazy(() => import("@/pages/DocsPage"));
const DocEditor = lazy(() => import("@/pages/DocEditor"));
const SharedChat = lazy(() => import("@/pages/SharedChat"));
const PageView = lazy(() => import("@/pages/PageView"));
const DiscoverPage = lazy(() => import("@/pages/DiscoverPage"));
const ResetPassword = lazy(() => import("@/pages/ResetPassword"));
import { Loader2 } from "lucide-react";
import { ThemeProvider } from "next-themes";

// A shared assistant link opened while signed out comes back after signing in.
const AFTER_LOGIN = "krish.afterLogin";

function RememberAssistant() {
  const { code } = useParams();
  try { sessionStorage.setItem(AFTER_LOGIN, `/assistant/${code}`); } catch { /* optional */ }
  return <Navigate to="/login" replace />;
}

function takeRememberedPath() {
  try {
    const path = sessionStorage.getItem(AFTER_LOGIN);
    sessionStorage.removeItem(AFTER_LOGIN);
    if (path && path.startsWith("/assistant/")) return path;
  } catch { /* optional */ }
  return "/";
}

function PageLoading() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background">
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
    </div>
  );
}

function Gate() {
  const { user } = useAuth();

  if (user === null) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background" data-testid="auth-loading">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/assistant/:code" element={<RememberAssistant />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Navigate to={takeRememberedPath()} replace />} />
      <Route path="/" element={<Workspace key="chat" />} />
      <Route path="/counsellor" element={<Workspace key="counsellor" mode="counsellor" />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:id" element={<ProjectView />} />
      <Route path="/apps" element={<AppsPage />} />
      <Route path="/apps/:id" element={<AppBuilder />} />
      <Route path="/decks" element={<DecksPage />} />
      <Route path="/decks/:id" element={<DeckEditor />} />
      <Route path="/automations" element={<AutomationsPage />} />
      <Route path="/help" element={<HelpPage />} />
      <Route path="/discover" element={<DiscoverPage />} />
      <Route path="/assistant/:code" element={<AssistantInvite />} />
      <Route path="/docs" element={<DocsPage />} />
      <Route path="/docs/:id" element={<DocEditor />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem storageKey="radha-theme" disableTransitionOnChange>
      <div className="App">
        <AuthProvider>
          <BrowserRouter>
            {/* Pages other than chat load when first opened, so the app itself starts faster. */}
            <Suspense fallback={<PageLoading />}>
              <Routes>
                {/* Shared chats open for anyone, signed in or not. */}
                <Route path="/share/:shareId" element={<SharedChat />} />
                <Route path="/page/:pageId" element={<PageView />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route path="*" element={<Gate />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
          <Toaster position="top-center" />
        </AuthProvider>
      </div>
    </ThemeProvider>
  );
}
