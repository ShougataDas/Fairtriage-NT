import Link from "next/link";
import { ArrowRight, ClipboardList, Search, Siren, Wrench } from "lucide-react";

export default function Home() {
  return (
    <div className="flex flex-col gap-8">
      <div
        role="note"
        className="flex items-start gap-3 rounded-2xl border border-immediate/30 bg-immediate-soft p-4 text-immediate sm:items-center"
      >
        <Siren className="size-6 shrink-0" aria-hidden />
        <p className="font-bold">
          If there is a fire, or anyone is hurt, call <a className="underline" href="tel:000">000</a> now. Do not wait for a repair.
        </p>
      </div>

      <div className="max-w-3xl">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Something broken at home?</h1>
        <p className="mt-4 text-xl text-muted">
          Tell us in your own words. Short is fine. We will tell you how urgent it is, roughly when someone can come, and why.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <HomeCard
          href="/report"
          icon={<Wrench className="size-6" aria-hidden />}
          title="Report a repair"
          body="Describe what is wrong. It takes about a minute."
          primary
        />
        <HomeCard
          href="/track"
          icon={<Search className="size-6" aria-hidden />}
          title="Track a repair"
          body="Use the reference number you were given, like NTF3-00012-ab34."
        />
        <HomeCard
          href="/coordinator"
          icon={<ClipboardList className="size-6" aria-hidden />}
          title="Staff area"
          body="Review the queue, approve recommendations and plan trips."
        />
      </div>

      <section className="grid gap-6 rounded-2xl border border-line bg-paper p-6 sm:grid-cols-3">
        {[
          ["Danger comes first", "Sparks, gas, sewage inside, a house that cannot be locked: these are made safe before anything else."],
          ["Where you live does not change your place", "A job in Wadeye ranks exactly where the same job in Darwin would. Only the travel time differs, and we say so."],
          ["A person checks every decision", "The system recommends. Staff approve, and you can ask a person to review it."],
        ].map(([t, b]) => (
          <div key={t}>
            <h2 className="font-bold">{t}</h2>
            <p className="mt-1 text-muted">{b}</p>
          </div>
        ))}
      </section>
    </div>
  );
}

function HomeCard({ href, icon, title, body, primary }: { href: string; icon: React.ReactNode; title: string; body: string; primary?: boolean }) {
  return (
    <Link
      href={href}
      className={
        "group flex flex-col gap-3 rounded-2xl border p-6 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md " +
        (primary ? "border-ink bg-ink text-white" : "border-line bg-paper text-graphite")
      }
    >
      <span className={"grid size-11 place-items-center rounded-xl " + (primary ? "bg-white/15" : "bg-ink-soft text-ink")}>{icon}</span>
      <span className="text-xl font-bold">{title}</span>
      <span className={primary ? "text-white/85" : "text-muted"}>{body}</span>
      <span className="mt-auto inline-flex items-center gap-1 font-bold">
        Open <ArrowRight className="size-4 transition group-hover:translate-x-0.5" aria-hidden />
      </span>
    </Link>
  );
}
