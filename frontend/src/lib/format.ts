import type { Tier } from "./api";

export const TIERS: Exclude<Tier, "NotInQueue">[] = ["Immediate", "Urgent", "Routine"];

export const tierStyle: Record<Tier, { text: string; soft: string; ring: string; dot: string; label: string }> = {
  Immediate: { text: "text-immediate", soft: "bg-immediate-soft", ring: "ring-immediate/30", dot: "bg-immediate", label: "Immediate" },
  Urgent: { text: "text-urgent", soft: "bg-urgent-soft", ring: "ring-urgent/30", dot: "bg-urgent", label: "Urgent" },
  Routine: { text: "text-routine", soft: "bg-routine-soft", ring: "ring-routine/30", dot: "bg-routine", label: "Routine" },
  NotInQueue: { text: "text-muted", soft: "bg-canvas", ring: "ring-line", dot: "bg-muted", label: "Not a repair job" },
};

export const tierMeaning: Record<Tier, string> = {
  Immediate: "Can hurt someone today. Made safe first.",
  Urgent: "An essential service is not working.",
  Routine: "Needs fixing, not dangerous.",
  NotInQueue: "Not a repair to book.",
};

export function days(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return "—";
  const v = Number(n.toFixed(digits));
  return `${v} day${v === 1 ? "" : "s"}`;
}

export function hoursOrDays(h: number, workday = 10): string {
  if (h < workday) return `${h.toFixed(1)} h`;
  return `${(h / workday).toFixed(1)} crew days`;
}

export function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-AU", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

const FLAG_LABELS: Record<string, string> = {
  extraction_fallback: "Model unavailable",
  person_hurt: "Person may be hurt",
  emergency_000: "Danger: call 000",
  normalisation_changed_outcome: "Spelling changed the reading",
};

/** Which reader produced a reading, in plain words. */
export function readerName(extractor: string, model?: string | null): string {
  if (extractor.startsWith("keyword")) return "FairTriage triage engine";
  return model ? `${extractor} (${model})` : extractor;
}

export function humanise(code: string): string {
  if (FLAG_LABELS[code]) return FLAG_LABELS[code];
  const s = code.replaceAll("_", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const statusLabel: Record<string, string> = {
  lodged: "Received",
  awaiting_tenant: "Waiting for your answer",
  ranked: "In the queue",
  approved: "Approved by staff",
  scheduled: "Trip booked",
  not_in_queue: "Not a repair job",
  needs_phone_call: "Staff will phone you",
  awaiting_confirmation: "Staff will check with you",
};

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/** Split a stored explanation into paragraphs of lines, as the API writes it. */
export function paragraphs(text: string): string[][] {
  return text
    .split("\n\n")
    .map((b) => b.split("\n").filter((l) => l.trim()))
    .filter((b) => b.length);
}
