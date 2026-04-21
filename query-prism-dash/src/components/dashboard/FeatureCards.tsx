import { FileText, Globe2, ScrollText, ArrowUpRight } from "lucide-react";
import { useI18n } from "@/lib/i18n";

type Card = {
  icon: typeof FileText;
  titleKey: "card_summary_title" | "card_multilingual_title" | "card_policy_title";
  descKey: "card_summary_desc" | "card_multilingual_desc" | "card_policy_desc";
  prompt: { en: string; ar: string };
  tone: "cyan" | "violet" | "mix";
};

const CARDS: Card[] = [
  {
    icon: FileText,
    titleKey: "card_summary_title",
    descKey: "card_summary_desc",
    prompt: {
      en: "Summarize the most recently uploaded document in 5 bullet points with page references.",
      ar: "لخّص آخر مستند تم رفعه في خمس نقاط مع الإشارة إلى أرقام الصفحات.",
    },
    tone: "cyan",
  },
  {
    icon: Globe2,
    titleKey: "card_multilingual_title",
    descKey: "card_multilingual_desc",
    prompt: {
      en: "Compare how data privacy is described across our Arabic and English policy documents.",
      ar: "قارن كيفية وصف خصوصية البيانات في مستندات السياسات العربية والإنجليزية.",
    },
    tone: "mix",
  },
  {
    icon: ScrollText,
    titleKey: "card_policy_title",
    descKey: "card_policy_desc",
    prompt: {
      en: "What does our policy say about remote work eligibility for new hires?",
      ar: "ماذا تنص سياستنا بشأن أهلية العمل عن بُعد للموظفين الجدد؟",
    },
    tone: "violet",
  },
];

export function FeatureCards({ onPick }: { onPick: (prompt: string) => void }) {
  const { t, lang } = useI18n();
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {CARDS.map(({ icon: Icon, titleKey, descKey, prompt, tone }) => (
        <button
          key={titleKey}
          onClick={() => onPick(prompt[lang])}
          className="glass-card group relative overflow-hidden rounded-2xl p-5 text-start transition-all hover:-translate-y-0.5 hover:shadow-elevated"
        >
          <div
            className={`pointer-events-none absolute -top-12 -end-12 h-32 w-32 rounded-full opacity-50 blur-2xl transition-opacity group-hover:opacity-80 ${
              tone === "cyan" ? "bg-primary/40" : tone === "violet" ? "bg-secondary/40" : "bg-gradient-primary"
            }`}
          />
          <div className="relative flex items-start justify-between">
            <div
              className={`grid h-10 w-10 place-items-center rounded-xl border border-border/40 ${
                tone === "cyan"
                  ? "bg-primary/10 text-primary"
                  : tone === "violet"
                  ? "bg-secondary/10 text-secondary-glow"
                  : "bg-gradient-primary text-primary-foreground"
              }`}
            >
              <Icon className="h-5 w-5" />
            </div>
            <ArrowUpRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 rtl:group-hover:-translate-x-0.5" />
          </div>
          <div className="relative mt-4">
            <div className="text-base font-semibold text-foreground">{t(titleKey)}</div>
            <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{t(descKey)}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
