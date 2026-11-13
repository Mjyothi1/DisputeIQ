import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getCustomerToken } from "./auth";
import { portal } from "./client";
import type { PortalComplaint, PortalComplaintDetail } from "./types";

const PENDING = new Set(["SUBMITTED", "PROCESSING"]);
const key = () => getCustomerToken().slice(-12); // re-fetch per session, never share between users

export const usePortalMe = () =>
  useQuery({ queryKey: ["portal", key(), "me"], queryFn: portal.me, retry: false });
export const usePortalTxns = () =>
  useQuery({ queryKey: ["portal", key(), "txns"], queryFn: portal.transactions });
export const usePortalCategories = () =>
  useQuery({ queryKey: ["portal-categories"], queryFn: portal.categories, staleTime: Infinity });

export function usePortalComplaints() {
  return useQuery({
    queryKey: ["portal", key(), "complaints"],
    queryFn: portal.complaints,
    refetchInterval: (q) =>
      (q.state.data as PortalComplaint[] | undefined)?.some((c) => PENDING.has(c.status)) ? 3000 : false,
  });
}

export function usePortalComplaint(id: number) {
  return useQuery({
    queryKey: ["portal", key(), "complaint", id],
    queryFn: () => portal.complaint(id),
    refetchInterval: (q) => {
      const d = q.state.data as PortalComplaintDetail | undefined;
      return d && PENDING.has(d.status) ? 2500 : false;
    },
  });
}

export function useReportProblem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: portal.report,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["portal"] }),
  });
}
