import { FormEvent, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { LogIn, ShieldCheck, UserCircle2 } from "lucide-react";

import { AppShell } from "@/components/layout/AppShell";
import {
  continueAsGuest,
  getCurrentIdentity,
  listDocuments,
  listSessions,
  listStoredIdentities,
  switchIdentity,
  upsertLocalIdentity,
  type StoredIdentity,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Stats = {
  docs: number;
  sessions: number;
};

const Profile = () => {
  const { lang } = useI18n();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [activeIdentity, setActiveIdentity] = useState<StoredIdentity>(() => getCurrentIdentity());
  const [identities, setIdentities] = useState<StoredIdentity[]>(() => listStoredIdentities());
  const [stats, setStats] = useState<Stats>({ docs: 0, sessions: 0 });
  const [loadingStats, setLoadingStats] = useState(true);

  const copy = useMemo(
    () => ({
      title: lang === "ar" ? "الملف الشخصي والإعدادات" : "Profile & Settings",
      subtitle:
        lang === "ar"
          ? "تقدر تستخدم النظام كضيف، أو تحفظ ملفًا شخصيًا محليًا وتبدّل له وقت ما تريد."
          : "You can keep using the app as a guest, or save an optional local profile and switch back to it anytime.",
      guestTitle: lang === "ar" ? "وضع الضيف" : "Guest Mode",
      guestDesc:
        lang === "ar"
          ? "الدخول غير إلزامي. استخدامك كضيف يبقى معزولًا داخل هذا المتصفح."
          : "Login is optional. Guest usage stays isolated inside this browser.",
      loginTitle: lang === "ar" ? "تسجيل دخول اختياري" : "Optional Sign In",
      loginDesc:
        lang === "ar"
          ? "اكتب الاسم والبريد لحفظ ملف محلي على هذا الجهاز. إذا كان البريد موجودًا، سيتم فتح نفس الملف."
          : "Enter your name and email to save a local profile on this device. If the email already exists, it reopens that profile.",
      name: lang === "ar" ? "الاسم" : "Name",
      email: lang === "ar" ? "البريد الإلكتروني" : "Email",
      continueGuest: lang === "ar" ? "المتابعة كضيف" : "Continue as Guest",
      saveSignin: lang === "ar" ? "حفظ وتسجيل الدخول" : "Save and Sign In",
      currentIdentity: lang === "ar" ? "الهوية الحالية" : "Current Identity",
      savedProfiles: lang === "ar" ? "الملفات المحفوظة" : "Saved Profiles",
      noProfiles: lang === "ar" ? "لا توجد ملفات محلية محفوظة بعد." : "No saved local profiles yet.",
      documents: lang === "ar" ? "الملفات" : "Documents",
      sessions: lang === "ar" ? "المحادثات" : "Sessions",
      guestBadge: lang === "ar" ? "ضيف" : "Guest",
      localBadge: lang === "ar" ? "ملف محلي" : "Local Profile",
      identityHint: lang === "ar" ? "معرف الهوية داخل المتصفح" : "Browser identity ID",
      switchTo: lang === "ar" ? "الدخول لهذا الملف" : "Switch to this profile",
      statsLoading: lang === "ar" ? "جارٍ تحميل الإحصاءات..." : "Loading stats...",
    }),
    [lang],
  );

  useEffect(() => {
    let cancelled = false;
    setLoadingStats(true);
    Promise.all([listDocuments(), listSessions()]).then(([docsResult, sessionsResult]) => {
      if (cancelled) {
        return;
      }
      setStats({
        docs: docsResult.docs.length,
        sessions: sessionsResult.sessions.length,
      });
      setLoadingStats(false);
    });

    return () => {
      cancelled = true;
    };
  }, [activeIdentity.id]);

  const refreshIdentities = () => {
    setActiveIdentity(getCurrentIdentity());
    setIdentities(listStoredIdentities());
  };

  const handleGuest = () => {
    continueAsGuest();
    refreshIdentities();
    toast.success(lang === "ar" ? "تم التحويل إلى وضع الضيف." : "Switched to guest mode.");
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    try {
      upsertLocalIdentity(name, email);
      refreshIdentities();
      setName("");
      setEmail("");
      toast.success(lang === "ar" ? "تم فتح الملف الشخصي المحلي." : "Local profile is ready.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error(message);
    }
  };

  const handleSwitch = (identityId: string) => {
    switchIdentity(identityId);
    refreshIdentities();
    toast.success(lang === "ar" ? "تم التبديل للملف الشخصي." : "Switched profile.");
  };

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{copy.title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{copy.subtitle}</p>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <section className="glass-card rounded-2xl p-5">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
                <UserCircle2 className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-foreground">{copy.currentIdentity}</h2>
                <p className="text-sm text-muted-foreground">{copy.identityHint}</p>
              </div>
            </div>

            <div className="mt-5 grid gap-4 rounded-2xl border border-border/60 bg-card/40 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="text-base font-semibold text-foreground">{activeIdentity.name}</div>
                <span className="rounded-full bg-primary/15 px-3 py-1 text-xs font-medium text-primary">
                  {activeIdentity.type === "guest" ? copy.guestBadge : copy.localBadge}
                </span>
              </div>
              {activeIdentity.email && <div className="text-sm text-muted-foreground">{activeIdentity.email}</div>}
              <code className="overflow-x-auto rounded-xl bg-background/70 px-3 py-2 text-xs text-muted-foreground">
                {activeIdentity.id}
              </code>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-border/60 bg-background/40 p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy.documents}</div>
                  <div className="mt-2 text-2xl font-semibold text-foreground">
                    {loadingStats ? "..." : stats.docs}
                  </div>
                </div>
                <div className="rounded-2xl border border-border/60 bg-background/40 p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy.sessions}</div>
                  <div className="mt-2 text-2xl font-semibold text-foreground">
                    {loadingStats ? "..." : stats.sessions}
                  </div>
                </div>
              </div>

              {loadingStats && <div className="text-xs text-muted-foreground">{copy.statsLoading}</div>}
            </div>
          </section>

          <section className="grid gap-6">
            <div className="glass-card rounded-2xl p-5">
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-secondary/10 text-secondary-glow">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">{copy.guestTitle}</h2>
                  <p className="text-sm text-muted-foreground">{copy.guestDesc}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleGuest}
                className="mt-5 rounded-full border border-border/60 bg-card/60 px-4 py-2 text-sm text-foreground transition-colors hover:border-primary/40 hover:text-primary"
              >
                {copy.continueGuest}
              </button>
            </div>

            <div className="glass-card rounded-2xl p-5">
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
                  <LogIn className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">{copy.loginTitle}</h2>
                  <p className="text-sm text-muted-foreground">{copy.loginDesc}</p>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="mt-5 grid gap-3">
                <label className="grid gap-1 text-sm text-foreground">
                  <span>{copy.name}</span>
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    className="h-11 rounded-xl border border-border/60 bg-background/60 px-3 outline-none focus:border-primary/40"
                  />
                </label>
                <label className="grid gap-1 text-sm text-foreground">
                  <span>{copy.email}</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="h-11 rounded-xl border border-border/60 bg-background/60 px-3 outline-none focus:border-primary/40"
                    required
                  />
                </label>
                <button
                  type="submit"
                  className="mt-2 rounded-full bg-gradient-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-glow-cyan"
                >
                  {copy.saveSignin}
                </button>
              </form>
            </div>
          </section>
        </div>

        <section className="glass-card mt-6 rounded-2xl p-5">
          <h2 className="text-lg font-semibold text-foreground">{copy.savedProfiles}</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {identities.length > 0 ? (
              identities.map((identity) => {
                const active = identity.id === activeIdentity.id;
                return (
                  <div
                    key={identity.id}
                    className={`rounded-2xl border p-4 transition-colors ${
                      active
                        ? "border-primary/50 bg-primary/10"
                        : "border-border/60 bg-card/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-medium text-foreground">{identity.name}</div>
                        {identity.email && (
                          <div className="truncate text-sm text-muted-foreground">{identity.email}</div>
                        )}
                      </div>
                      <span className="rounded-full bg-background/70 px-2.5 py-1 text-[11px] text-muted-foreground">
                        {identity.type === "guest" ? copy.guestBadge : copy.localBadge}
                      </span>
                    </div>
                    <div className="mt-3 text-xs text-muted-foreground">{identity.id}</div>
                    {!active && (
                      <button
                        type="button"
                        onClick={() => handleSwitch(identity.id)}
                        className="mt-4 rounded-full border border-border/60 bg-background/60 px-3 py-1.5 text-xs text-foreground transition-colors hover:border-primary/40 hover:text-primary"
                      >
                        {copy.switchTo}
                      </button>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-sm text-muted-foreground">{copy.noProfiles}</div>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
};

export default Profile;
