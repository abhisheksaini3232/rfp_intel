import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export const bidsQueryKey = ["bids"] as const;

/** All bids known to the API (list page + bid switcher).
 *
 * Polls every 3 s while an upload is still being indexed, so the card flips
 * from "indexing" to "indexed" on its own, then stops polling.
 */
export function useBids() {
  return useQuery({
    queryKey: bidsQueryKey,
    queryFn: api.listBids,
    refetchInterval: (query) =>
      query.state.data?.some((bid) => bid.indexing) ? 3_000 : false,
  });
}

/** Documents and index stats of one bid. */
export function useBidDetail(bidId: string | undefined) {
  return useQuery({
    queryKey: ["bid", bidId],
    queryFn: () => api.getBid(bidId as string),
    enabled: Boolean(bidId),
  });
}

/** Remove a bid everywhere (index, outputs, uploaded files); refreshes the bid list on success. */
export function useRemoveBid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bidId: string) => api.removeBid(bidId),
    onSuccess: (_result, bidId) => {
      queryClient.removeQueries({ queryKey: ["bid", bidId] });
      void queryClient.invalidateQueries({ queryKey: bidsQueryKey });
    },
  });
}
