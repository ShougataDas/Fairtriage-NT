import Link from "next/link";
import { CircleAlert, LoaderCircle } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import type { Tier } from "@/lib/api";
import { cx, tierStyle } from "@/lib/format";

export function Card({ className, children, ...rest }: ComponentProps<"section">) {
  return (
    <section className={cx("rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6", className)} {...rest}>
      {children}
    </section>
  );
}

export function CardTitle({ children, aside, icon }: { children: ReactNode; aside?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <h2 className="flex items-center gap-2 text-lg font-bold text-graphite">
        {icon}
        {children}
      </h2>
      {aside}
    </div>
  );
}

type ButtonProps = ComponentProps<"button"> & { variant?: "primary" | "secondary" | "danger" | "ghost"; busy?: boolean };

const buttonBase =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2 font-bold transition disabled:cursor-not-allowed disabled:opacity-60";
const buttonVariants = {
  primary: "bg-ink text-white hover:bg-ink-strong",
  secondary: "border border-line bg-paper text-ink hover:bg-ink-soft",
  danger: "bg-immediate text-white hover:brightness-95",
  ghost: "text-ink hover:bg-ink-soft",
};

export function Button({ variant = "primary", busy, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button className={cx(buttonBase, buttonVariants[variant], className)} disabled={disabled || busy} {...rest}>
      {busy && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "primary",
  className,
  ...rest
}: ComponentProps<typeof Link> & { variant?: keyof typeof buttonVariants }) {
  return <Link className={cx(buttonBase, buttonVariants[variant], className)} {...rest} />;
}

export function TierBadge({ tier, size = "md" }: { tier: Tier; size?: "sm" | "md" | "lg" }) {
  const s = tierStyle[tier];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full font-bold ring-1 ring-inset",
        s.text, s.soft, s.ring,
        size === "sm" && "px-2 py-0.5 text-xs",
        size === "md" && "px-2.5 py-1 text-sm",
        size === "lg" && "px-4 py-1.5 text-lg",
      )}
    >
      <span className={cx("size-2 rounded-full", s.dot)} aria-hidden />
      {s.label}
    </span>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ink" | "warn" | "bad" | "good" }) {
  const tones = {
    neutral: "bg-canvas text-muted ring-line",
    ink: "bg-ink-soft text-ink ring-ink/20",
    warn: "bg-urgent-soft text-urgent ring-urgent/25",
    bad: "bg-immediate-soft text-immediate ring-immediate/25",
    good: "bg-routine-soft text-routine ring-routine/25",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ring-1 ring-inset", tones[tone])}>
      {children}
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-muted" role="status">
      <LoaderCircle className="size-5 animate-spin" aria-hidden />
      {label}…
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-immediate/30 bg-immediate-soft p-4 text-immediate">
      <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="flex-1">
        <p className="font-bold">Something went wrong</p>
        <p className="text-graphite">{msg}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line bg-paper px-6 py-12 text-center">
      {icon && <div className="text-muted">{icon}</div>}
      <p className="font-bold">{title}</p>
      {children && <div className="max-w-md text-muted">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, lede, aside }: { title: string; lede?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-graphite">{title}</h1>
        {lede && <p className="mt-2 max-w-2xl text-lg text-muted">{lede}</p>}
      </div>
      {aside}
    </div>
  );
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="font-bold">
        {label} {hint && <span className="font-normal text-muted">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

export const inputClass =
  "w-full rounded-xl border border-line bg-paper px-3.5 py-2.5 text-base text-graphite placeholder:text-muted/70 focus:border-ink focus:outline-none focus:ring-2 focus:ring-ink/20";
