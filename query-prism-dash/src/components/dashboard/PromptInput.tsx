import { useEffect, useMemo, useRef, useState, KeyboardEvent } from "react";
import { ArrowUp, Brain, Paperclip, Quote, Telescope } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";

export type ChatOptions = {
  sourceCheck: boolean;
  deepResearch: boolean;
  reasoning: boolean;
};

type PromptMode = "sourceCheck" | "deepResearch" | "reasoning";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (text: string, opts: ChatOptions) => void;
  onAttach?: () => void;
  busy?: boolean;
  attachmentsBusy?: boolean;
};

const INTRO_HINT_DURATION_MS = 4200;

export function PromptInput({ value, onChange, onSubmit, onAttach, busy, attachmentsBusy }: Props) {
  const { t, lang } = useI18n();
  const [mode, setMode] = useState<PromptMode | null>("sourceCheck");
  const [showIntroHints, setShowIntroHints] = useState(true);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowIntroHints(false), INTRO_HINT_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, []);

  const optionHelp = useMemo(
    () => ({
      sourceCheck: {
        label: t("chip_source"),
        title: lang === "ar" ? "للإجابات الموثقة" : "For cited answers",
        description:
          lang === "ar"
            ? "يركز على دعم الرد بالمصادر والاقتباسات حتى تعرف المعلومة من أي مستند."
            : "Keeps the answer grounded in visible citations so the user can trace each claim.",
        icon: Quote,
        tone: "cyan" as const,
      },
      deepResearch: {
        label: t("chip_research"),
        title: lang === "ar" ? "للبحث الأوسع" : "For broader research",
        description:
          lang === "ar"
            ? "مناسب عندما تريد تحليلًا أوسع وتجميعًا من أكثر من جزء أو أكثر من ملف."
            : "Best when the user wants a wider scan across multiple document sections or files.",
        icon: Telescope,
        tone: "violet" as const,
      },
      reasoning: {
        label: t("chip_reasoning"),
        title: lang === "ar" ? "للأسئلة التحليلية" : "For analytical questions",
        description:
          lang === "ar"
            ? "يفيد في الأسئلة التي تحتاج تفكيرًا مرتبًا ومقارنة أو استنتاجًا أو تفصيلًا منطقيًا."
            : "Useful for structured thinking, comparisons, inference, and more deliberate analysis.",
        icon: Brain,
        tone: "amber" as const,
      },
    }),
    [lang, t],
  );

  const toggle = (nextMode: PromptMode) => {
    setShowIntroHints(false);
    setMode((currentMode) => (currentMode === nextMode ? null : nextMode));
  };

  const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    setShowIntroHints(false);
    onSubmit(text, {
      sourceCheck: mode === "sourceCheck",
      deepResearch: mode === "deepResearch",
      reasoning: mode === "reasoning",
    });
  };

  const Chip = ({
    active,
    modeKey,
  }: {
    active: boolean;
    modeKey: PromptMode;
  }) => {
    const config = optionHelp[modeKey];
    const Icon = config.icon;

    return (
      <Tooltip delayDuration={120}>
        <div className="relative">
          {showIntroHints && (
            <div className="pointer-events-none absolute inset-x-0 bottom-full z-20 mb-2 flex justify-center animate-fade-in">
              <div className="max-w-[190px] rounded-2xl border border-border/60 bg-background/90 px-3 py-2 text-center shadow-elevated backdrop-blur-xl">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-foreground/85">
                  {config.title}
                </div>
                <div className="mt-1 text-[11px] leading-4 text-muted-foreground">{config.description}</div>
              </div>
            </div>
          )}

          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => toggle(modeKey)}
              aria-label={`${config.label}. ${config.description}`}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-all ${
                active
                  ? config.tone === "cyan"
                    ? "border-primary/50 bg-primary/15 text-primary shadow-[0_0_20px_hsl(var(--primary)/0.25)]"
                    : config.tone === "violet"
                    ? "border-secondary/50 bg-secondary/15 text-secondary-glow shadow-[0_0_20px_hsl(var(--secondary)/0.25)]"
                    : "border-warning/50 bg-warning/15 text-warning shadow-[0_0_20px_hsl(var(--warning)/0.2)]"
                  : "border-border/60 bg-card/40 text-muted-foreground hover:border-border hover:text-foreground"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {config.label}
            </button>
          </TooltipTrigger>

          <TooltipContent
            side="top"
            align="center"
            className="max-w-[220px] rounded-2xl border-border/60 bg-card/95 px-3 py-2 text-start shadow-elevated"
          >
            <div className="text-[11px] font-semibold text-foreground">{config.title}</div>
            <div className="mt-1 text-[11px] leading-4 text-muted-foreground">{config.description}</div>
          </TooltipContent>
        </div>
      </Tooltip>
    );
  };

  return (
    <div className="glass-strong relative rounded-2xl border-border/60 p-3 shadow-elevated">
      <div className="pointer-events-none absolute inset-x-6 -top-px h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
      <textarea
        ref={taRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKey}
        rows={1}
        placeholder={t("prompt_placeholder")}
        className="w-full resize-none bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className={`flex flex-wrap items-center gap-2 transition-all ${showIntroHints ? "pt-12" : ""}`}>
          <Chip active={mode === "sourceCheck"} modeKey="sourceCheck" />
          <Chip active={mode === "deepResearch"} modeKey="deepResearch" />
          <Chip active={mode === "reasoning"} modeKey="reasoning" />
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
