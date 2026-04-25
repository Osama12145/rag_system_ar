import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  Hexagon,
  LayoutDashboard,
  Library,
  MessageSquareText,
  Settings,
  Zap,
} from "lucide-react";

import { getQdrantStatus, getTokenUsage } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type SidebarContentProps = {
  compact?: boolean;
  onNavigate?: () => void;
};

export function AppSidebarContent({ compact = false, onNavigate }: SidebarContentProps) {
  const { t } = useI18n();
  const location = useLocation();
  const [qdrant, setQdrant] = useState({ active: true });
  const [usage, setUsage] = useState({ used: 0, total: 1 });

  useEffect(() => {
    getQdrantStatus().then((r) => setQdrant({ active: r.active }));
    getTokenUsage().then((r) => setUsage({ used: r.used, total: r.total }));
  }, []);

  const items = useMemo(
    () => [
      { to: "/", icon: LayoutDashboard, label: t("nav_dashboard") },
      { to: "/library", icon: Library, label: t("nav_library") },
      { to: "/interrogations", icon: MessageSquareText, label: t("nav_interrogations") },
    ],
    [t],
  );

  const usagePct = Math.min(100, Math.round((usage.used / Math.max(1, usage.total)) * 100));

  return (
    <div className={`glass-strong flex h-full flex-col rounded-2xl ${compact ? "p-4" : "p-4"}`}>
      <NavLink to="/" className="group flex items-center gap-3 px-2 py-2" onClick={onNavigate}>
        <div className="relative grid h-10 w-10 place-items-center rounded-xl bg-gradient-primary shadow-glow-cyan">
          <Hexagon className="h-5 w-5 text-primary-foreground" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight text-foreground">OS_AI</div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{t("app_tagline")}</div>
        </div>
      </NavLink>

      <nav className="mt-6 flex flex-1 flex-col gap-1">
        {items.map(({ to, icon: Icon, label }) => {
          const active = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={onNavigate}
              className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                active
                  ? "bg-primary/10 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.25)]"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              }`}
            >
              {active && <span className="absolute inset-y-2 start-0 w-[3px] rounded-full bg-gradient-primary" />}
              <Icon className={`h-4 w-4 ${active ? "text-primary" : ""}`} />
              <span>{label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-4 rounded-xl border border-border/60 bg-card/40 p-3 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <Activity className="h-3.5 w-3.5 text-success" />
            {t("qdrant_status")}
          </div>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              qdrant.active ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                qdrant.active ? "bg-success animate-pulse-glow" : "bg-destructive"
              }`}
            />
            {qdrant.active ? t("qdrant_active") : t("qdrant_offline")}
          </span>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-primary" />
            {t("token_usage")}
          </span>
          <span className="tabular-nums text-foreground/80">{usagePct}%</span>
        </div>
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted/60">
          <div className="h-full rounded-full bg-gradient-primary transition-all" style={{ width: `${usagePct}%` }} />
        </div>
        <div className="mt-1.5 text-[10px] text-muted-foreground/80">
          {(usage.used / 1000).toFixed(0)}k / {(usage.total / 1000).toFixed(0)}k tokens
        </div>
      </div>

      <NavLink
        to="/profile"
        onClick={onNavigate}
        className="mt-3 flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
      >
        <Settings className="h-4 w-4" />
        {t("nav_settings")}
      </NavLink>
    </div>
  );
}

export function AppSidebar() {
  return (
    <aside className="sticky top-0 z-20 hidden h-screen w-[260px] shrink-0 flex-col gap-6 border-e border-border/40 p-4 md:flex">
      <AppSidebarContent />
    </aside>
  );
}
