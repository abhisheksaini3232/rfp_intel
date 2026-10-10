import { useEffect, useRef, useState, type FormEvent } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";
import { ChatMessage, type ChatEntry } from "@/components/ChatMessage";
import { EmptyState } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAsk } from "@/hooks/useAsk";
import { useBids } from "@/hooks/useBids";
import { SUGGESTED_QUESTIONS } from "@/lib/questions";
import { cn } from "@/lib/utils";

let counter = 0;
const nextId = () => `m${++counter}`;

/** Ask page: chat over one or more bids with cited answers. */
export function AskPage() {
  const bids = useBids();
  const ask = useAsk();
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length, ask.isPending]);

  const toggleBid = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const submit = (text: string) => {
    const q = text.trim();
    if (!q || ask.isPending) return;
    setEntries((prev) => [...prev, { kind: "question", id: nextId(), text: q }]);
    setQuestion("");
    ask.mutate(
      { question: q, bid_ids: selected.length ? selected : undefined },
      {
        onSuccess: (answer) => setEntries((prev) => [...prev, { kind: "answer", id: nextId(), answer }]),
        onError: (err) => setEntries((prev) => [...prev, { kind: "error", id: nextId(), text: err.message }]),
      },
    );
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(question);
  };

  return (
    <div className="flex h-[calc(100vh-7.5rem)] flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ask</h1>
          <p className="text-sm text-muted-foreground">Every answer cites the exact passages it was built from.</p>
        </div>
        <fieldset className="flex flex-wrap items-center justify-end gap-1.5">
          <legend className="sr-only">Bids in scope</legend>
          <span className="mr-1 text-xs text-muted-foreground">Scope:</span>
          {(bids.data ?? []).map((b) => {
            const on = selected.includes(b.bid_id);
            return (
              <button
                key={b.bid_id}
                type="button"
                role="checkbox"
                aria-checked={on}
                onClick={() => toggleBid(b.bid_id)}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 font-mono text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  on ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {b.bid_id}
              </button>
            );
          })}
          {bids.data && bids.data.length > 0 && (
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {selected.length === 0 ? "all bids" : `${selected.length} selected`}
            </Badge>
          )}
        </fieldset>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border bg-muted/30 p-4">
        {entries.length === 0 && (
          <EmptyState
            title="Ask anything about the bids"
            message="Pick a suggested question or type your own. Leave the scope empty to search every bid."
          />
        )}
        {entries.map((entry) => (
          <ChatMessage key={entry.id} entry={entry} />
        ))}
        {ask.isPending && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Thinking...
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => submit(q)}
              disabled={ask.isPending}
              className="inline-flex items-center gap-1 rounded-full border bg-card px-3 py-1 text-xs hover:border-primary/60 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Sparkles className="h-3 w-3 text-primary" /> {q}
            </button>
          ))}
        </div>
        <form onSubmit={onSubmit} className="flex gap-2">
          <Input
            aria-label="Question"
            placeholder="Ask a question about the bids..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={ask.isPending}
          />
          <Button type="submit" disabled={!question.trim() || ask.isPending}>
            <Send /> Ask
          </Button>
        </form>
      </div>
    </div>
  );
}
