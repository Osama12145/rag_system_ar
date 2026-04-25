import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { ArrowUp, Quote, Telescope, Brain, Paperclip } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export type ChatOptions = {
  sourceCheck: boolean;
  deepResearch: boolean;
  reasoning: boolean;
};

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (text: string, opts: ChatOptions) => void;
  onAttach?: () => void;
  busy?: boolean;
  attachmentsBusy?: boolean;
};

export function PromptInput({ value, onChange, onSubmit, onAttach, busy, attachmentsBusy }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"sourceCheck" | "deepResearch" | "reasoning" | null>("sourceCheck");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  const toggle = (m: "sourceCheck" | "deepResearch" | "reasoning") =>
    setMode((cur) => (cur === m ? null : m));

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSubmit(text, {
      sourceCheck: mode === "sourceCheck",
      deepResearch: mode === "deepResearch",
      reasoning: mode === "reasoning",
    });
  };

  const Chip = ({
    active,
    onClick,
    icon: Icon,
    label,
    tone,
  }: {
    active: boolean;
    onClick: () => void;
    icon: typeof Quote;
    label: string;
    tone: "cyan" | "violet" | "amber";
  }) => (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-all ${
        active
          ? tone === "cyan"
            ? "border-primary/50 bg-primary/15 text-primary shadow-[0_0_20px_hsl(var(--primary)/0.25)]"
            : tone === "violet"
            ? "border-secondary/50 bg-secondary/15 text-secondary-glow shadow-[0_0_20px_hsl(var(--secondary)/0.25)]"
            : "border-warning/50 bg-warning/15 text-warning shadow-[0_0_20px_hsl(var(--warning)/0.2)]"
          : "border-border/60 bg-card/40 text-muted-foreground hover:border-border hover:text-foreground"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );

  return (
    <div className="glass-strong relative rounded-2xl border-border/60 p-3 shadow-elevated">
      <div className="pointer-events-none absolute inset-x-6 -top-px h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        rows={1}
        placeholder={t("prompt_placeholder")}
        className="w-full resize-none bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Chip
            active={mode === "sourceCheck"}
            onClick={() => toggle("sourceCheck")}
            icon={Quote}
            label={t("chip_source")}
            tone="cyan"
          />
          <Chip
            active={mode === "deepResearch"}
            onClick={() => toggle("deepResearch")}
            icon={Telescope}
            label={t("chip_research")}
            tone="violet"
          />
          <Chip
            active={mode === "reasoning"}
            onClick={() => toggle("reasoning")}
            icon={Brain}
            label={t("chip_reasoning")}
            tone="amber"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onAttach}
            disabled={attachmentsBusy}
            className="grid h-9 w-9 place-items-center rounded-full border border-border/60 bg-card/40 text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Attach"
          >
            <Paperclip className={`h-4 w-4 ${attachmentsBusy ? "animate-pulse" : ""}`} />
          </button>
          <button
            type="button"
            disabled={busy || !value.trim()}
            onClick={submit}
            className="grid h-9 w-9 place-items-center rounded-full bg-gradient-primary text-primary-foreground shadow-glow-cyan transition-all hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
