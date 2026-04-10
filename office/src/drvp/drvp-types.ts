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
  // TurboQuant memory
  "memory.pool.status",
  "memory.pool.eviction",
  "memory.compression.stats",
  // Deep Research lifecycle
  "deep_research.started",
  "deep_research.iteration",
  "deep_research.search",
  "deep_research.scored",
  "deep_research.completed",
  // RL training lifecycle
  "rl.rollout.collected",
  "rl.training.step",
  "rl.checkpoint.saved",
  "rl.evaluation.completed",
  "rl.checkpoint.promoted",
  "rl.checkpoint.rolledback",
  // Debate lifecycle
  "debate.started",
  "debate.round.completed",
  "debate.completed",
  "debate.transcript.ready",
  // Decision engine
  "decision.recommended",
  "readiness.scored",
  "campaign.reflection.completed",
  "uncertainty.routing",
  // Campaign orchestration
  "campaign.step.retrying",
  "campaign.step.cascade_failed",
  "campaign.step.routed",
  // Plan-file orchestrator (v2 Phase 24)
  "plan.detected",
  "plan.parsed",
  "plan.error",
  "orchestrator.started",
  "orchestrator.step_dispatched",
  "orchestrator.completed",
  "orchestrator.failed",
  // KAIROS ambient daemon (v2 Phase 24)
  "kairos.heartbeat",
  "kairos.blocked",
  "kairos.autodream.started",
  "kairos.autodream.completed",
  "kairos.proactive.suggestion",
  "kairos.rollout.curated",
  // Research router (v2 Phase 24)
  "research.backend.started",
  "research.backend.completed",
  "research.backend.failed",
  "research.synthesis.started",
  "research.synthesis.completed",
  // Compute pool / borrowing (v2 Phase 24)
  "compute.borrow.requested",
  "compute.borrow.accepted",
  "compute.borrow.rejected",
  "compute.borrow.completed",
  "compute.capability.published",
  "compute.priority_floor.changed",
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
