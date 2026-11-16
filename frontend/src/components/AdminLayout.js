import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, useLocation } from "react-router-dom";
import {
  Activity, AlertTriangle, ArrowLeft, BarChart3, LayoutDashboard, Menu, MessageCircleQuestion, ShieldCheck, Tag,
  ThumbsUp, Users, X,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";
import ThemeToggle from "@/components/ThemeToggle";

export const ADMIN_NAV = [
  ["Insights", [
    ["/admin", "Overview", LayoutDashboard, true],
    ["/admin/activity", "Activity", Activity],
    ["/admin/questions", "Questions", MessageCircleQuestion],
    ["/admin/usage", "Daily usage", BarChart3],
  ]],
  ["People", [
    ["/admin/users", "Users", Users],
    ["/admin/answers", "Answer ratings", ThumbsUp],
  ]],
  ["Manage", [
    ["/admin/problems", "Problems", AlertTriangle],
    ["/admin/codes", "Offer codes", Tag],
  ]],
];

function NavItems({ onPick }) {
  return (
    <nav className="flex flex-col gap-5">
      {ADMIN_NAV.map(([group, items]) => (
        <div key={group}>
          <p className="px-3 pb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">{group}</p>
          <div className="flex flex-col gap-0.5">
            {items.map(([to, label, Icon, end]) => (
              <NavLink key={to} to={to} end={end} onClick={onPick} data-testid={`admin-nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
                className={({ isActive }) => `group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  isActive ? "bg-foreground text-background shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
                <Icon className="h-4 w-4 shrink-0" />{label}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <Link to="/admin" className="flex items-center gap-2.5" data-testid="admin-brand">
      <BrandMark className="h-8 w-8" />
      <span className="leading-tight">
        <span className="block text-[14px] font-bold tracking-tight">Krish Admin</span>
        <span className="flex items-center gap-1 text-[10.5px] font-medium text-muted-foreground"><ShieldCheck className="h-3 w-3" />Owner console</span>
      </span>
    </Link>
  );
}

/** The owner's own console: a separate layout from the chat app, with its own menu (a sidebar on laptops, a
 *  drawer on phones). Only the owner can open it. */
export default function AdminLayout({ title, subtitle, actions, children, wide = true }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  if (!user?.isOwner) return <Navigate to="/" replace />;

  const footer = (
    <div className="mt-auto space-y-2 border-t border-border/70 pt-4">
      <div className="flex items-center gap-2.5 px-1">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">{(user.name || user.email || "?")[0].toUpperCase()}</span>
        <div className="min-w-0 flex-1"><p className="truncate text-[12.5px] font-semibold">{user.name || "Owner"}</p><p className="truncate text-[11px] text-muted-foreground">{user.email}</p></div>
        <ThemeToggle />
      </div>
      <Link to="/" className="flex items-center gap-2 rounded-lg px-3 py-2 text-[12.5px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground" data-testid="admin-back-to-app">
        <ArrowLeft className="h-4 w-4" /> Back to Krish AI
      </Link>
    </div>
  );

  return (
    <div className="owner-viz flex h-dvh w-full overflow-hidden bg-[var(--viz-page)] text-foreground" data-testid="admin-layout">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border/70 bg-card px-3 py-5 lg:flex">
        <div className="px-2 pb-6"><Brand /></div>
        <NavItems />
        {footer}
      </aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-card px-3 py-5 shadow-2xl">
            <div className="flex items-center justify-between px-2 pb-6"><Brand />
              <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted" aria-label="Close menu"><X className="h-4 w-4" /></button>
            </div>
            <NavItems onPick={() => setOpen(false)} />
            {footer}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border/70 bg-card/90 px-4 backdrop-blur lg:hidden">
          <button type="button" onClick={() => setOpen(true)} className="-ml-1 rounded-md p-1.5 hover:bg-muted" aria-label="Open menu" data-testid="admin-menu-button"><Menu className="h-5 w-5" /></button>
          <Brand />
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className={`mx-auto w-full ${wide ? "max-w-[1280px]" : "max-w-5xl"} px-4 pb-14 pt-6 sm:px-6 lg:px-8 lg:pt-8`}>
            {(title || actions) && (
              <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-0">
                  {title && <h1 className="text-xl font-bold tracking-tight sm:text-2xl" data-testid="admin-title">{title}</h1>}
                  {subtitle && <div className="mt-1 text-[12.5px] text-muted-foreground">{subtitle}</div>}
                </div>
                {actions && <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{actions}</div>}
              </header>
            )}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
