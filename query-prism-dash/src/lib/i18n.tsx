import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";

export type Lang = "en" | "ar";

type Dict = Record<string, { en: string; ar: string }>;

const DICT: Dict = {
  app_name: { en: "OS_AI", ar: "OS_AI" },
  app_tagline: { en: "Enterprise RAG", ar: "ذكاء المؤسسة" },
  nav_dashboard: { en: "Dashboard", ar: "لوحة التحكم" },
  nav_library: { en: "Library", ar: "المكتبة" },
  nav_interrogations: { en: "Interrogations", ar: "الاستفسارات" },
  nav_settings: { en: "Settings", ar: "الإعدادات" },
  greeting: {
    en: "Welcome to OS_AI Center.",
    ar: "مرحبًا بك في مركز OS_AI.",
  },
  greeting_sub: {
    en: "How can I assist you today?",
    ar: "كيف يمكنني مساعدتك اليوم؟",
  },
  card_summary_title: { en: "Document Summary", ar: "ملخص المستندات" },
  card_summary_desc: {
    en: "Summarize the latest uploaded file in seconds.",
    ar: "لخّص آخر ملف تم رفعه في ثوانٍ.",
  },
  card_multilingual_title: { en: "Multilingual RAG", ar: "بحث متعدد اللغات" },
  card_multilingual_desc: {
    en: "Ask in Arabic or English — powered by Cohere embeddings.",
    ar: "اسأل بالعربية أو الإنجليزية — مدعوم بنماذج Cohere.",
  },
  card_policy_title: { en: "Policy Search", ar: "بحث السياسات" },
  card_policy_desc: {
    en: "Query internal policies and legal documents instantly.",
    ar: "ابحث في السياسات والوثائق القانونية الداخلية فورًا.",
  },
  prompt_placeholder: {
    en: "Ask anything about your company documents…",
    ar: "اسأل عن أي شيء في مستندات شركتك…",
  },
  chip_source: { en: "Source Check", ar: "التحقق من المصدر" },
  chip_research: { en: "Deep Research", ar: "بحث متعمق" },
  chip_reasoning: { en: "Reasoning", ar: "التفكير المتسلسل" },
  send: { en: "Send", ar: "إرسال" },
  qdrant_status: { en: "Qdrant Connection", ar: "اتصال Qdrant" },
  qdrant_active: { en: "Active", ar: "نشط" },
  qdrant_offline: { en: "Offline", ar: "غير متصل" },
  token_usage: { en: "Token Usage", ar: "استهلاك الرموز" },
  library_title: { en: "Document Library", ar: "مكتبة المستندات" },
  library_subtitle: {
    en: "Manage your company's indexed knowledge base.",
    ar: "إدارة قاعدة المعرفة المفهرسة لشركتك.",
  },
  upload_cta: { en: "Upload Document", ar: "رفع مستند" },
  drop_here: {
    en: "Drop PDFs here or click to upload",
    ar: "أسقط ملفات PDF هنا أو انقر للرفع",
  },
  indexing: { en: "Indexing into Qdrant…", ar: "جاري الفهرسة في Qdrant…" },
  ready: { en: "Ready", ar: "جاهز" },
  pages: { en: "pages", ar: "صفحة" },
  chunks: { en: "chunks", ar: "أجزاء" },
  interrogations_title: { en: "Past Interrogations", ar: "الاستفسارات السابقة" },
  interrogations_subtitle: {
    en: "Review and resume previous analysis sessions.",
    ar: "راجع جلسات التحليل السابقة وتابعها.",
  },
  sources: { en: "Sources", ar: "المصادر" },
  citation_panel_title: { en: "Source Citations", ar: "اقتباسات المصادر" },
  no_citations: {
    en: "Citations will appear here when the assistant cites documents.",
    ar: "ستظهر الاقتباسات هنا عندما يستشهد المساعد بالمستندات.",
  },
  thinking: { en: "Thinking…", ar: "جاري التفكير…" },
  error_disconnected: { en: "Server disconnected — using local mock data.", ar: "الخادم غير متصل — يتم استخدام بيانات محلية." },
  error_token_limit: { en: "Token limit reached.", ar: "تم الوصول إلى حد الرموز." },
  page: { en: "Page", ar: "صفحة" },
};

type Ctx = {
  lang: Lang;
  dir: "ltr" | "rtl";
  toggleLang: () => void;
  setLang: (l: Lang) => void;
  t: (key: keyof typeof DICT) => string;
};

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    localStorage.setItem("cib-lang", l);
  }, []);

  useEffect(() => {
    const saved = (localStorage.getItem("cib-lang") as Lang | null) ?? "en";
    setLangState(saved);
  }, []);

  useEffect(() => {
    const dir = lang === "ar" ? "rtl" : "ltr";
    document.documentElement.setAttribute("dir", dir);
    document.documentElement.setAttribute("lang", lang);
  }, [lang]);

  const toggleLang = useCallback(() => setLang(lang === "en" ? "ar" : "en"), [lang, setLang]);

  const t = useCallback((key: keyof typeof DICT) => DICT[key]?.[lang] ?? String(key), [lang]);

  return (
    <I18nContext.Provider value={{ lang, dir: lang === "ar" ? "rtl" : "ltr", toggleLang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
