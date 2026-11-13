import { ArrowRight, Briefcase, FileSearch, Scale, ShieldCheck, UserRound, Workflow } from "lucide-react";
import { Link } from "react-router-dom";
import { Brand } from "@/components/Brand";

const STEPS = [
  { icon: UserRound, title: "Customer reports a problem", text: "Pick the transaction, describe it in English or Hinglish." },
  { icon: FileSearch, title: "AI agent investigates", text: "Masks personal data, matches the transaction and checks the bank's own evidence." },
  { icon: Scale, title: "Policy decides, in code", text: "Only clear, low-value, evidence-backed refunds are resolved automatically." },
  { icon: Workflow, title: "Analyst reviews the rest", text: "Risky cases reach a bank analyst with evidence, a recommendation and drafts." },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Brand />
        <span className="hidden text-sm text-muted-foreground sm:inline">Zeta Innovate 2026 prototype</span>
      </header>

      <section className="mx-auto max-w-6xl px-4 pb-10 pt-6 sm:px-6 sm:pt-12">
        <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
          AI-powered dispute resolution platform
        </p>
        <h1 className="max-w-3xl font-serif text-3xl font-semibold leading-tight sm:text-5xl">
          Card disputes resolved faster, with a person in charge of every risky decision.
        </h1>
        <p className="mt-4 max-w-2xl text-base text-muted-foreground sm:text-lg">
          Customers report a problem in their own words. An AI agent gathers the evidence; bank
          policy, written as code, decides what can be resolved automatically and what an analyst
          must review.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <PortalCard
            to="/customer/login"
            icon={UserRound}
            title="Customer login"
            text="Report a problem with a card transaction and track your complaints."
            cta="Enter customer portal"
            primary
          />
          <PortalCard
            to="/reviewer"
            icon={Briefcase}
            title="Reviewer login"
            text="For bank dispute analysts: queue, evidence, AI recommendations, decisions and audit trail."
            cta="Enter reviewer portal"
          />
        </div>
      </section>

      <section className="border-t border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h2 className="mb-6 font-serif text-2xl font-semibold">How it works</h2>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-panel border border-border bg-background p-4">
                <div className="mb-3 flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <s.icon className="h-4.5 w-4.5" aria-hidden />
                  </span>
                  <span className="text-xs font-semibold text-muted-foreground">Step {i + 1}</span>
                </div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 flex items-start gap-2 text-sm text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
            DisputeIQ recommends and records decisions. It does not move money: refunds are credited
            by the bank&apos;s payment systems.
          </p>
        </div>
      </section>
    </div>
  );
}

function PortalCard(props: {
  to: string;
  icon: typeof UserRound;
  title: string;
  text: string;
  cta: string;
  primary?: boolean;
}) {
  return (
    <Link
      to={props.to}
      className={
        "group flex flex-col rounded-panel border p-5 transition-shadow hover:shadow-md " +
        (props.primary ? "border-primary bg-primary text-primary-foreground" : "border-border bg-surface")
      }
    >
      <props.icon className="mb-3 h-6 w-6" aria-hidden />
      <span className="font-serif text-xl font-semibold">{props.title}</span>
      <span className={"mt-1 text-sm " + (props.primary ? "text-primary-foreground/85" : "text-muted-foreground")}>
        {props.text}
      </span>
      <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold">
        {props.cta} <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
      </span>
    </Link>
  );
}
