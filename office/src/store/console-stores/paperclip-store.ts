/**
 * Zustand store for Paperclip governance data.
 *
 * Fetches dashboard, agents, issues, and costs from the Paperclip REST API.
 */
import { create } from "zustand";
import { PaperclipRestClient } from "@/paperclip/paperclip-client";
import type {
  PaperclipAgent,
  PaperclipCostByAgent,
  PaperclipDashboard,
  PaperclipIssue,
} from "@/paperclip/paperclip-types";

interface PaperclipStoreState {
  dashboard: PaperclipDashboard | null;
  agents: PaperclipAgent[];
  activeIssues: PaperclipIssue[];
  costsByAgent: PaperclipCostByAgent[];
  isLoading: boolean;
  error: string | null;

  /** Initialize the REST client. Must be called before refresh(). */
  init: (baseUrl: string, companyId: string, apiKey?: string) => void;
  /** Fetch all Paperclip data. */
  refresh: () => Promise<void>;
}

let client: PaperclipRestClient | null = null;

export const usePaperclipStore = create<PaperclipStoreState>((set) => ({
  dashboard: null,
  agents: [],
  activeIssues: [],
  costsByAgent: [],
  isLoading: false,
  error: null,

  init: (baseUrl: string, companyId: string, apiKey?: string) => {
    client = new PaperclipRestClient(baseUrl, companyId, apiKey);
  },

  refresh: async () => {
    if (!client) {
      set({ error: "Paperclip client not initialized" });
      return;
    }

    set({ isLoading: true, error: null });

    try {
      const results = await Promise.allSettled([
        client.getDashboard(),
        client.getAgents(),
        client.getIssues("open"),
        client.getCostsByAgent(),
      ]);

      const dashboard =
        results[0].status === "fulfilled" ? results[0].value : null;
      const agents =
        results[1].status === "fulfilled" ? results[1].value : [];
      const activeIssues =
        results[2].status === "fulfilled" ? results[2].value : [];
      const costsByAgent =
        results[3].status === "fulfilled" ? results[3].value : [];

      const errors: string[] = [];
      for (const [i, label] of ["dashboard", "agents", "issues", "costs"].entries()) {
        if (results[i].status === "rejected") {
          errors.push(`${label}: ${(results[i] as PromiseRejectedResult).reason}`);
        }
      }

      set({
        dashboard,
        agents,
        activeIssues,
        costsByAgent,
        isLoading: false,
        error: errors.length > 0 ? errors.join("; ") : null,
      });
    } catch (err) {
      set({ error: String(err), isLoading: false });
    }
  },
}));
