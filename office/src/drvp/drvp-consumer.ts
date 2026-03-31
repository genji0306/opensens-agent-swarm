/**
 * DRVP event consumer — bridges incoming DRVP events to the frontend stores.
 *
 * 1. Pushes every event into the drvp-store (circular buffer, active requests)
 * 2. Maps agent lifecycle events to office-store visual status updates
 * 3. Handles handoff animations between agents
 * 4. Triggers budget gauge refresh on budget events
 * 5. Tracks campaign step progress
 */
import type { DRVPEvent, DRVPEventType } from "./drvp-types";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import { useOfficeStore } from "@/store/office-store";
import { usePaperclipStore } from "@/store/console-stores/paperclip-store";
import type { AgentVisualStatus } from "@/gateway/types";

/** Map DRVP event types to Agent Office visual status. */
const DRVP_TO_VISUAL_STATUS: Partial<Record<DRVPEventType, AgentVisualStatus>> = {
  "agent.activated": "thinking",
  "agent.thinking": "thinking",
  "agent.speaking": "speaking",
  "agent.idle": "idle",
  "agent.error": "error",
  "tool.call.started": "tool_calling",
  "tool.call.completed": "thinking",
  "tool.call.failed": "error",
  "llm.call.started": "thinking",
  "llm.call.completed": "thinking",
  "llm.call.boosted": "thinking",
  "request.completed": "idle",
  "request.failed": "error",
  "browser.navigate": "tool_calling",
  "browser.action": "tool_calling",
  "browser.blocked": "error",
};

/** Track active handoff timeouts so we can clean up links. */
const handoffTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
const HANDOFF_LINK_DURATION_MS = 8_000;

/** Track browser-blocked recovery timers per agent to prevent stale overwrites. */
const browserBlockedTimers = new Map<string, ReturnType<typeof setTimeout>>();

/**
 * Dispatch a single DRVP event into the frontend stores.
 * Call this from the SSE onMessage handler.
 */
export function dispatchDrvpEvent(event: DRVPEvent): void {
  // 1. Always push to drvp-store
  useDrvpStore.getState().pushEvent(event);

  // 2. Map to office-store visual status if applicable
  const visualStatus = DRVP_TO_VISUAL_STATUS[event.event_type];
  if (visualStatus) {
    // Cancel any stale browser-blocked recovery timer for this agent
    const existingBbTimer = browserBlockedTimers.get(event.agent_name);
    if (existingBbTimer) {
      clearTimeout(existingBbTimer);
      browserBlockedTimers.delete(event.agent_name);
    }
    useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, visualStatus);
  }

  // 3. Handle specialized events
  switch (event.event_type) {
    case "handoff.started":
      handleHandoffStarted(event);
      break;
    case "handoff.completed":
      handleHandoffCompleted(event);
      break;
    case "budget.warning":
    case "budget.exhausted":
      handleBudgetEvent(event);
      break;
    case "campaign.step.started":
    case "campaign.step.completed":
      handleCampaignStep(event);
      break;
    case "campaign.approval.required":
      handleCampaignApprovalRequired(event);
      break;
    case "browser.blocked":
      handleBrowserBlocked(event);
      break;
    case "request.completed":
    case "request.failed":
      cleanupHandoffLinks(event.request_id);
      break;
    // TurboQuant memory pool events
    case "memory.pool.status":
    case "memory.pool.eviction":
    case "memory.compression.stats":
      handleMemoryPoolEvent(event);
      break;
    // Deep Research events
    case "deep_research.started":
    case "deep_research.iteration":
    case "deep_research.search":
    case "deep_research.scored":
    case "deep_research.completed":
      handleDeepResearchEvent(event);
      break;
    // RL training events
    case "rl.rollout.collected":
    case "rl.training.step":
    case "rl.checkpoint.saved":
    case "rl.evaluation.completed":
    case "rl.checkpoint.promoted":
    case "rl.checkpoint.rolledback":
      handleRLEvent(event);
      break;
    // Debate events
    case "debate.started":
    case "debate.round.completed":
    case "debate.completed":
    case "debate.transcript.ready":
      handleDebateEvent(event);
      break;
    // Decision engine events
    case "decision.recommended":
    case "readiness.scored":
    case "campaign.reflection.completed":
    case "uncertainty.routing":
      handleDecisionEvent(event);
      break;
  }

  // DeerFlow sub-agent progress: update metrics when DeerFlow reports step counts
  if (event.agent_name === "deerflow" && event.event_type === "agent.idle") {
    const steps = event.payload.steps as number | undefined;
    const outputLen = event.payload.output_length as number | undefined;
    if (steps != null || outputLen != null) {
      const store = useOfficeStore.getState();
      store.setAgentVisualStatusByName("deerflow", "idle");
    }
  }
}

// ─── Handoff visualization ─────────────────────────────────────────

function handleHandoffStarted(event: DRVPEvent): void {
  const payload = event.payload;
  const fromAgent = (payload.from_agent as string) || event.agent_name;
  const toAgent = payload.to_agent as string;
  if (!fromAgent || !toAgent) return;

  const store = useOfficeStore.getState();

  // Set from-agent to speaking (handing off) and to-agent to thinking (receiving)
  store.setAgentVisualStatusByName(fromAgent, "speaking");
  store.setAgentVisualStatusByName(toAgent, "thinking");

  // Create a temporary collaboration link between agents.
  // We use addCollaborationLink if available, otherwise update via the
  // drvp-store so the EventTimeline can visualize it.
  const linkKey = `handoff:${event.request_id}:${fromAgent}:${toAgent}`;

  // Auto-remove the link after a duration
  const existingTimeout = handoffTimeouts.get(linkKey);
  if (existingTimeout) clearTimeout(existingTimeout);

  handoffTimeouts.set(
    linkKey,
    setTimeout(() => {
      handoffTimeouts.delete(linkKey);
    }, HANDOFF_LINK_DURATION_MS),
  );
}

function handleHandoffCompleted(event: DRVPEvent): void {
  const payload = event.payload;
  const fromAgent = (payload.from_agent as string) || event.agent_name;
  const toAgent = payload.to_agent as string;

  if (fromAgent) {
    useOfficeStore.getState().setAgentVisualStatusByName(fromAgent, "idle");
  }
  if (toAgent) {
    useOfficeStore.getState().setAgentVisualStatusByName(toAgent, "thinking");
  }
}

function cleanupHandoffLinks(requestId: string): void {
  // Clear all handoff timeouts for this request
  for (const [key, timeout] of handoffTimeouts.entries()) {
    if (key.startsWith(`handoff:${requestId}:`)) {
      clearTimeout(timeout);
      handoffTimeouts.delete(key);
    }
  }
}

// ─── Budget events ─────────────────────────────────────────────────

function handleBudgetEvent(event: DRVPEvent): void {
  // Trigger a Paperclip store refresh so budget gauges update in real-time
  void usePaperclipStore.getState().refresh();

  // Also update the agent's visual status for budget.exhausted
  if (event.event_type === "budget.exhausted") {
    useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "error");
  }
}

// ─── Campaign step tracking ────────────────────────────────────────

function handleCampaignStep(event: DRVPEvent): void {
  const payload = event.payload;
  const stepNumber = payload.step_number as number | undefined;
  const totalSteps = payload.total_steps as number | undefined;

  if (event.event_type === "campaign.step.started") {
    useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
  }

  // Campaign step metadata is already captured in the drvp-store via pushEvent.
  // The RequestsPage and EventTimeline consume this data directly.
  // Log for debugging during development:
  if (stepNumber != null && totalSteps != null) {
    const stepTitle = (payload.step_title as string) || `Step ${stepNumber}`;
    const qualityScore = payload.quality_score as number | undefined;
    // Update the active request in drvp-store with campaign progress
    useDrvpStore.getState().updateCampaignProgress(event.request_id, {
      currentStep: stepNumber,
      totalSteps,
      stepTitle,
      qualityScore,
    });
  }
}

function handleCampaignApprovalRequired(_event: DRVPEvent): void {
  // Trigger Paperclip refresh to show the new approval in the panel
  void usePaperclipStore.getState().refresh();
}

// ─── Browser events ───────────────────────────────────────────────
// browser.navigate and browser.action are handled by DRVP_TO_VISUAL_STATUS map (→ tool_calling).

// ─── TurboQuant memory pool events ───────────────────────────────

function handleMemoryPoolEvent(event: DRVPEvent): void {
  const payload = event.payload;

  switch (event.event_type) {
    case "memory.pool.eviction": {
      // Agent evicted from memory pool — show brief error flash
      const evictedAgent = (payload.agent_id as string) || event.agent_name;
      useOfficeStore.getState().setAgentVisualStatusByName(evictedAgent, "error");
      setTimeout(() => {
        useOfficeStore.getState().setAgentVisualStatusByName(evictedAgent, "idle");
      }, 2_000);
      break;
    }
    case "memory.pool.status":
    case "memory.compression.stats":
      // Informational — captured in drvp-store via pushEvent
      // Future: update a dedicated TurboQuant dashboard panel
      break;
  }
}

// ─── Deep Research events ────────────────────────────────────────

function handleDeepResearchEvent(event: DRVPEvent): void {
  const payload = event.payload;

  switch (event.event_type) {
    case "deep_research.started":
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
      break;
    case "deep_research.iteration": {
      const iteration = payload.iteration as number | undefined;
      const total = payload.total as number | undefined;
      if (iteration != null && total != null) {
        useDrvpStore.getState().updateCampaignProgress(event.request_id, {
          currentStep: iteration,
          totalSteps: total,
          stepTitle: `Research iteration ${iteration}`,
        });
      }
      break;
    }
    case "deep_research.search":
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "tool_calling");
      break;
    case "deep_research.scored": {
      const passed = payload.passed as boolean | undefined;
      if (passed) {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "speaking");
      }
      break;
    }
    case "deep_research.completed":
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "idle");
      break;
  }
}

// ─── RL training events ──────────────────────────────────────────

function handleRLEvent(event: DRVPEvent): void {
  const payload = event.payload;

  switch (event.event_type) {
    case "rl.checkpoint.promoted":
      // Agent just got upgraded — show brief "speaking" animation
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "speaking");
      setTimeout(() => {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "idle");
      }, 3_000);
      break;
    case "rl.checkpoint.rolledback":
      // Agent rolled back — brief error flash then idle
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "error");
      setTimeout(() => {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "idle");
      }, 2_000);
      break;
    case "rl.training.step":
      // Training in progress — agent shows as "thinking"
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
      break;
    default:
      // rl.rollout.collected, rl.checkpoint.saved, rl.evaluation.completed
      // These are informational — just captured in drvp-store via pushEvent
      break;
  }
}

// ─── Debate events ──────────────────────────────────────────────

function handleDebateEvent(event: DRVPEvent): void {
  const payload = event.payload;

  switch (event.event_type) {
    case "debate.started":
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
      break;
    case "debate.round.completed": {
      const round = payload.round as number | undefined;
      const totalRounds = payload.total_rounds as number | undefined;
      if (round != null && totalRounds != null) {
        useDrvpStore.getState().updateCampaignProgress(event.request_id, {
          currentStep: round,
          totalSteps: totalRounds,
          stepTitle: `Debate round ${round}`,
        });
      }
      break;
    }
    case "debate.completed":
      useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "speaking");
      setTimeout(() => {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "idle");
      }, 3_000);
      break;
    case "debate.transcript.ready":
      // Transcript ready for training — informational
      break;
  }
}

// ─── Browser events ───────────────────────────────────────────────
// browser.navigate and browser.action are handled by DRVP_TO_VISUAL_STATUS map (→ tool_calling).

// ─── Decision engine events ─────────────────────────────────────

function handleDecisionEvent(event: DRVPEvent): void {
  const payload = event.payload;

  switch (event.event_type) {
    case "decision.recommended": {
      const action = payload.action as string | undefined;
      if (action === "escalate_to_human") {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "speaking");
      }
      // Decision data captured in drvp-store via pushEvent for DecisionPanel
      break;
    }
    case "readiness.scored": {
      // Informational — captured in drvp-store for panels
      break;
    }
    case "campaign.reflection.completed": {
      const rec = payload.recommendation as string | undefined;
      if (rec === "retry_with_refinement") {
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
      }
      break;
    }
    case "uncertainty.routing": {
      const shouldProceed = payload.should_proceed as boolean | undefined;
      if (!shouldProceed) {
        // Routing blocked — show brief thinking state
        useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "thinking");
      }
      break;
    }
  }
}

// ─── Browser events ───────────────────────────────────────────────

function handleBrowserBlocked(event: DRVPEvent): void {
  // Domain blocked → brief error state, then auto-recover to thinking
  const agentName = event.agent_name;
  useOfficeStore.getState().setAgentVisualStatusByName(agentName, "error");

  // Cancel any existing recovery timer for this agent
  const existing = browserBlockedTimers.get(agentName);
  if (existing) clearTimeout(existing);

  browserBlockedTimers.set(
    agentName,
    setTimeout(() => {
      browserBlockedTimers.delete(agentName);
      useOfficeStore.getState().setAgentVisualStatusByName(agentName, "thinking");
    }, 3_000),
  );
}
