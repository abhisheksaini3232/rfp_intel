import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ChatMessage } from "@/components/ChatMessage";
import { RunSteps } from "@/components/RunSteps";
import { ErrorState, ListSkeleton } from "@/components/States";
import { Card, CardContent } from "@/components/ui/card";
import { useRun } from "@/hooks/useExtractRun";

/** Full step timeline of one run (/runs/:runId). */
export function RunTracePage() {
  const { runId = "" } = useParams<{ runId: string }>();
  const run = useRun(runId);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        {run.data && run.data.kind === "qa" && (
          <Link to="/ask" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3 w-3" /> Ask
          </Link>
        )}
        {run.data && run.data.kind !== "qa" && (
          <Link
            to={`/bids/${encodeURIComponent(run.data.bid_id)}`}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" /> {run.data.bid_id}
          </Link>
        )}
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          {run.data?.kind === "qa" ? "Question trace" : "Run trace"}
        </h1>
        <p className="break-all font-mono text-xs text-muted-foreground sm:text-sm">{runId}</p>
      </div>

      {run.isLoading && <ListSkeleton rows={6} />}
      {run.isError && (
        <ErrorState title="Could not load the run" message={run.error.message} onRetry={() => void run.refetch()} />
      )}
      {run.data?.kind === "qa" && run.data.answer && (
        <ChatMessage entry={{ kind: "answer", id: run.data.run_id, answer: run.data.answer }} />
      )}
      {run.data?.status === "failed" && run.data.error && (
        <ChatMessage entry={{ kind: "error", id: `${run.data.run_id}-error`, text: run.data.error }} />
      )}
      {run.data && (
        <Card>
          <CardContent className="p-4 sm:p-5">
            <RunSteps steps={run.data.steps} status={run.data.status} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
