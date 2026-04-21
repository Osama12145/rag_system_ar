import { Languages, Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function TopBar() {
  const { lang, toggleLang } = useI18n();
  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border/40 bg-background/40 px-6 py-3 backdrop-blur-xl md:px-10">
      <div className="relative flex flex-1 items-center">
        <Search className="absolute start-3 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder={lang === "ar" ? "ابحث في المستندات والاستفسارات…" : "Search documents, sessions…"}
          className="h-10 w-full max-w-md rounded-full border border-border/60 bg-card/50 ps-9 pe-4 text-sm text-foreground outline-none ring-0 placeholder:text-muted-foreground focus:border-primary/40"
        />
      </div>

      <button
        onClick={toggleLang}
        className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/60 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:text-primary"
        aria-label="Toggle language"
      >
        <Languages className="h-3.5 w-3.5" />
        {lang === "en" ? "العربية" : "English"}
      </button>

      <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-primary text-xs font-semibold text-primary-foreground">
        OS
      </div>
    </header>
  );
}
