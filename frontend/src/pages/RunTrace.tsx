import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
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
        {run.data && (
          <Link
            to={`/bids/${encodeURIComponent(run.data.bid_id)}`}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" /> {run.data.bid_id}
          </Link>
        )}
        <h1 className="text-2xl font-semibold tracking-tight">Run trace</h1>
        <p className="font-mono text-sm text-muted-foreground">{runId}</p>
      </div>

      {run.isLoading && <ListSkeleton rows={6} />}
      {run.isError && (
        <ErrorState title="Could not load the run" message={run.error.message} onRetry={() => void run.refetch()} />
      )}
      {run.data && (
        <Card>
          <CardContent className="p-5">
            <RunSteps steps={run.data.steps} status={run.data.status} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
