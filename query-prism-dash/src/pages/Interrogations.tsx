import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Clock, MessageSquareText, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/layout/AppShell";
import { Session, startNewSession, useSessionsQuery } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const Interrogations = () => {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data, error } = useSessionsQuery();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  useEffect(() => {
    if (data?.sessions) {
      setSessions(data.sessions);
    }
  }, [data?.sessions]);

  useEffect(() => {
    if (error) {
      toast.message(t("error_disconnected"));
    }
  }, [error, t]);

  const filteredSessions = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) {
      return sessions;
    }

    return sessions.filter((session) => {
      const haystack = `${session.title} ${session.preview}`.toLowerCase();
      return haystack.includes(value);
    });
  }, [query, sessions]);

  const handleStartNewChat = () => {
    const sessionId = startNewSession();
    navigate(`/?session=${encodeURIComponent(sessionId)}`);
  };

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t("interrogations_title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("interrogations_subtitle")}</p>
          </div>
          <button
            type="button"
            onClick={handleStartNewChat}
            className="inline-flex items-center gap-2 self-start rounded-full border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/15"
          >
            <Plus className="h-4 w-4 text-primary" />
            {lang === "ar" ? "محادثة جديدة" : "New Chat"}
          </button>
        </div>

        <div className="relative mt-6">
          <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={lang === "ar" ? "ابحث في المحادثات..." : "Search sessions..."}
            className="h-10 w-full rounded-xl border border-border/60 bg-card/40 ps-9 pe-3 text-sm outline-none focus:border-primary/40"
          />
        </div>

        <div className="mt-8 grid gap-3 md:grid-cols-2">
          {filteredSessions.map((session) => (
            <button
              key={session.id}
              onClick={() => navigate(`/?session=${encodeURIComponent(session.id)}`)}
              className="glass-card group relative overflow-hidden rounded-2xl p-5 text-start transition-all hover:-translate-y-0.5 hover:shadow-elevated"
            >
              <div className="pointer-events-none absolute -top-12 -end-12 h-32 w-32 rounded-full bg-secondary/30 opacity-40 blur-2xl transition-opacity group-hover:opacity-70" />
              <div className="relative flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-secondary/15 text-secondary-glow">
                    <MessageSquareText className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">{session.title}</div>
                    <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3" /> {session.updatedAt} | {session.messageCount} {lang === "ar" ? "رسالة" : "messages"}
                    </div>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </div>
              <p className="relative mt-3 line-clamp-2 text-sm text-muted-foreground">{session.preview}</p>
            </button>
          ))}
        </div>

        {filteredSessions.length === 0 && (
          <div className="glass-card mt-4 rounded-xl py-10 text-center text-sm text-muted-foreground">
            {lang === "ar" ? "لا توجد محادثات مطابقة." : "No matching sessions."}
          </div>
        )}
      </div>
    </AppShell>
  );
};

export default Interrogations;
