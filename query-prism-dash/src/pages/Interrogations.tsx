import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Clock, MessageSquareText, Search } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/layout/AppShell";
import { listSessions, Session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const Interrogations = () => {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  useEffect(() => {
    listSessions().then(({ sessions, mocked }) => {
      setSessions(sessions);
      if (mocked) {
        toast.message(t("error_disconnected"));
      }
    });
  }, [t]);

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

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t("interrogations_title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("interrogations_subtitle")}</p>

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
                      <Clock className="h-3 w-3" /> {session.updatedAt} · {session.messageCount}{" "}
                      {lang === "ar" ? "رسالة" : "messages"}
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
