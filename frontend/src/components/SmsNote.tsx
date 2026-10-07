import { MessageSquare, TriangleAlert } from "lucide-react";
import type { SmsResult } from "@/lib/api";

/** Tells the tenant, truthfully, whether their reference and message were texted. */
export function SmsNote({ sms, reference }: { sms?: SmsResult | null; reference: string }) {
  if (!sms || sms.status === "no_number") return null;
  const ok = sms.status === "sent";
  return (
    <div
      role="status"
      className={
        ok
          ? "flex items-start gap-3 rounded-2xl border border-routine/30 bg-routine-soft p-4"
          : "flex items-start gap-3 rounded-2xl border border-urgent/30 bg-urgent-soft p-4"
      }
    >
      {ok ? (
        <MessageSquare className="mt-0.5 size-5 shrink-0 text-routine" aria-hidden />
      ) : (
        <TriangleAlert className="mt-0.5 size-5 shrink-0 text-urgent" aria-hidden />
      )}
      <p>
        {ok && (
          <>
            We have texted your reference number and this message to <strong>{sms.to}</strong>. If you lose it, use{" "}
            <strong>Track a repair</strong> and we can text your reference again.
          </>
        )}
        {sms.status === "demo" && (
          <>
            <strong>Demo:</strong> a text with your reference and this message is ready for <strong>{sms.to}</strong>, but no text
            service is connected yet, so it was not sent. Write down your reference: <strong className="font-mono">{reference}</strong>.
          </>
        )}
        {sms.status === "failed" && (
          <>
            We could not send a text to <strong>{sms.to}</strong>. Write down your reference:{" "}
            <strong className="font-mono">{reference}</strong>.
          </>
        )}
      </p>
    </div>
  );
}
