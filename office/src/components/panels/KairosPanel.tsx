/**
 * KairosPanel — KAIROS ambient daemon status card (Phase 24).
 *
 * Shows:
 * - Status indicator: green (running) / yellow (idle) / red (stopped)
 * - Last heartbeat timestamp + budget ratio
 * - autoDream: last run date, entries processed
 * - Suggestions queue: count of pending suggestions
 * - Budget gate: current daily spend ratio vs 20% threshold
 *
 * Consumes DRVP events:
 *   kairos.heartbeat, kairos.blocked, kairos.autodream.started,
 *   kairos.autodream.completed, kairos.proactive.suggestion,
 *   kairos.rollout.curated
 */
import { useMemo } from "react";
import { Moon, Lightbulb, Activity, Clock, Zap } from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import type { DRVPEvent } from "@/drvp/drvp-types";

type DaemonStatus = "running" | "idle" | "stopped";

interface KairosState {
  status: DaemonStatus;
  blocked: boolean;
  budgetRatio: number;
  lastHeartbeat: string;
  autoDreamRunning: boolean;
  lastAutoDream: {
    succeeded: boolean;
    entriesBefore: number;
    entriesAfter: number;
    date: string;
  } | null;
  suggestions: Array<{
    kind: string;
    topic: string;
    rationale: string;
    priority: number;
    timestamp: string;
  }>;
  curatedRollouts: number;
}

function extractKairosState(events: readonly DRVPEvent[]): KairosState {
  let status: DaemonStatus = "idle";
  let blocked = false;
  let budgetRatio = 0;
  let lastHeartbeat = "";
  let autoDreamRunning = false;
  let lastAutoDream: KairosState["lastAutoDream"] = null;
  let curatedRollouts = 0;
  const suggestions: KairosState["suggestions"] = [];

  for (const ev of events) {
    switch (ev.event_type) {
      case "kairos.heartbeat": {
        status = "running";
        budgetRatio = (ev.payload.budget_ratio as number) ?? 0;
        blocked = (ev.payload.budget_blocked as boolean) ?? false;
        lastHeartbeat = ev.timestamp;
        break;
      }
      case "kairos.blocked": {
        blocked = true;
        budgetRatio = (ev.payload.ratio as number) ?? budgetRatio;
        break;
      }
      case "kairos.autodream.started": {
        autoDreamRunning = true;
        break;
      }
      case "kairos.autodream.completed": {
        autoDreamRunning = false;
        lastAutoDream = {
          succeeded: (ev.payload.succeeded as boolean) ?? false,
          entriesBefore: (ev.payload.entries_before as number) ?? 0,
          entriesAfter: (ev.payload.entries_after as number) ?? 0,
          date: ev.timestamp,
        };
        break;
      }
      case "kairos.proactive.suggestion": {
        suggestions.push({
          kind: (ev.payload.kind as string) ?? "",
          topic: (ev.payload.topic as string) ?? "",
          rationale: (ev.payload.rationale as string) ?? "",
          priority: (ev.payload.priority as number) ?? 1,
          timestamp: ev.timestamp,
        });
        break;
      }
      case "kairos.rollout.curated": {
        curatedRollouts += 1;
        break;
      }
    }
  }

  return {
    status,
    blocked,
    budgetRatio,
    lastHeartbeat,
    autoDreamRunning,
    lastAutoDream,
    suggestions: suggestions.slice(-5),
    curatedRollouts,
  };
}

const KIND_LABELS: Record<string, string> = {
  research_gap: "Gap",
  low_confidence: "Low conf.",
  rl_curation: "RL trace",
  knowledge_decay: "Decay",
  cross_domain: "X-domain",
};

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

const STATUS_CONFIG: Record<DaemonStatus, { label: string; bg: string; text: string }> = {
  running: {
    label: "Running",
    bg: "bg-green-100 dark:bg-green-900",
    text: "text-green-700 dark:text-green-300",
  },
  idle: {
    label: "Idle",
    bg: "bg-zinc-100 dark:bg-zinc-800",
    text: "text-zinc-500 dark:text-zinc-400",
  },
  stopped: {
    label: "Stopped",
    bg: "bg-red-100 dark:bg-red-900",
    text: "text-red-700 dark:text-red-300",
  },
};

export function KairosPanel() {
  const events = useDrvpStore((s) => s.events);
  const state = useMemo(() => extractKairosState(events), [events]);

  const displayStatus: DaemonStatus = state.blocked ? "stopped" : state.status;
  const statusCfg = STATUS_CONFIG[displayStatus];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
        <Moon className="h-4 w-4" />
        KAIROS
        <span className={`ml-auto rounded px-1.5 py-0.5 text-xs ${statusCfg.bg} ${statusCfg.text}`}>
          {state.blocked ? "Budget blocked" : statusCfg.label}
        </span>
      </div>

      {/* Last heartbeat */}
      {state.lastHeartbeat && (
        <div className="mb-2 flex items-center gap-1.5 text-[11px] text-zinc-500">
          <Clock className="h-3 w-3" />
          Last heartbeat: {formatTimestamp(state.lastHeartbeat)}
        </div>
      )}

      {/* Budget ratio bar */}
      <div className="mb-3">
        <div className="mb-0.5 flex justify-between text-[10px] text-zinc-500">
          <span>Idle budget</span>
          <span>{(state.budgetRatio * 100).toFixed(0)}% / 20%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-700">
          <div
            className={`h-full rounded transition-all ${
              state.budgetRatio > 0.2 ? "bg-red-500" : "bg-green-500"
            }`}
            style={{ width: `${Math.min(state.budgetRatio * 500, 100)}%` }}
          />
        </div>
      </div>

      {/* autoDream status */}
      <div className="mb-3 flex items-center gap-1.5 text-xs text-zinc-500">
        <Activity className="h-3 w-3" />
        {state.autoDreamRunning ? (
          <span className="text-amber-500">autoDream running...</span>
        ) : state.lastAutoDream ? (
          <>
            autoDream: {state.lastAutoDream.entriesBefore} → {state.lastAutoDream.entriesAfter} entries
            {state.lastAutoDream.succeeded ? (
              <span className="text-green-500">done</span>
            ) : (
              <span className="text-red-500">failed</span>
            )}
            <span className="ml-auto text-[10px] text-zinc-400">
              {formatTimestamp(state.lastAutoDream.date)}
            </span>
          </>
        ) : (
          <span className="text-zinc-400">No autoDream runs yet</span>
        )}
      </div>

      {/* Curated rollouts count */}
      {state.curatedRollouts > 0 && (
        <div className="mb-3 flex items-center gap-1.5 text-xs text-zinc-500">
          <Zap className="h-3 w-3 text-orange-400" />
          {state.curatedRollouts} rollout{state.curatedRollouts !== 1 ? "s" : ""} curated
        </div>
      )}

      {/* Suggestions queue */}
      <div className="space-y-1">
        <div className="flex items-center gap-1 text-xs font-medium text-zinc-600 dark:text-zinc-300">
          <Lightbulb className="h-3 w-3" />
          Suggestions
          {state.suggestions.length > 0 && (
            <span className="ml-1 rounded-full bg-amber-100 px-1.5 text-[10px] text-amber-700 dark:bg-amber-900 dark:text-amber-300">
              {state.suggestions.length}
            </span>
          )}
        </div>
        {state.suggestions.length === 0 ? (
          <p className="text-[11px] text-zinc-400">No pending suggestions</p>
        ) : (
          state.suggestions.map((s, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-[11px]">
              <span className="shrink-0 rounded bg-zinc-100 px-1 text-zinc-500 dark:bg-zinc-800">
                {KIND_LABELS[s.kind] ?? s.kind}
              </span>
              <span className="text-zinc-600 dark:text-zinc-400 line-clamp-1">
                {s.topic}: {s.rationale}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
