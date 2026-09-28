"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Button, Field, inputClass } from "@/components/ui";

export default function TrackPage() {
  const router = useRouter();
  const [ref, setRef] = useState("");
  const clean = ref.trim().toUpperCase();
  const valid = /^NTF3-\d{5}-[0-9A-F]{4}$/.test(clean);

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-3xl font-bold tracking-tight">Track a repair</h1>
      <p className="mt-2 text-lg text-muted">Enter the reference number you were given when you reported it.</p>
      <form
        className="mt-6 flex flex-col gap-4 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-7"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) router.push(`/track/${clean.slice(0, 11)}${clean.slice(11).toLowerCase()}`);
        }}
      >
        <Field label="Reference number" hint="like NTF3-00012-ab34" htmlFor="ref">
          <input
            id="ref"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="NTF3-00000-0000"
            className={inputClass + " font-mono text-lg"}
          />
        </Field>
        {ref && !valid && <p className="text-muted">A reference looks like NTF3, five digits, then four letters or numbers.</p>}
        <Button type="submit" disabled={!valid} className="self-start">
          <Search className="size-5" aria-hidden /> Find my repair
        </Button>
      </form>
    </div>
  );
}
