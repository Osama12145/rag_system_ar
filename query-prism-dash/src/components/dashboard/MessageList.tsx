import { Citation } from "@/lib/api";
import { FileText } from "lucide-react";
import { useI18n } from "@/lib/i18n";

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
};

export function MessageList({
  messages,
  onCitationClick,
}: {
  messages: Msg[];
  onCitationClick: (c: Citation) => void;
}) {
  const { t, lang } = useI18n();
  if (messages.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex w-full ${m.role === "user" ? "justify-end" : "justify-start"} animate-fade-in`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              m.role === "user"
                ? "bg-gradient-primary text-primary-foreground shadow-glow-cyan"
                : "glass-card text-foreground"
            }`}
          >
            <div className="whitespace-pre-wrap">
              {renderMarkdownLite(m.content)}
              {m.streaming && <span className="ms-1 inline-block h-3 w-[2px] translate-y-[2px] bg-primary animate-blink" />}
            </div>

            {m.role === "assistant" && m.citations && m.citations.length > 0 && (
              <div className="mt-3 border-t border-border/40 pt-3">
                <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {t("sources")}
                </div>
                <div className="flex flex-wrap gap-2">
                  {m.citations.map((c, i) => (
                    <button
                      key={c.id}
                      onClick={() => onCitationClick(c)}
                      className="group inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] text-foreground transition-colors hover:border-primary/60 hover:bg-primary/10"
                      title={c.snippet}
                    >
                      <span className="grid h-4 w-4 place-items-center rounded-full bg-primary/20 text-[10px] font-semibold text-primary">
                        {i + 1}
                      </span>
                      <FileText className="h-3 w-3 text-primary" />
                      <span className="truncate">
                        {c.document} · {t("page")} {c.page}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ))}
      <div className="sr-only" aria-live="polite">
        {lang === "ar" ? "رد جديد" : "new reply"}
      </div>
    </div>
  );
}

// Tiny markdown subset: **bold** and _italic_
function renderMarkdownLite(text: string) {
  const parts: (string | JSX.Element)[] = [];
  const regex = /(\*\*[^*]+\*\*|_[^_]+_)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={key++} className="font-semibold text-primary">{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<em key={key++} className="text-muted-foreground">{token.slice(1, -1)}</em>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
