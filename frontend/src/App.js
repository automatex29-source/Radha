import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import AuthPage from "@/components/AuthPage";
import Workspace from "@/pages/Workspace";
import { Loader2 } from "lucide-react";

function Gate() {
  const { user } = useAuth();

  if (user === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" data-testid="auth-loading">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <AuthPage />} />
      <Route path="/" element={user ? <Workspace /> : <Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <div className="App dark">
      <AuthProvider>
        <BrowserRouter>
          <Gate />
        </BrowserRouter>
        <Toaster position="top-center" theme="dark" />
      </AuthProvider>
    </div>
  );
}
