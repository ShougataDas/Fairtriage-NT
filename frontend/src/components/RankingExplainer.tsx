"use client";

import { useMemo, useState } from "react";
import { ArrowDown, Calculator, Scale, Sigma } from "lucide-react";
import type { RankedJob, RankingPolicy } from "@/lib/api";
import { TIERS, cx, tierStyle } from "@/lib/format";
import { Card, CardTitle, TierBadge } from "@/components/ui";

const HABITABILITY: Record<string, string> = {
  uninhabitable: "The house cannot be lived in",
  severely_impaired: "A big part of the house is unusable",
  impaired: "Something important does not work",
  cosmetic: "It only looks bad",
  none: "It does not affect living there",
};

const VULNERABILITY: Record<string, string> = {
  none: "Nobody listed",
  children: "Children",
  elderly: "Older people",
  disability: "Someone with a disability",
  medical_equipment: "Someone on medical equipment",
};

const FACTORS: { key: keyof RankingPolicy["need_weights"]; name: string; plain: string }[] = [
  { key: "habitability", name: "How badly it affects living there", plain: "Can the family still use the house?" },
  { key: "vulnerability", name: "Who lives in the house", plain: "Children, older people, disability, medical equipment" },
  { key: "containment", name: "Can it still hurt someone", plain: "Lower if the tenant has already made it safe" },
  { key: "extent", name: "How much of the house", plain: "The whole house, or one room or fitting" },
];

const days = (d: number) => (d < 1 ? `${Math.round(d * 24)} hours` : `${d} days`);

/** Step by step: which tier, then who goes first inside it. */
export function HowRankingWorks({ policy }: { policy: RankingPolicy }) {
  const t = policy.service_targets_days;
  const ladder: { q: string; example: string; tier: (typeof TIERS)[number] | "000"; target?: string }[] = [
    { q: "Is someone's life at risk right now?", example: "fire, someone hurt, violence", tier: "000" },
    { q: "Can it hurt someone today?", example: "sparking, gas smell, sewage inside, house cannot be locked", tier: "Immediate",
      target: `made safe within ${days(t.Immediate.urban)}` },
    { q: "Is an essential service lost?", example: "no water, no power, the only toilet, no way to cook", tier: "Urgent",
      target: `${days(t.Urgent.urban)} in town · ${days(t.Urgent.remote)} remote` },
    { q: "Anything else", example: "a cracked window, a dripping tap, a torn flyscreen", tier: "Routine",
      target: `${days(t.Routine.urban)} in town · ${days(t.Routine.remote)} remote` },
  ];

  return (
    <Card>
      <CardTitle icon={<Scale className="size-5 text-ink" aria-hidden />}>How a job gets its place in line</CardTitle>
      <p className="-mt-2 mb-6 text-muted">
        Three simple steps, the same for every house in the Territory. <strong className="text-graphite">Where the house is never counts.</strong>
      </p>

      <ol className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <li>
          <h3 className="mb-1 font-bold"><StepNo n={1} /> How serious is it?</h3>
          <p className="mb-4 text-sm text-muted">The questions are asked top to bottom. The first “yes” sets the group, called a tier.</p>
          <div className="flex flex-col">
            {ladder.map((r, i) => (
              <div key={r.q}>
                <div className="flex flex-col gap-2 rounded-xl border border-line bg-paper p-3 sm:flex-row sm:items-center sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-bold">{r.q}</p>
                    <p className="text-sm text-muted">e.g. {r.example}</p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-col sm:items-end sm:gap-1 sm:text-right">
                    {r.tier === "000" ? (
                      <span className="rounded-full bg-immediate px-2.5 py-1 text-sm font-bold text-white">Call 000 · top of line</span>
                    ) : (
                      <TierBadge tier={r.tier} size="sm" />
                    )}
                    {r.target && <span className="text-xs text-muted">{r.target}</span>}
                  </div>
                </div>
                {i < ladder.length - 1 && (
                  <div className="flex items-center gap-2 py-1 pl-4 text-xs text-muted">
                    <ArrowDown className="size-4" aria-hidden /> if no
                  </div>
                )}
              </div>
            ))}
          </div>
          <p className="mt-3 rounded-xl bg-canvas p-3 text-sm">
            A lower tier can <strong>never</strong> jump above a higher one, however long it has waited. A dripping tap that
            has waited a month still goes after a sparking power point reported today.
          </p>
        </li>

        <li>
          <h3 className="mb-1 font-bold"><StepNo n={2} /> Inside a tier: who needs it most?</h3>
          <p className="mb-4 text-sm text-muted">Each job gets a need score out of 100 from four facts. Higher goes first.</p>
          <WeightBars policy={policy} />
          <h3 className="mb-1 mt-6 font-bold"><StepNo n={3} /> Same score?</h3>
          <p className="text-sm text-muted">Whoever reported first goes first.</p>
        </li>
      </ol>
    </Card>
  );
}

function StepNo({ n }: { n: number }) {
  return <span className="mr-1 inline-flex size-6 items-center justify-center rounded-full bg-ink text-sm text-white">{n}</span>;
}

/** How much each fact can add to the need score, with distance shown at zero. */
function WeightBars({ policy }: { policy: RankingPolicy }) {
  const w = policy.need_weights;
  return (
    <ul className="flex flex-col gap-3" aria-label="How much each fact counts">
      {FACTORS.map((f) => {
        const pct = Math.round(w[f.key] * 100);
        return (
          <li key={f.key}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span className="font-bold">{f.name}</span>
              <span className="font-bold tabular-nums">{pct}%</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-canvas">
              <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-0.5 text-xs text-muted">{f.plain}</p>
          </li>
        );
      })}
      <li>
        <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
          <span className="font-bold">Distance from Darwin</span>
          <span className="font-bold tabular-nums text-routine">0%</span>
        </div>
        <div className="h-3 rounded-full border-2 border-dashed border-line" />
        <p className="mt-0.5 text-xs text-muted">Not a weight set to zero: the score has no place to put distance at all.</p>
      </li>
    </ul>
  );
}

/** Pick the facts of a job and watch its need score build up. */
export function NeedCalculator({ policy }: { policy: RankingPolicy }) {
  const [hab, setHab] = useState("severely_impaired");
  const [vul, setVul] = useState("children");
  const [safe, setSafe] = useState(false);
  const [whole, setWhole] = useState(false);
  const [place, setPlace] = useState("Darwin");

  const w = policy.need_weights;
  const parts = [
    { key: "habitability", label: "Affects living there", score: policy.habitability_score[hab] ?? 0, weight: w.habitability },
    { key: "vulnerability", label: "Who lives there", score: vul === "none" ? 0 : policy.vulnerability_score[vul] ?? 0, weight: w.vulnerability },
    { key: "containment", label: "Can still hurt someone",
      score: safe ? policy.containment_score.tenant_made_safe : policy.containment_score.not_contained, weight: w.containment },
    { key: "extent", label: "How much of the house",
      score: whole ? policy.extent_score.whole_dwelling : policy.extent_score.one_fixture, weight: w.extent },
  ].map((p) => ({ ...p, points: Math.round(p.score * p.weight * 1000) / 10 }));
  const total = Math.round(parts.reduce((s, p) => s + p.points, 0) * 10) / 10;

  const sel = "w-full rounded-lg border border-line bg-paper px-3 py-2";
  return (
    <Card>
      <CardTitle icon={<Calculator className="size-5 text-ink" aria-hidden />}>Try it: work out a need score</CardTitle>
      <p className="-mt-2 mb-5 text-muted">Change the facts and watch the score. Then change the place: the score does not move.</p>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="grid gap-3">
          <label className="grid gap-1 text-sm font-bold">How badly does it affect living there?
            <select className={sel} value={hab} onChange={(e) => setHab(e.target.value)}>
              {Object.keys(policy.habitability_score).map((k) => <option key={k} value={k}>{HABITABILITY[k] ?? k}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-bold">Who lives in the house?
            <select className={sel} value={vul} onChange={(e) => setVul(e.target.value)}>
              {["none", ...Object.keys(policy.vulnerability_score)].map((k) => <option key={k} value={k}>{VULNERABILITY[k] ?? k}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input type="checkbox" className="size-4" checked={whole} onChange={(e) => setWhole(e.target.checked)} /> The whole house is affected
          </label>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input type="checkbox" className="size-4" checked={safe} onChange={(e) => setSafe(e.target.checked)} /> The tenant has already made it safe
          </label>
          <label className="grid gap-1 text-sm font-bold">Where is the house?
            <select className={sel} value={place} onChange={(e) => setPlace(e.target.value)}>
              {["Darwin", "Palmerston", "Katherine", "Wadeye", "Maningrida", "Galiwinku", "Numbulwar"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
        </div>

        <div aria-live="polite">
          <p className="text-sm font-bold text-muted">Need score</p>
          <p className="text-5xl font-bold tabular-nums">{total}<span className="text-xl text-muted"> / 100</span></p>
          <ul className="mt-4 flex flex-col gap-2">
            {parts.map((p) => (
              <li key={p.key} className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-2 text-sm">
                <span>{p.label}</span>
                <div className="h-3 overflow-hidden rounded-full bg-canvas">
                  <div className="h-full rounded-full bg-ink transition-all" style={{ width: `${(p.points / (p.weight * 100)) * 100}%` }} />
                </div>
                <span className="text-right font-bold tabular-nums">+{p.points}</span>
              </li>
            ))}
            <li className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-2 text-sm">
              <span>Where: {place}</span>
              <div className="h-3 rounded-full border-2 border-dashed border-line" />
              <span className="text-right font-bold tabular-nums text-routine">+0</span>
            </li>
          </ul>
          <p className="mt-3 text-xs text-muted">
            Each bar fills up to that fact&apos;s share ({Object.values(w).map((x) => Math.round(x * 100)).join(" + ")} = 100).
            Life at risk right now scores {policy.emergency_need} outright.
          </p>
        </div>
      </div>
    </Card>
  );
}

/** One real job: its place in line where it is, and if the house were in Darwin. */
export function SameRepairTwoPlaces({ jobs }: { jobs: RankedJob[] }) {
  const job = useMemo(() => {
    // A typical case, not the most extreme one: an Urgent remote job if there
    // is one, with the middle-sized gap between its wait and Darwin's.
    const remote = jobs.filter((j) => j.remote && j.darwin_rank != null && j.wait_days != null && j.wait_days_darwin != null);
    for (const tier of ["Urgent", "Immediate", "Routine"]) {
      const js = remote.filter((j) => j.tier === tier)
        .sort((a, b) => (a.wait_days! - a.wait_days_darwin!) - (b.wait_days! - b.wait_days_darwin!));
      if (js.length) return js[Math.floor(js.length / 2)];
    }
    return undefined;
  }, [jobs]);
  if (!job) return null;
  const extra = Math.round(job.wait_days! - job.wait_days_darwin!);

  return (
    <Card>
      <CardTitle icon={<Sigma className="size-5 text-ink" aria-hidden />}>A real job from the queue</CardTitle>
      <p className="-mt-2 mb-5 text-muted">
        The same repair, worked out twice: once where the house really is, and once as if it were in Darwin.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {[
          { where: job.community, rank: job.rank, wait: job.wait_days!, note: "where the house is" },
          { where: "Darwin", rank: job.darwin_rank!, wait: job.wait_days_darwin!, note: "if the same house were in Darwin" },
        ].map((s) => (
          <div key={s.note} className={cx("rounded-2xl p-4 ring-1 ring-inset", tierStyle[job.tier].soft, tierStyle[job.tier].ring)}>
            <p className="text-sm text-muted">{s.note}</p>
            <p className="text-xl font-bold">{s.where}</p>
            <div className="mt-3 flex flex-wrap items-end gap-6">
              <div>
                <p className="text-sm text-muted">Place in line</p>
                <p className="text-4xl font-bold tabular-nums">#{s.rank}</p>
                <p className="text-sm">in {job.tier}</p>
              </div>
              <div>
                <p className="text-sm text-muted">Expected wait</p>
                <p className="text-4xl font-bold tabular-nums">{s.wait < 1 ? Math.max(1, Math.round(s.wait * 24)) : Math.round(s.wait)}</p>
                <p className="text-sm">{s.wait < 1 ? "hours" : Math.round(s.wait) === 1 ? "day" : "days"}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 font-bold">
        {job.rank === job.darwin_rank ? "Same place in line." : "Different place in line: this should never happen."}{" "}
        {extra > 0 && <span className="font-normal">The extra {extra === 1 ? "day comes" : `${extra} days come`} from travel and from waiting for a crew to go out there, not from a lower priority.</span>}
      </p>
    </Card>
  );
}

const W = 260, H = 200, PAD = 34;

/** Every open job: its place in line against its place if it were in Darwin. On the line means equal. */
export function RankCheckChart({ jobs }: { jobs: RankedJob[] }) {
  const [hover, setHover] = useState<RankedJob | null>(null);
  const groups = TIERS.map((tier) => ({ tier, jobs: jobs.filter((j) => j.tier === tier && j.darwin_rank != null) }))
    .filter((g) => g.jobs.length > 0);
  if (groups.length === 0) return null;

  return (
    <Card>
      <CardTitle>Check every job: is the place in line the same as in Darwin?</CardTitle>
      <p className="-mt-2 mb-3 text-muted">
        Each dot is one open job. Across: its place in line. Up: its place if the house were in Darwin.
        Dots on the diagonal line mean the place did not change. A dot off the line would mean location changed a rank.
      </p>
      <div className="mb-3 flex flex-wrap gap-4 text-sm" aria-label="Legend">
        <span className="flex items-center gap-1.5"><svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="5" className="fill-ink" /></svg> Remote community</span>
        <span className="flex items-center gap-1.5"><svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="4.5" className="fill-paper stroke-ink" strokeWidth="2" /></svg> Town</span>
        <span className="flex items-center gap-1.5"><svg width="18" height="12" aria-hidden><line x1="0" y1="11" x2="18" y2="1" className="stroke-muted" strokeDasharray="3 3" strokeWidth="1.5" /></svg> Same place</span>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {groups.map(({ tier, jobs: js }) => {
          const max = Math.max(...js.map((j) => Math.max(j.rank, j.darwin_rank!)), 2);
          const x = (r: number) => PAD + ((r - 1) / (max - 1)) * (W - PAD - 10);
          const y = (r: number) => H - PAD - ((r - 1) / (max - 1)) * (H - PAD - 10);
          const same = js.filter((j) => j.rank === j.darwin_rank).length;
          return (
            <figure key={tier} className="rounded-xl border border-line p-3">
              <figcaption className="mb-1 flex items-baseline justify-between gap-2">
                <span className={cx("font-bold", tierStyle[tier].text)}>{tier}</span>
                <span className="text-xs text-muted">{same} of {js.length} on the line</span>
              </figcaption>
              <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
                aria-label={`${tier}: ${same} of ${js.length} jobs have the same place in line as in Darwin`}>
                <line x1={PAD} y1={H - PAD} x2={W - 10} y2={H - PAD} className="stroke-line" />
                <line x1={PAD} y1={10} x2={PAD} y2={H - PAD} className="stroke-line" />
                <line x1={x(1)} y1={y(1)} x2={x(max)} y2={y(max)} className="stroke-muted" strokeDasharray="4 4" strokeWidth="1.5" />
                <text x={PAD} y={H - PAD + 16} className="fill-muted text-[10px]">1</text>
                <text x={W - 10} y={H - PAD + 16} textAnchor="end" className="fill-muted text-[10px]">#{max}</text>
                <text x={(PAD + W) / 2} y={H - 4} textAnchor="middle" className="fill-muted text-[10px]">place in line</text>
                <text x={PAD - 6} y={y(max) + 4} textAnchor="end" className="fill-muted text-[10px]">#{max}</text>
                <text x={10} y={(H - PAD) / 2} transform={`rotate(-90 10 ${(H - PAD) / 2})`} textAnchor="middle"
                  className="fill-muted text-[10px]">if in Darwin</text>
                {js.map((j) => (
                  <g key={j.request_id} onMouseEnter={() => setHover(j)} onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(j)} onBlur={() => setHover(null)} tabIndex={0} className="cursor-default outline-none">
                    <circle cx={x(j.rank)} cy={y(j.darwin_rank!)} r={10} fill="transparent" />
                    <circle cx={x(j.rank)} cy={y(j.darwin_rank!)} r={j.remote ? 4.5 : 4}
                      className={cx(j.remote ? "fill-ink stroke-paper" : "fill-paper stroke-ink",
                        hover?.request_id === j.request_id && "stroke-graphite")}
                      strokeWidth={2} />
                  </g>
                ))}
              </svg>
            </figure>
          );
        })}
      </div>
      <p className="mt-3 min-h-6 text-sm" aria-live="polite">
        {hover
          ? <><strong>{hover.request_id}</strong> · {hover.community} ({hover.remote ? "remote" : "town"}) · {hover.tier} #{hover.rank}, in Darwin #{hover.darwin_rank} · need {hover.need}</>
          : <span className="text-muted">Point at a dot to see the job.</span>}
      </p>
    </Card>
  );
}
