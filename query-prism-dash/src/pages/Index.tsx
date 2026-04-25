import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AppShell } from "@/components/layout/AppShell";
import { CitationsPanel } from "@/components/dashboard/CitationsPanel";
import { FeatureCards } from "@/components/dashboard/FeatureCards";
import { MessageList } from "@/components/dashboard/MessageList";
import { PromptInput, ChatOptions } from "@/components/dashboard/PromptInput";
import {
  Citation,
  clearChatHistory,
  createSessionId,
  getActiveSessionId,
  getChatHistory,
  setActiveSessionId,
  streamChat,
  uploadDocument,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
};

function toUiMessages(
  history: { role: "user" | "assistant"; content: string }[],
): Msg[] {
  return history.map((item, index) => ({
    id: `${item.role}-${index}-${item.content.length}`,
    role: item.role,
    content: item.content,
  }));
}

const Dashboard = () => {
  const { t, lang } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchParams] = useSearchParams();
  const requestedSessionId = searchParams.get("session")?.trim();

  const [sessionId, setSessionId] = useState(() => requestedSessionId || getActiveSessionId() || createSessionId());
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [allCitations, setAllCitations] = useState<Citation[]>([]);

  useEffect(() => {
    const nextSessionId = requestedSessionId || getActiveSessionId() || createSessionId();
    setSessionId((current) => (current === nextSessionId ? current : nextSessionId));
    setActiveSessionId(nextSessionId);
  }, [requestedSessionId]);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    setAllCitations([]);
    setActiveCitation(null);

    getChatHistory(sessionId).then(({ history, mocked }) => {
      if (cancelled) {
        return;
      }
      setMessages(toUiMessages(history));
      setHistoryLoading(false);
      if (mocked) {
        toast.message(t("error_disconnected"));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [sessionId, t]);

  const handleSubmit = useCallback(
    async (text: string, opts: ChatOptions) => {
      const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", content: text };
      const aId = `a-${Date.now()}`;
      const aMsg: Msg = { id: aId, role: "assistant", content: "", streaming: true };
      setMessages((prev) => [...prev, userMsg, aMsg]);
      setInput("");
      setBusy(true);
      setActiveSessionId(sessionId);

      try {
        const history = messages
          .filter((message) => !message.streaming)
          .map((message) => ({ role: message.role, content: message.content }));

        let acc = "";
        let mocked = false;
        let receivedCitations = false;

        for await (const chunk of streamChat({
          message: text,
          ...opts,
          language: lang,
          history,
          sessionId,
        })) {
          if (chunk.delta) {
            acc += chunk.delta;
            setMessages((prev) => prev.map((message) => (message.id === aId ? { ...message, content: acc } : message)));
          }

          if (chunk.citations) {
            receivedCitations = true;
            const citations = chunk.citations;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === aId ? { ...message, citations, streaming: false } : message,
              ),
            );
            setAllCitations((prev) => [...citations, ...prev]);
            if (citations.length > 0) {
              setPanelOpen(true);
            }
          }

          if (chunk.mocked) {
            mocked = true;
          }
        }

        if (!receivedCitations) {
          setMessages((prev) => prev.map((message) => (message.id === aId ? { ...message, streaming: false } : message)));
        }

        if (mocked) {
          toast.message(t("error_disconnected"));
        }
      } catch {
        toast.error(lang === "ar" ? "حدث خطأ أثناء إرسال الرسالة." : "Something went wrong while sending the message.");
        setMessages((prev) => prev.map((message) => (message.id === aId ? { ...message, streaming: false } : message)));
      } finally {
        setBusy(false);
      }
    },
    [lang, messages, sessionId, t],
  );

  const handleAttach = () => {
    fileInputRef.current?.click();
  };

  const handleFilesSelected = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) {
        return;
      }

      setUploading(true);
      try {
        for (const file of Array.from(files)) {
          await uploadDocument(file);
          toast.success(
            lang === "ar" ? `تم رفع ${file.name} ويمكنك السؤال عنه الآن.` : `${file.name} uploaded and ready for chat.`,
          );
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        toast.error(lang === "ar" ? `فشل رفع الملف: ${message}` : `Upload failed: ${message}`);
      } finally {
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
        setUploading(false);
      }
    },
    [lang],
  );

  const handleCitationClick = (citation: Citation) => {
    setActiveCitation(citation);
    setPanelOpen(true);
  };

  const handleClearCurrentChat = useCallback(async () => {
    try {
      await clearChatHistory(sessionId);
      setMessages([]);
      setAllCitations([]);
      setActiveCitation(null);
      toast.success(lang === "ar" ? "تم مسح المحادثة الحالية." : "Current chat cleared.");
    } catch {
      toast.error(lang === "ar" ? "تعذر مسح المحادثة الحالية." : "Unable to clear the current chat.");
    }
  }, [lang, sessionId]);

  return (
    <AppShell>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.docx,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        multiple
        className="hidden"
        onChange={(event) => handleFilesSelected(event.target.files)}
      />

      <div className={`mx-auto w-full max-w-4xl pb-40 ${panelOpen ? "md:pe-0" : ""}`}>
        {historyLoading ? (
          <div className="glass-card mt-6 rounded-2xl p-6 text-sm text-muted-foreground">
            {lang === "ar" ? "جارٍ تحميل المحادثة..." : "Loading conversation..."}
          </div>
        ) : messages.length === 0 ? (
          <div className="animate-fade-in pt-4 md:pt-8">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
                  {t("greeting")}
                </h1>
                <p className="mt-2 text-base text-gradient md:text-xl">{t("greeting_sub")}</p>
              </div>
              <button
                type="button"
                onClick={handleClearCurrentChat}
                className="rounded-full border border-border/60 bg-card/50 px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {lang === "ar" ? "بدء محادثة نظيفة" : "Reset current chat"}
              </button>
            </div>

            <div className="mt-8">
              <FeatureCards onPick={(prompt) => setInput(prompt)} />
            </div>
          </div>
        ) : (
          <div className="pt-2 md:pt-4">
            <div className="mb-4 flex justify-end">
              <button
                type="button"
                onClick={handleClearCurrentChat}
                className="rounded-full border border-border/60 bg-card/50 px-4 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                {lang === "ar" ? "مسح المحادثة الحالية" : "Clear current chat"}
              </button>
            </div>
            <MessageList messages={messages} onCitationClick={handleCitationClick} />
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 px-3 pb-4 md:px-10 md:pb-6">
        <div className={`mx-auto w-full max-w-4xl transition-all ${panelOpen ? "md:pe-[24rem]" : ""}`}>
          <PromptInput
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            onAttach={handleAttach}
            busy={busy}
            attachmentsBusy={uploading}
          />
          <div className="mt-2 text-center text-[11px] text-muted-foreground/70">
            {lang === "ar"
              ? "اضغط Enter للإرسال أو استخدم زر المشبك لرفع الملفات."
              : "Press Enter to send, or use the paperclip to upload files."}
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
