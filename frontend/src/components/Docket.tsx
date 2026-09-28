"use client";

import { useState } from "react";
import { ArrowUpRight, Check, CircleCheck, Clock, Copy, House, ListOrdered, MessageSquareQuote, ShieldCheck, Siren, UserCheck } from "lucide-react";
import type { Tier } from "@/lib/api";
import { cx, paragraphs, tierMeaning, tierStyle } from "@/lib/format";

const EMERGENCY = "If there is a fire, or anyone is hurt, call 000";
const SAFETY = ["If it is safe to do so", "If you can,", "Keep children", "Keep everyone", "Thank you for making it safe"];

type Kind = "wait" | "why" | "safety" | "queue" | "override" | "worse" | "footer" | "other";

function kindOf(line: string): Kind {
  if (line.startsWith("Expect a tradesperson") || line.startsWith("Once everyone is safe")) return "wait";
  if (SAFETY.some((p) => line.startsWith(p))) return "safety";
  if (/^(Your repair is in the|You told us:|We asked:|It is )/.test(line)) return "why";
  if (/^(You are number|Where you live)/.test(line)) return "queue";
  if (line.startsWith("A staff member changed")) return "override";
  if (line.startsWith("If we have missed something")) return "worse";
  if (/^(A staff member will confirm|Reference )/.test(line)) return "footer";
  return "other";
}

/**
 * The tenant's record. The words are exactly what the service wrote and
 * verified; this only decides where each one sits. The wait comes first,
 * in bold, because it is what a tenant most wants to know.
 */
export function Docket({
  requestId, tier, explanation, address, community,
}: { requestId: string; tier: Tier; explanation: string; address?: string | null; community?: string }) {
  const paras = paragraphs(explanation);
  const emergency = tier !== "NotInQueue" && paras[0]?.[0]?.startsWith(EMERGENCY);
  const rest = emergency ? paras.slice(1) : paras;
  const groups: Record<Kind, string[][]> = { wait: [], why: [], safety: [], queue: [], override: [], worse: [], footer: [], other: [] };
  for (const p of rest) groups[kindOf(p[0])].push(p);

  const wait = groups.wait[0];
  const s = tierStyle[tier];
  const headline = wait?.[0] ?? (tier === "NotInQueue" ? rest[0]?.[0] : undefined);
  const headlineRest = wait ? wait.slice(1) : tier === "NotInQueue" ? rest[0]?.slice(1) ?? [] : [];
  const whyLines = groups.why.flat().filter((l) => !l.startsWith("Your repair is in the"));
  const other = tier === "NotInQueue" ? rest.slice(1).filter((p) => kindOf(p[0]) !== "footer") : groups.other;

  return (
    <article aria-label="Your repair record" className="overflow-hidden rounded-3xl border border-line bg-paper shadow-md">
      {emergency && (
        <div role="alert" className="flex items-start gap-3 bg-immediate px-5 py-4 text-white sm:px-7">
          <Siren className="mt-0.5 size-7 shrink-0" aria-hidden />
          <p className="text-lg font-bold leading-snug">{paras[0].join(" ")}</p>
        </div>
      )}

      {/* the wait, first and in bold */}
      <header className={cx("px-5 pb-6 pt-6 sm:px-7", s.soft)}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-muted">
            <Clock className="size-4" aria-hidden /> {tier === "NotInQueue" ? "Your report" : "When to expect someone"}
          </span>
          <span className={cx("inline-flex items-center gap-1.5 rounded-full bg-paper px-3 py-1 text-sm font-bold ring-1 ring-inset", s.text, s.ring)}>
            <span className={cx("size-2 rounded-full", s.dot)} aria-hidden />
            {s.label} priority
          </span>
        </div>
        {headline && (
          <p className="mt-3 text-2xl font-bold leading-tight text-graphite sm:text-3xl">
            <strong>{headline}</strong>
          </p>
        )}
        {headlineRest.map((l, i) => (
          <p key={i} className="mt-2 text-lg text-graphite/80">{l}</p>
        ))}
      </header>

      <div className="flex flex-col divide-y divide-line">
        {whyLines.length > 0 && (
          <Section icon={<MessageSquareQuote className="size-5" aria-hidden />} title={`Why it is ${s.label}`}>
            <p className="text-muted">{tierMeaning[tier]}</p>
            {whyLines.map((l, i) =>
              l.startsWith("You told us:") || l.startsWith("We asked:") ? (
                <blockquote key={i} className="rounded-xl bg-canvas px-4 py-3 italic">{l}</blockquote>
              ) : (
                <p key={i} className="font-bold">{l}</p>
              ),
            )}
          </Section>
        )}

        {groups.safety.map((lines, i) => (
          <div key={i} className="px-5 py-5 sm:px-7">
            <div className="flex items-start gap-3 rounded-2xl border border-urgent/30 bg-urgent-soft p-4">
              <ShieldCheck className="mt-0.5 size-6 shrink-0 text-urgent" aria-hidden />
              <div className="flex flex-col gap-1">
                <p className="font-bold text-urgent">While you wait</p>
                {lines.map((l, j) => <p key={j} className="text-lg">{l}</p>)}
              </div>
            </div>
          </div>
        ))}

        {groups.queue.length > 0 && (
          <Section icon={<ListOrdered className="size-5" aria-hidden />} title="Your place in the queue">
            {groups.queue.flat().map((l, i) =>
              l.startsWith("Where you live") ? (
                <p key={i} className="flex items-start gap-2 text-routine">
                  <CircleCheck className="mt-1 size-4 shrink-0" aria-hidden />
                  <span>{l}</span>
                </p>
              ) : (
                <p key={i} className="text-lg font-bold">{l}</p>
              ),
            )}
          </Section>
        )}

        {groups.override.map((lines, i) => (
          <Section key={i} icon={<UserCheck className="size-5" aria-hidden />} title="Changed by staff">
            {lines.map((l, j) => <p key={j}>{l}</p>)}
          </Section>
        ))}

        {other.map((lines, i) => (
          <div key={i} className="px-5 py-5 sm:px-7">
            {lines.map((l, j) => <p key={j} className="text-lg">{l}</p>)}
          </div>
        ))}

        {groups.worse.map((lines, i) => (
          <div key={i} className="px-5 py-5 sm:px-7">
            <div className="flex items-start gap-3 rounded-2xl bg-ink-soft p-4 text-ink-strong">
              <ArrowUpRight className="mt-0.5 size-5 shrink-0" aria-hidden />
              <div>
                <p className="font-bold">If it gets worse</p>
                <p>{lines.join(" ")}</p>
              </div>
            </div>
          </div>
        ))}

        <footer className="flex flex-wrap items-end justify-between gap-4 bg-canvas/60 px-5 py-5 sm:px-7">
          <div className="flex flex-col gap-1 text-sm text-muted">
            {(address || community) && (
              <span className="flex items-center gap-1.5 text-graphite">
                <House className="size-4" aria-hidden /> {[address, community].filter(Boolean).join(", ")}
              </span>
            )}
            <span>A staff member will confirm this. You can ask a person to review it.</span>
          </div>
          <CopyRef id={requestId} />
        </footer>
      </div>
    </article>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 px-5 py-5 sm:px-7">
      <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-muted">
        {icon} {title}
      </h3>
      <div className="flex flex-col gap-2 text-lg">{children}</div>
    </section>
  );
}

export function CopyRef({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(id);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          /* clipboard blocked: the number is still visible */
        }
      }}
      className="group flex flex-col items-start rounded-xl border border-line bg-paper px-4 py-2 text-left hover:border-ink"
      aria-label={`Reference number ${id}. Copy it.`}
    >
      <span className="text-xs font-bold uppercase tracking-wide text-muted">Your reference</span>
      <span className="flex items-center gap-2 font-mono text-lg font-bold text-graphite">
        {id}
        {copied ? <Check className="size-4 text-routine" aria-hidden /> : <Copy className="size-4 text-muted group-hover:text-ink" aria-hidden />}
      </span>
      <span aria-live="polite" className="text-xs text-routine">{copied ? "Copied" : ""}</span>
    </button>
  );
}
