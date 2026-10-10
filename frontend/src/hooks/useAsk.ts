import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AskRequest } from "@/api/types";

/** Ask a free-form question over one or more bids. */
export function useAsk() {
  return useMutation({ mutationFn: (body: AskRequest) => api.ask(body) });
}
