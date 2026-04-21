import { useCallback, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { FeatureCards } from "@/components/dashboard/FeatureCards";
import { PromptInput, ChatOptions } from "@/components/dashboard/PromptInput";
import { MessageList } from "@/components/dashboard/MessageList";
import { CitationsPanel } from "@/components/dashboard/CitationsPanel";
import { useI18n } from "@/lib/i18n";
import { Citation, streamChat } from "@/lib/api";
import { toast } from "sonner";

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
};

function generateSessionId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `session-${globalThis.crypto.randomUUID()}`;
  }

  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const Dashboard = () => {
  const { t, lang } = useI18n();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [allCitations, setAllCitations] = useState<Citation[]>([]);
  const [sessionId] = useState(() => {
    const existing = window.localStorage.getItem("os-ai-session-id");
    if (existing) return existing;
    const created = generateSessionId();
    window.localStorage.setItem("os-ai-session-id", created);
    return created;
  });

  const handleSubmit = useCallback(
    async (text: string, opts: ChatOptions) => {
      const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", content: text };
      const aId = `a-${Date.now()}`;
      const aMsg: Msg = { id: aId, role: "assistant", content: "", streaming: true };
      setMessages((prev) => [...prev, userMsg, aMsg]);
      setInput("");
      setBusy(true);

      try {
        const history = messages.map((m) => ({ role: m.role, content: m.content }));
        let acc = "";
        let mocked = false;
        for await (const chunk of streamChat({
          message: text,
          ...opts,
          language: lang,
          history,
          sessionId,
        })) {
          if (chunk.delta) {
            acc += chunk.delta;
            setMessages((prev) => prev.map((m) => (m.id === aId ? { ...m, content: acc } : m)));
          }
          if (chunk.citations) {
            const cits = chunk.citations;
            setMessages((prev) =>
              prev.map((m) => (m.id === aId ? { ...m, citations: cits, streaming: false } : m)),
            );
            setAllCitations((prev) => [...cits, ...prev]);
            if (cits.length > 0) setPanelOpen(true);
          }
          if (chunk.mocked) mocked = true;
        }
        if (mocked) toast.message(t("error_disconnected"));
      } catch (e) {
        toast.error(lang === "ar" ? "حدث خطأ ما" : "Something went wrong");
        setMessages((prev) => prev.map((m) => (m.id === aId ? { ...m, streaming: false } : m)));
      } finally {
        setBusy(false);
      }
    },
    [messages, lang, sessionId, t],
  );

  const handleCitationClick = (c: Citation) => {
    setActiveCitation(c);
    setPanelOpen(true);
  };

  return (
    <AppShell>
      <div className={`mx-auto w-full max-w-4xl pb-32 ${panelOpen ? "md:pe-0" : ""}`}>
        {messages.length === 0 ? (
          <div className="animate-fade-in pt-8">
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
              {t("greeting")}
            </h1>
            <p className="mt-2 text-lg text-gradient md:text-xl">{t("greeting_sub")}</p>

            <div className="mt-8">
              <FeatureCards onPick={(p) => setInput(p)} />
            </div>
          </div>
        ) : (
          <div className="pt-4">
            <MessageList messages={messages} onCitationClick={handleCitationClick} />
          </div>
        )}
      </div>

      {/* Floating prompt */}
      <div className="fixed inset-x-0 bottom-0 z-20 px-4 pb-6 md:px-10">
        <div className={`mx-auto w-full max-w-4xl transition-all ${panelOpen ? "md:pe-[24rem]" : ""}`}>
          <PromptInput value={input} onChange={setInput} onSubmit={handleSubmit} busy={busy} />
          <div className="mt-2 text-center text-[11px] text-muted-foreground/70">
            {lang === "ar"
              ? "اضغط Enter للإرسال · Shift+Enter لسطر جديد"
              : "Press Enter to send · Shift+Enter for newline"}
          </div>
        </div>
      </div>

      <CitationsPanel
        open={panelOpen}
        citations={allCitations}
        active={activeCitation}
        onClose={() => setPanelOpen(false)}
        onSelect={setActiveCitation}
      />
    </AppShell>
  );
};

export default Dashboard;
