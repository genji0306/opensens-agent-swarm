/**
 * Paperclip REST client for Agent Office.
 *
 * Simple fetch wrapper following the method signatures from the Python
 * `PaperclipClient` in `core/oas_core/adapters/paperclip.py`.
 */
import type {
  PaperclipAgent,
  PaperclipCostByAgent,
  PaperclipCostSummary,
  PaperclipDashboard,
  PaperclipIssue,
} from "./paperclip-types";

export class PaperclipClientError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "PaperclipClientError";
  }
}

export class PaperclipRestClient {
  private baseUrl: string;
  private companyId: string;
  private apiKey: string | undefined;

  constructor(baseUrl: string, companyId: string, apiKey?: string) {
    // Strip trailing slash
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.companyId = companyId;
    this.apiKey = apiKey;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers as Record<string, string>) },
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new PaperclipClientError(res.status, detail);
    }
    return res.json();
  }

  private companyPath(suffix: string): string {
    return `/api/companies/${this.companyId}${suffix}`;
  }

  /** Fetch the full dashboard summary. */
  async getDashboard(): Promise<PaperclipDashboard> {
    return this.request(this.companyPath("/dashboard"));
  }

  /** Fetch all agents for this company. */
  async getAgents(): Promise<PaperclipAgent[]> {
    return this.request(this.companyPath("/agents"));
  }

  /** Fetch issues, optionally filtered by status. */
  async getIssues(status?: string): Promise<PaperclipIssue[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request(this.companyPath(`/issues${query}`));
  }

  /** Fetch cost breakdown per agent. */
  async getCostsByAgent(): Promise<PaperclipCostByAgent[]> {
    return this.request(this.companyPath("/costs/by-agent"));
  }

  /** Toggle boost mode for an agent. */
  async toggleBoost(agentId: string, enabled: boolean): Promise<{ boostEnabled: boolean }> {
    return this.request(this.companyPath(`/agents/${agentId}/boost`), {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  }

  /** Get boost status for an agent. */
  async getBoostStatus(agentId: string): Promise<{ boostEnabled: boolean }> {
    return this.request(this.companyPath(`/agents/${agentId}/boost`));
  }

  /** Fetch cost summary for a date range. */
  async getCostSummary(from?: string, to?: string): Promise<PaperclipCostSummary> {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(this.companyPath(`/costs/summary${query}`));
  }
}
