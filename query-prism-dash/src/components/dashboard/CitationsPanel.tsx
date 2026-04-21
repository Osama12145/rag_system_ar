import { Citation } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { X, FileText, Sparkles } from "lucide-react";

type Props = {
  open: boolean;
  citations: Citation[];
  active?: Citation | null;
  onClose: () => void;
  onSelect: (c: Citation) => void;
};

export function CitationsPanel({ open, citations, active, onClose, onSelect }: Props) {
  const { t } = useI18n();

  return (
    <aside
      className={`fixed inset-y-0 end-0 z-30 w-full max-w-sm transform border-s border-border/40 bg-background/80 backdrop-blur-2xl transition-transform duration-300 ease-out md:max-w-md ${
        open ? "translate-x-0 rtl:-translate-x-0" : "translate-x-full rtl:-translate-x-full"
      }`}
      aria-hidden={!open}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between border-b border-border/40 px-5 py-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">{t("citation_panel_title")}</h2>
            <span className="ms-1 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
              {citations.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {citations.length === 0 ? (
            <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
              <div className="max-w-[240px]">{t("no_citations")}</div>
            </div>
          ) : (
            <ol className="flex flex-col gap-3">
              {citations.map((c, i) => (
                <li key={c.id}>
                  <button
                    onClick={() => onSelect(c)}
                    className={`w-full rounded-xl border p-4 text-start transition-all ${
                      active?.id === c.id
                        ? "border-primary/60 bg-primary/10 shadow-glow-cyan"
                        : "border-border/60 bg-card/50 hover:border-primary/30 hover:bg-card/80"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="grid h-5 w-5 place-items-center rounded-full bg-gradient-primary text-[10px] font-semibold text-primary-foreground">
                        {i + 1}
                      </span>
                      <FileText className="h-3.5 w-3.5 text-primary" />
                      <div className="truncate text-xs font-medium text-foreground">{c.document}</div>
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {t("page")} {c.page}
                      {typeof c.score === "number" && <span> · score {(c.score * 100).toFixed(0)}%</span>}
                    </div>
                    <div className="mt-3 rounded-lg border-s-2 border-primary/60 bg-background/40 px-3 py-2 text-xs italic leading-relaxed text-foreground/90">
                      “{c.snippet}”
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </aside>
  );
}
