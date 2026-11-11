import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { CaseDetail, QueueQuery, ReviewRequest } from "./types";

const ACTIVE = new Set(["NEW", "PROCESSING"]);

export function useQueue(q: QueueQuery) {
  return useQuery({
    queryKey: ["queue", q],
    queryFn: () => api.queue(q),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  });
}

/** Polls every 1.5s while the agent is still working on the case. */
export function useCase(id: number) {
  return useQuery({
    queryKey: ["case", id],
    queryFn: () => api.case(id),
    refetchInterval: (query) => {
      const data = query.state.data as CaseDetail | undefined;
      return data && ACTIVE.has(data.status) ? 1500 : false;
    },
  });
}

export function useConfig() {
  return useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
}

export function useReasonCodes() {
  return useQuery({ queryKey: ["reason-codes"], queryFn: api.reasonCodes, staleTime: Infinity });
}

export function useCustomers(q: string) {
  return useQuery({
    queryKey: ["customers", q],
    queryFn: () => api.customers(q),
    placeholderData: keepPreviousData,
  });
}

export function useReview(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReviewRequest) => api.review(id, body),
    onSuccess: (data) => {
      qc.setQueryData(["case", id], data);
      void qc.invalidateQueries({ queryKey: ["queue"] });
      void qc.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export function useRerun(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.process(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["case", id] });
      void qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}

export function useRecentTxns(customerId: number | null) {
  return useQuery({
    queryKey: ["recent-txns", customerId],
    queryFn: () => api.recentTxns(customerId as number),
    enabled: customerId !== null,
  });
}

export function useMetrics() {
  return useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 30_000 });
}
