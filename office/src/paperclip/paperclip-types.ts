/**
 * TypeScript types for Paperclip REST API responses.
 *
 * Mirrors the Python `PaperclipClient` in `core/oas_core/adapters/paperclip.py`
 * and the Paperclip shared types from `@paperclipai/shared`.
 */

export interface PaperclipAgent {
  id: string;
  name: string;
  role: string;
  status: string;
  monthlyBudgetCents: number;
  spentThisMonthCents: number;
  avatarIcon?: string;
  metadata?: Record<string, unknown>;
}

/** Helper to check if an agent has boost enabled. */
export function isBoostEnabled(agent: PaperclipAgent): boolean {
  return agent.metadata?.boostEnabled === true;
}

export interface PaperclipIssue {
  id: string;
  identifier: string; // e.g. "DL-47"
  title: string;
  status: string;
  priority: string;
  assigneeAgentId?: string;
  parentId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PaperclipCostSummary {
  totalCents: number;
  periodStart: string;
  periodEnd: string;
  byProvider?: Record<string, number>;
}

export interface PaperclipCostByAgent {
  agentId: string;
  agentName: string;
  totalCents: number;
  budgetCents: number;
}

export interface PaperclipDashboard {
  agents: PaperclipAgent[];
  issues: { total: number; open: number; inProgress: number };
  costs: PaperclipCostSummary;
  pendingApprovals: number;
}

export interface PaperclipLiveEvent {
  id: number;
  companyId: string;
  type: string;
  createdAt: string;
  payload: Record<string, unknown>;
}
