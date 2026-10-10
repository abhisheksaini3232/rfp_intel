import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import type { RunStatus } from "@/api/types";
import { bidsQueryKey } from "./useBids";
import { recordQueryKey } from "./useRecord";

export const POLL_INTERVAL_MS = 1500;

function isFinished(status: RunStatus | undefined): boolean {
  return status?.status === "done" || status?.status === "failed";
}

/** Poll one run every 1.5 s until it is done or failed. */
export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => (isFinished(query.state.data) ? false : POLL_INTERVAL_MS),
  });
}

/**
 * Start an extraction for a bid and follow its progress. When the run
 * finishes, the record and bid list are refetched.
 */
export function useExtractRun(bidId: string) {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | undefined>();
  const [settled, setSettled] = useState(false);

  const start = useMutation({
    mutationFn: () => api.extract(bidId),
    onSuccess: (data) => {
      setSettled(false);
      setRunId(data.run_id);
    },
  });

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => (isFinished(query.state.data) ? false : POLL_INTERVAL_MS),
  });

  const finished = isFinished(run.data);
  useEffect(() => {
    if (!finished || settled) return;
    setSettled(true);
    void queryClient.invalidateQueries({ queryKey: recordQueryKey(bidId) });
    void queryClient.invalidateQueries({ queryKey: bidsQueryKey });
  }, [finished, settled, bidId, queryClient]);

  const reset = useCallback(() => {
    setRunId(undefined);
    setSettled(false);
  }, []);

  const conflict = start.error instanceof ApiError && start.error.status === 409;

  return {
    start: start.mutate,
    starting: start.isPending,
    startError: start.error,
    conflict,
    runId,
    status: run.data,
    running: Boolean(runId) && !finished,
    finished,
    reset,
  };
}
