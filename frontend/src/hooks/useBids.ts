import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export const bidsQueryKey = ["bids"] as const;

/** All bids known to the API (list page + bid switcher). */
export function useBids() {
  return useQuery({ queryKey: bidsQueryKey, queryFn: api.listBids });
}

/** Documents and index stats of one bid. */
export function useBidDetail(bidId: string | undefined) {
  return useQuery({
    queryKey: ["bid", bidId],
    queryFn: () => api.getBid(bidId as string),
    enabled: Boolean(bidId),
  });
}
