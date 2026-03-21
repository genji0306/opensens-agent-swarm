/**
 * Zustand store for DRVP (Dynamic Request Visualization Protocol) events.
 *
 * Maintains a circular buffer of recent events, tracks active requests,
 * maps agents to their current Paperclip issues, and tracks campaign progress.
 */
import { enableMapSet } from "immer";
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { DRVPEvent } from "@/drvp/drvp-types";

enableMapSet();

const EVENT_BUFFER_LIMIT = 500;

export interface CampaignProgress {
  currentStep: number;
  totalSteps: number;
  stepTitle: string;
  qualityScore?: number;
}

export interface ActiveRequest {
  requestId: string;
  agentName: string;
  startedAt: string;
  lastEventType: string;
  issueId?: string;
  /** Campaign progress tracking (populated for multi-step campaigns). */
  campaign?: CampaignProgress;
}

interface DrvpStoreState {
  /** Circular buffer of recent DRVP events (newest last). */
  events: DRVPEvent[];
  /** Active (in-progress) requests keyed by request_id. */
  activeRequests: Map<string, ActiveRequest>;
  /** Agent name → current issue_id mapping. */
  agentIssueMap: Map<string, string>;

  /** Push a new DRVP event into the store. */
  pushEvent: (event: DRVPEvent) => void;
  /** Update campaign progress for an active request. */
  updateCampaignProgress: (requestId: string, progress: CampaignProgress) => void;
  /** Clear all state. */
  clear: () => void;
}

export const useDrvpStore = create<DrvpStoreState>()(
  immer((set) => ({
    events: [],
    activeRequests: new Map(),
    agentIssueMap: new Map(),

    pushEvent: (event: DRVPEvent) => {
      set((state) => {
        // Circular buffer: trim from front if over limit
        state.events.push(event);
        if (state.events.length > EVENT_BUFFER_LIMIT) {
          state.events = state.events.slice(state.events.length - EVENT_BUFFER_LIMIT);
        }

        // Track active requests
        const { request_id, event_type, agent_name, issue_id } = event;

        if (event_type === "request.created") {
          state.activeRequests.set(request_id, {
            requestId: request_id,
            agentName: agent_name,
            startedAt: event.timestamp,
            lastEventType: event_type,
            issueId: issue_id,
          });
        } else if (
          event_type === "request.completed" ||
          event_type === "request.failed"
        ) {
          state.activeRequests.delete(request_id);
        } else if (state.activeRequests.has(request_id)) {
          const req = state.activeRequests.get(request_id)!;
          req.lastEventType = event_type;
          if (issue_id) req.issueId = issue_id;
        }

        // Track agent → issue mapping
        if (issue_id) {
          state.agentIssueMap.set(agent_name, issue_id);
        }
      });
    },

    updateCampaignProgress: (requestId: string, progress: CampaignProgress) => {
      set((state) => {
        const req = state.activeRequests.get(requestId);
        if (req) {
          req.campaign = progress;
        }
      });
    },

    clear: () => {
      set((state) => {
        state.events = [];
        state.activeRequests = new Map();
        state.agentIssueMap = new Map();
      });
    },
  })),
);
