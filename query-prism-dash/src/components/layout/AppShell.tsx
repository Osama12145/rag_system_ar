import { ReactNode } from "react";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Ambient glow orbs */}
      <div className="ambient-orb h-[520px] w-[520px] -top-40 -left-40 bg-primary/30" />
      <div className="ambient-orb h-[600px] w-[600px] top-1/2 -right-60 bg-secondary/25" />
      <div className="ambient-orb h-[420px] w-[420px] bottom-[-180px] left-1/3 bg-primary/15" />

      <div className="relative z-10 flex min-h-screen w-full">
        <AppSidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <TopBar />
          <main className="flex-1 px-6 pb-10 pt-6 md:px-10">{children}</main>
          <footer className="px-6 py-4 text-center text-xs text-muted-foreground/70 md:px-10">
            © {new Date().getFullYear()} OS_AI · Enterprise RAG Platform
          </footer>
        </div>
      </div>
    </div>
  );
}
