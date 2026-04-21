import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useI18n } from "@/lib/i18n";
import { listSessions, Session } from "@/lib/api";
import { MessageSquareText, Clock, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const Interrogations = () => {
  const { t, lang } = useI18n();
  const [sessions, setSessions] = useState<Session[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    listSessions().then(({ sessions, mocked }) => {
      setSessions(sessions);
      if (mocked) toast.message(t("error_disconnected"));
    });
  }, [t]);

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t("interrogations_title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("interrogations_subtitle")}</p>

        <div className="mt-8 grid gap-3 md:grid-cols-2">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => navigate("/")}
              className="glass-card group relative overflow-hidden rounded-2xl p-5 text-start transition-all hover:-translate-y-0.5 hover:shadow-elevated"
            >
              <div className="pointer-events-none absolute -top-12 -end-12 h-32 w-32 rounded-full bg-secondary/30 opacity-40 blur-2xl transition-opacity group-hover:opacity-70" />
              <div className="relative flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-secondary/15 text-secondary-glow">
                    <MessageSquareText className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">{s.title}</div>
                    <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3" /> {s.updatedAt} · {s.messageCount} {lang === "ar" ? "رسالة" : "messages"}
                    </div>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </div>
              <p className="relative mt-3 line-clamp-2 text-sm text-muted-foreground">{s.preview}</p>
            </button>
          ))}
        </div>
      </div>
    </AppShell>
  );
};

export default Interrogations;
