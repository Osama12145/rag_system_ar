import { FormEvent, useEffect, useMemo, useState } from "react";
import { Languages, Menu, Search } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { listDocuments, listSessions, type DocumentRecord, type Session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { AppSidebarContent } from "./AppSidebar";

type SearchResults = {
  docs: DocumentRecord[];
  sessions: Session[];
};

export function TopBar() {
  const { lang, toggleLang } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults>({ docs: [], sessions: [] });
  const [searching, setSearching] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setQuery(params.get("q") ?? "");
  }, [location.search]);

  useEffect(() => {
    const value = query.trim().toLowerCase();
    if (value.length < 2) {
      setResults({ docs: [], sessions: [] });
      setSearching(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      setSearching(true);
      const [{ docs }, { sessions }] = await Promise.all([listDocuments(), listSessions()]);
      setResults({
        docs: docs.filter((doc) => doc.name.toLowerCase().includes(value)).slice(0, 5),
        sessions: sessions
          .filter((session) => {
            const haystack = `${session.title} ${session.preview}`.toLowerCase();
            return haystack.includes(value);
          })
          .slice(0, 5),
      });
      setSearching(false);
    }, 220);

    return () => window.clearTimeout(timer);
  }, [query]);

  const hasResults = results.docs.length > 0 || results.sessions.length > 0;
  const showResults = focused && query.trim().length >= 2;

  const searchTarget = useMemo(() => {
    if (location.pathname === "/interrogations") {
      return "/interrogations";
    }
    return "/library";
  }, [location.pathname]);

  const submitSearch = (event?: FormEvent) => {
    event?.preventDefault();
    const value = query.trim();
    if (!value) {
      return;
    }
    navigate(`${searchTarget}?q=${encodeURIComponent(value)}`);
    setFocused(false);
  };

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border/40 bg-background/70 px-4 py-3 backdrop-blur-xl md:px-10">
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetTrigger asChild>
          <button
            type="button"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-border/60 bg-card/60 text-foreground md:hidden"
            aria-label={lang === "ar" ? "فتح القائمة" : "Open menu"}
          >
            <Menu className="h-4 w-4" />
          </button>
        </SheetTrigger>
        <SheetContent side={lang === "ar" ? "right" : "left"} className="w-[85vw] border-border/40 bg-background p-3">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="h-full pt-8">
            <AppSidebarContent compact onNavigate={() => setMenuOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="relative flex-1">
        <form onSubmit={submitSearch} className="relative flex items-center">
          <Search className="absolute start-3 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => window.setTimeout(() => setFocused(false), 120)}
            placeholder={lang === "ar" ? "ابحث في المستندات أو المحادثات..." : "Search documents or sessions..."}
            className="h-10 w-full rounded-full border border-border/60 bg-card/50 ps-9 pe-4 text-sm text-foreground outline-none ring-0 placeholder:text-muted-foreground focus:border-primary/40"
          />
        </form>

        {showResults && (
          <div className="absolute inset-x-0 top-[calc(100%+0.5rem)] rounded-2xl border border-border/60 bg-background/95 p-3 shadow-elevated backdrop-blur-xl">
            {hasResults ? (
              <div className="grid gap-3">
                {results.docs.length > 0 && (
                  <div>
                    <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                      {lang === "ar" ? "ملفات" : "Documents"}
                    </div>
                    <div className="grid gap-2">
                      {results.docs.map((doc) => (
                        <button
                          key={doc.id}
                          type="button"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => {
                            navigate(`/library?q=${encodeURIComponent(doc.name)}`);
                            setFocused(false);
                          }}
                          className="rounded-xl border border-border/60 bg-card/40 px-3 py-2 text-start text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-card/70"
                        >
                          <div className="truncate font-medium">{doc.name}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{doc.uploadedAt}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {results.sessions.length > 0 && (
                  <div>
                    <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                      {lang === "ar" ? "محادثات" : "Sessions"}
                    </div>
                    <div className="grid gap-2">
                      {results.sessions.map((session) => (
                        <button
                          key={session.id}
                          type="button"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => {
                            navigate(`/?session=${encodeURIComponent(session.id)}`);
                            setFocused(false);
                          }}
                          className="rounded-xl border border-border/60 bg-card/40 px-3 py-2 text-start text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-card/70"
                        >
                          <div className="truncate font-medium">{session.title}</div>
                          <div className="mt-1 line-clamp-1 text-xs text-muted-foreground">{session.preview}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="px-2 py-4 text-sm text-muted-foreground">
                {searching
                  ? lang === "ar"
                    ? "جارٍ البحث..."
                    : "Searching..."
                  : lang === "ar"
                  ? "لا توجد نتائج مطابقة."
                  : "No matching results."}
              </div>
            )}
          </div>
        )}
      </div>

      <button
        onClick={toggleLang}
        className="inline-flex shrink-0 items-center gap-2 rounded-full border border-border/60 bg-card/60 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:text-primary"
        aria-label="Toggle language"
      >
        <Languages className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{lang === "en" ? "العربية" : "English"}</span>
      </button>

      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-primary text-xs font-semibold text-primary-foreground">
        OS
      </div>
    </header>
  );
}
