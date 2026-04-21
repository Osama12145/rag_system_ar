import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useI18n } from "@/lib/i18n";
import { DocumentRecord, listDocuments, uploadDocument } from "@/lib/api";
import { Upload, FileText, Loader2, CheckCircle2, Search, AlertCircle } from "lucide-react";
import { toast } from "sonner";

const Library = () => {
  const { t, lang } = useI18n();
  const [docs, setDocs] = useState<DocumentRecord[]>([]);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [query, setQuery] = useState("");

  useEffect(() => {
    listDocuments().then(({ docs, mocked }) => {
      setDocs(docs);
      if (mocked) toast.message(t("error_disconnected"));
    });
  }, [t]);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files) return;
      for (const file of Array.from(files)) {
        const tempId = `tmp-${Date.now()}-${file.name}`;
        const placeholder: DocumentRecord = {
          id: tempId,
          name: file.name,
          size: file.size,
          pages: 0,
          chunks: 0,
          uploadedAt: new Date().toISOString().slice(0, 10),
          status: "indexing",
        };
        setDocs((prev) => [placeholder, ...prev]);
        setProgress((p) => ({ ...p, [tempId]: 0 }));

        try {
          const { doc } = await uploadDocument(file, (pct) =>
            setProgress((p) => ({ ...p, [tempId]: pct })),
          );
          setDocs((prev) => prev.map((d) => (d.id === tempId ? doc : d)));
          toast.success(lang === "ar" ? `تمت فهرسة ${file.name}` : `Indexed ${file.name}`);
        } catch (err: unknown) {
          // Mark the file as error and show a toast
          setDocs((prev) =>
            prev.map((d) => (d.id === tempId ? { ...d, status: "error" as const } : d)),
          );
          const msg = err instanceof Error ? err.message : String(err);
          toast.error(lang === "ar" ? `فشل رفع ${file.name}: ${msg}` : `Upload failed for ${file.name}: ${msg}`);
        } finally {
          setProgress((p) => {
            const { [tempId]: _, ...rest } = p;
            return rest;
          });
        }
      }
    },
    [lang],
  );

  const filtered = docs.filter((d) => d.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-6xl">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t("library_title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("library_subtitle")}</p>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 self-start rounded-full bg-gradient-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-glow-cyan transition-transform hover:scale-[1.02]">
            <Upload className="h-4 w-4" />
            {t("upload_cta")}
            <input
              type="file"
              accept="application/pdf"
              multiple
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </label>
        </div>

        {/* Dropzone */}
        <label
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFiles(e.dataTransfer.files);
          }}
          className="glass-card group mt-6 grid cursor-pointer place-items-center rounded-2xl border-2 border-dashed border-border/60 px-6 py-10 text-center transition-colors hover:border-primary/50"
        >
          <input
            type="file"
            accept="application/pdf"
            multiple
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary">
            <Upload className="h-5 w-5" />
          </div>
          <div className="mt-3 text-sm font-medium text-foreground">{t("drop_here")}</div>
          <div className="mt-1 text-xs text-muted-foreground">PDF · {lang === "ar" ? "حتى ٥٠ ميجابايت" : "up to 50 MB"}</div>
        </label>

        {/* Search */}
        <div className="relative mt-6">
          <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={lang === "ar" ? "ابحث عن مستند…" : "Search documents…"}
            className="h-10 w-full rounded-xl border border-border/60 bg-card/40 ps-9 pe-3 text-sm outline-none focus:border-primary/40"
          />
        </div>

        {/* List */}
        <div className="mt-4 grid gap-3">
          {filtered.map((d) => {
            const pct = progress[d.id];
            const isIndexing = d.status === "indexing";
            const isError = d.status === "error";
            return (
              <div key={d.id} className="glass-card flex items-center gap-4 rounded-xl p-4">
                <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl text-primary ${isError ? "bg-destructive/10 text-destructive" : "bg-primary/10"}`}>
                  <FileText className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="truncate text-sm font-medium text-foreground">{d.name}</div>
                    {isIndexing ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] text-warning">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {t("indexing")}
                      </span>
                    ) : isError ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] text-destructive">
                        <AlertCircle className="h-3 w-3" />
                        {lang === "ar" ? "خطأ" : "Error"}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] text-success">
                        <CheckCircle2 className="h-3 w-3" />
                        {t("ready")}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {(d.size / 1_000_000).toFixed(1)} MB · {d.pages} {t("pages")} · {d.chunks} {t("chunks")} ·{" "}
                    {d.uploadedAt}
                  </div>
                  {isIndexing && typeof pct === "number" && (
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted/60">
                      <div className="h-full bg-gradient-primary transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="glass-card grid place-items-center rounded-xl py-12 text-sm text-muted-foreground">
              {lang === "ar" ? "لا توجد مستندات." : "No documents."}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};

export default Library;
