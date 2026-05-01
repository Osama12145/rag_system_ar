import { ReactNode } from "react";

import { useI18n } from "@/lib/i18n";

import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  const { lang } = useI18n();
  const footerLabel = lang === "ar" ? "منصة RAG للمؤسسة" : "Enterprise RAG Platform";

  return (
    <div className="relative flex h-dvh w-full flex-col overflow-x-hidden bg-background text-foreground">
      <div className="ambient-orb -left-40 -top-40 h-[520px] w-[520px] bg-primary/30" />
      <div className="ambient-orb top-1/2 -right-60 h-[600px] w-[600px] bg-secondary/25" />
      <div className="ambient-orb bottom-[-180px] left-1/3 h-[420px] w-[420px] bg-primary/15" />

      <div className="relative z-10 flex min-h-0 flex-1">
        <AppSidebar />

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="sticky top-0 z-50 shrink-0">
            <TopBar />
          </div>

          <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 pb-10 pt-4 md:px-10 md:pb-12 md:pt-6">
            <div className="flex min-h-full min-w-0 flex-col">{children}</div>
          </main>

          <footer className="shrink-0 px-4 py-4 text-center text-xs text-muted-foreground/70 md:px-10">
            (c) {new Date().getFullYear()} OS_AI | {footerLabel}
          </footer>
        </div>
      </div>
    </div>
  );
}
