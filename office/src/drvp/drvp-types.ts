/**
 * TypeScript types mirroring the Python DRVP schema
 * from `core/oas_core/protocols/drvp.py`.
 */

export const DRVP_EVENT_TYPES = [
  // Request lifecycle
  "request.created",
  "request.routed",
  "request.completed",
  "request.failed",
  // Agent lifecycle
  "agent.activated",
  "agent.thinking",
  "agent.speaking",
  "agent.idle",
  "agent.error",
  // Handoff
  "handoff.started",
  "handoff.completed",
  // Tool usage
  "tool.call.started",
  "tool.call.completed",
  "tool.call.failed",
  // LLM calls
  "llm.call.started",
  "llm.call.completed",
  "llm.call.boosted",
  "llm.stream.token",
  // Memory
  "memory.read",
  "memory.write",
  // Budget
  "budget.check",
  "budget.warning",
  "budget.exhausted",
  // Browser
  "browser.navigate",
  "browser.action",
  "browser.blocked",
  // Campaign
  "campaign.step.started",
  "campaign.step.completed",
  "campaign.approval.required",
  "campaign.approved",
] as const;

export type DRVPEventType = (typeof DRVP_EVENT_TYPES)[number];

export interface DRVPEvent {
  event_id: string;
  event_type: DRVPEventType;
  timestamp: string; // ISO 8601
  request_id: string;
  task_id?: string;
  issue_id?: string;
  agent_name: string;
  device: string; // "leader" | "academic" | "experiment"
  payload: Record<string, unknown>;
  parent_event_id?: string;
}
