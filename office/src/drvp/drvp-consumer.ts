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

function handleBrowserBlocked(event: DRVPEvent): void {
  // Domain blocked → brief error state, then auto-recover to thinking
  useOfficeStore.getState().setAgentVisualStatusByName(event.agent_name, "error");
  const agentName = event.agent_name;
  setTimeout(() => {
    useOfficeStore.getState().setAgentVisualStatusByName(agentName, "thinking");
  }, 3_000);
}
