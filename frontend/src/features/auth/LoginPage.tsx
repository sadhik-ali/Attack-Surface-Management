import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Eye,
  EyeOff,
  FileKey2,
  Radar,
  ShieldCheck,
  ShieldHalf,
} from "lucide-react";

import { useAuth } from "@/context/AuthProvider";
import { errorMessage } from "@/lib/api";
import { Button, Input, Spinner } from "@/components/ui";
import { AuthLoadingScreen } from "@/components/layout/AppShell";

const DEMO_ACCOUNTS = [
  {
    email: "platform@asm.example",
    label: "Super Admin",
    detail: "All three companies",
  },
  {
    email: "admin@northwind.example",
    label: "Company Admin",
    detail: "Northwind Technologies",
  },
  {
    email: "analyst@northwind.example",
    label: "Security Analyst",
    detail: "Northwind + Meridian read-only",
  },
  {
    email: "auditor@meridian.example",
    label: "Read-Only Auditor",
    detail: "Meridian Health Group",
  },
  {
    email: "analyst@atlas.example",
    label: "Security Analyst",
    detail: "Atlas Financial",
  },
];

const DEMO_PASSWORD = "AsmDemo!2026";
const SHOW_DEMO =
  import.meta.env.DEV ||
  ["localhost", "127.0.0.1"].includes(window.location.hostname);

const FEATURES = [
  {
    icon: Radar,
    title: "Authorized discovery",
    body: "Passive DNS, certificate transparency and consent-gated probes, with every scan scoped to an approved authorization.",
  },
  {
    icon: FileKey2,
    title: "Certificate assurance",
    body: "Track expiry, issuer coverage and hostname mismatches before an outage or browser warning reaches customers.",
  },
  {
    icon: Activity,
    title: "Explainable risk",
    body: "Every score lists its factors, so prioritisation is auditable rather than a black box.",
  },
];

export function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (() => {
    const candidate = (location.state as { from?: string } | null)?.from;
    return candidate && candidate.startsWith("/") && !candidate.startsWith("//")
      ? candidate
      : "/dashboard";
  })();

  useEffect(() => {
    if (status === "authenticated") {
      navigate(from, { replace: true });
    }
  }, [from, navigate, status]);

  if (status === "loading") return <AuthLoadingScreen />;
  if (status === "authenticated") return <Navigate to={from} replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (demoEmail: string) => {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError(null);
  };

  return (
    <div className="grid min-h-screen bg-bg lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden border-r border-border bg-surface lg:flex lg:flex-col lg:justify-between lg:p-10 xl:p-14">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,rgb(var(--color-grid))_1px,transparent_1px),linear-gradient(to_bottom,rgb(var(--color-grid))_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_top_left,black,transparent_75%)]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 top-1/3 h-96 w-96 rounded-full bg-brand-600/10 blur-3xl"
        />

        <div className="relative">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-brand-500/30 bg-brand-500/10">
              <ShieldHalf aria-hidden="true" className="h-5 w-5 text-brand-400" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-100">
                Perimeter ASM
              </p>
              <p className="text-[11px] text-slate-500">
                Attack surface management
              </p>
            </div>
          </div>

          <div className="mt-16 max-w-xl">
            <p className="inline-flex items-center gap-1.5 rounded-full border border-brand-500/25 bg-brand-500/10 px-2.5 py-1 text-[11px] font-medium text-brand-400">
              <ShieldCheck aria-hidden="true" className="h-3 w-3" />
              Multi-tenant security operations
            </p>
            <h2 className="mt-5 text-3xl font-semibold leading-tight tracking-tight text-slate-50 xl:text-4xl">
              Know your public attack surface before someone else maps it.
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-slate-400">
              One workspace for asset discovery, exposure tracking, certificate
              health and evidence-backed remediation — isolated per company and
              gated by explicit ownership authorization.
            </p>
          </div>

          <ul className="mt-10 flex max-w-xl flex-col gap-4">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-raised">
                  <feature.icon
                    aria-hidden="true"
                    className="h-4 w-4 text-brand-400"
                  />
                </span>
                <div>
                  <p className="text-sm font-medium text-slate-200">
                    {feature.title}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                    {feature.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative mt-12 flex items-center justify-between border-t border-border pt-5 text-[11px] text-slate-600">
          <span>Sample data is always labelled. Scans never run unauthorized.</span>
          <span className="num">v0.1 · 2026.10</span>
        </div>
      </section>

      <section className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-brand-500/30 bg-brand-500/10">
              <ShieldHalf aria-hidden="true" className="h-5 w-5 text-brand-400" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-100">
                Perimeter ASM
              </p>
              <p className="text-[11px] text-slate-500">
                Attack surface management
              </p>
            </div>
          </div>

          <div className="rounded-card border border-border bg-surface p-5 shadow-panel sm:p-7">
            <h1 className="text-xl font-semibold tracking-tight text-slate-50">
              Sign in
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Use your company account to enter the security workspace.
            </p>

            <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
              <Input
                type="email"
                label="Work email"
                autoComplete="username"
                placeholder="you@company.example"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoFocus
              />
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  label="Password"
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute bottom-2 right-2 rounded p-1 text-slate-500 transition-colors hover:text-slate-200"
                >
                  {showPassword ? (
                    <EyeOff aria-hidden="true" className="h-4 w-4" />
                  ) : (
                    <Eye aria-hidden="true" className="h-4 w-4" />
                  )}
                </button>
              </div>

              {error ? (
                <div
                  role="alert"
                  className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical"
                >
                  {error}
                </div>
              ) : null}

              <Button
                type="submit"
                size="lg"
                fullWidth
                loading={submitting}
                disabled={!email || !password}
              >
                {submitting ? "Signing in…" : "Sign in"}
                {!submitting ? (
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                ) : null}
              </Button>
            </form>

            <p className="mt-4 flex items-center gap-1.5 text-[11px] text-slate-500">
              <ShieldCheck aria-hidden="true" className="h-3 w-3" />
              Sessions expire after inactivity. Access is logged in the audit trail.
            </p>
          </div>

          {SHOW_DEMO ? (
            <div className="mt-4 rounded-card border border-border bg-surface p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-slate-300">
                  Demo workspace
                </p>
                <span className="inline-flex items-center gap-1 rounded-full border border-medium/30 bg-medium/10 px-1.5 py-0.5 text-[10px] font-medium text-medium">
                  Sample data
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                Choose a seeded account to explore each role. Password:{" "}
                <span className="num text-slate-300">{DEMO_PASSWORD}</span>
              </p>
              <div className="mt-3 grid gap-1.5">
                {DEMO_ACCOUNTS.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    onClick={() => fillDemo(account.email)}
                    className="flex items-center justify-between gap-2 rounded-md border border-border bg-bg px-2.5 py-1.5 text-left transition-colors hover:border-brand-500/40 hover:bg-surface-raised"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[11px] text-slate-300">
                        {account.email}
                      </span>
                      <span className="block truncate text-[10px] text-slate-600">
                        {account.detail}
                      </span>
                    </span>
                    <span className="shrink-0 text-[10px] font-medium text-brand-400">
                      {account.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {submitting ? (
            <div className="mt-3 flex items-center justify-center gap-2 text-[11px] text-slate-500">
              <Spinner className="h-3 w-3" />
              Verifying credentials…
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
