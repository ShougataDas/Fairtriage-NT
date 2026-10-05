"use client";

import { useState } from "react";
import { HelpCircle, MessageSquareWarning, Send, UserRound } from "lucide-react";
import { post } from "@/lib/api";
import { Button, ErrorBox, inputClass } from "@/components/ui";

type WhyAnswer = { request_id: string; question: string | null; answer: string[] };
type ReviewReply = { reply: string };

const QUICK = ["Why is my repair not first?", "Why has my wait changed?", "Why was my repair moved down?"];

/**
 * The tenant asks why their repair sits where it does and gets an answer built
 * from their record and today's queue. If they are not satisfied, they ask a
 * person to review it: it goes on the coordinator's phone list.
 */
export function AskWhy({ id }: { id: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<WhyAnswer | null>(null);
  const [message, setMessage] = useState("");
  const [review, setReview] = useState<ReviewReply | null>(null);
  const [busy, setBusy] = useState<"why" | "review" | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function ask(q: string) {
    setBusy("why");
    setError(null);
    try {
      setAnswer(await post<WhyAnswer>(`/api/requests/${id}/why`, { question: q.trim() || null }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function sendReview() {
    setBusy("review");
    setError(null);
    try {
      setReview(await post<ReviewReply>(`/api/requests/${id}/review`, { message: message.trim() || null }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Ask why" className="flex flex-col gap-4 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-bold">
          <HelpCircle className="size-5 text-ink" aria-hidden /> Ask why your repair is here
        </h2>
        <p className="mt-1 text-muted">You get an answer from your record and today&apos;s list of repairs, straight away.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button
            key={q}
            type="button"
            disabled={busy !== null}
            onClick={() => {
              setQuestion(q);
              ask(q);
            }}
            className="rounded-full border-2 border-line px-3 py-1.5 text-sm font-bold hover:border-ink hover:text-ink disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor="why-q" className="sr-only">Your question</label>
        <input
          id="why-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder="Or ask in your own words"
          className={inputClass + " flex-1"}
        />
        <Button type="submit" busy={busy === "why"}>
          <Send className="size-4" aria-hidden /> Ask
        </Button>
      </form>

      {answer && (
        <div role="status" className="flex flex-col gap-3 rounded-xl bg-canvas p-4">
          {answer.question && <p className="text-sm font-bold text-muted">You asked: “{answer.question}”</p>}
          {answer.answer.map((p, i) => (
            <p key={i} className={i === 0 ? "text-lg font-bold" : ""}>{p}</p>
          ))}
        </div>
      )}

      <div className="border-t border-line pt-4">
        {review ? (
          <p role="status" className="flex items-start gap-2 font-bold text-routine">
            <UserRound className="mt-0.5 size-5 shrink-0" aria-hidden /> {review.reply}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="flex items-center gap-2 font-bold">
              <MessageSquareWarning className="size-5 text-urgent" aria-hidden /> Think we have got it wrong?
            </p>
            <label htmlFor="review-msg" className="text-sm text-muted">
              Tell us what we missed (optional). A staff member will look at your repair.
            </label>
            <textarea
              id="review-msg"
              rows={2}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={500}
              className={inputClass}
              placeholder="For example: the power point is sparking now, or my mum lives with us and uses oxygen"
            />
            <Button variant="secondary" busy={busy === "review"} onClick={sendReview} className="self-start">
              <UserRound className="size-4" aria-hidden /> Ask a person to review it
            </Button>
          </div>
        )}
      </div>
      {error != null && <ErrorBox error={error} />}
    </section>
  );
}
