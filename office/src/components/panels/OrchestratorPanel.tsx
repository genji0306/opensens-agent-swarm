/**
 * OrchestratorPanel — plan-file orchestration status (Phase 24).
 *
 * Shows:
 * - Active plans: currently executing plans (from orchestrator.started)
 * - Plan queue: pending plans detected by PlanWatcher (plan.detected)
 * - Step progress: for active plan, show step completion (orchestrator.step_dispatched)
 * - Last completed: most recent completed plan with status
 * - Model tier routing decisions
 *
 * Consumes DRVP events:
 *   plan.detected, plan.parsed, plan.error,
 *   orchestrator.started, orchestrator.step_dispatched,
 *   orchestrator.completed, orchestrator.failed,
 *   campaign.step.routed, decision.recommended
 */
import { useMemo } from "react";
import {
  GitBranch,
  Zap,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Loader2,
} from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import type { DRVPEvent } from "@/drvp/drvp-types";

interface QueuedPlan {
  planId: string;
  filename: string;
  detectedAt: string;
  parsed: boolean;
  parseError: string;
}

interface ActivePlan {
  planId: string;
  title: string;
  totalSteps: number;
  dispatchedSteps: number;
  startedAt: string;
  stepDetails: Array<{ stepIndex: number; target: string; taskType: string }>;
}

interface CompletedPlan {
  planId: string;
  title: string;
  status: "completed" | "failed";
  timestamp: string;
  errorMessage: string;
  stepsCompleted: number;
  totalSteps: number;
}

interface RoutingEntry {
  tier: string;
  model: string;
  reason: string;
  timestamp: string;
}

interface OrchestratorState {
  queuedPlans: QueuedPlan[];
  activePlans: Map<string, ActivePlan>;
  lastCompleted: CompletedPlan | null;
  routingHistory: RoutingEntry[];
}

function extractOrchestratorState(events: readonly DRVPEvent[]): OrchestratorState {
  const queuedMap = new Map<string, QueuedPlan>();
  const activeMap = new Map<string, ActivePlan>();
  let lastCompleted: CompletedPlan | null = null;
  const routingHistory: RoutingEntry[] = [];

  for (const ev of events) {
    switch (ev.event_type) {
      case "plan.detected": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? (p.filename as string) ?? ev.request_id;
        queuedMap.set(planId, {
          planId,
          filename: (p.filename as string) ?? planId,
          detectedAt: ev.timestamp,
          parsed: false,
          parseError: "",
        });
        break;
      }
      case "plan.parsed": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        const queued = queuedMap.get(planId);
        if (queued) {
          queuedMap.set(planId, { ...queued, parsed: true });
        }
        break;
      }
      case "plan.error": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        const queued = queuedMap.get(planId);
        if (queued) {
          queuedMap.set(planId, {
            ...queued,
            parseError: (p.error as string) ?? "Parse error",
          });
        }
        break;
      }
      case "orchestrator.started": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        // Move from queue to active
        queuedMap.delete(planId);
        activeMap.set(planId, {
          planId,
          title: (p.title as string) ?? (p.plan_id as string) ?? planId,
          totalSteps: (p.total_steps as number) ?? 0,
          dispatchedSteps: 0,
          startedAt: ev.timestamp,
          stepDetails: [],
        });
        break;
      }
      case "orchestrator.step_dispatched": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        const active = activeMap.get(planId);
        if (active) {
          const stepIndex = (p.step_index as number) ?? active.dispatchedSteps;
          const target = (p.target as string) ?? (p.device as string) ?? "";
          const taskType = (p.task_type as string) ?? "";
          activeMap.set(planId, {
            ...active,
            dispatchedSteps: active.dispatchedSteps + 1,
            stepDetails: [
              ...active.stepDetails.slice(-4),
              { stepIndex, target, taskType },
            ],
          });
        }
        break;
      }
      case "orchestrator.completed": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        const active = activeMap.get(planId);
        activeMap.delete(planId);
        lastCompleted = {
          planId,
          title: active?.title ?? planId,
          status: "completed",
          timestamp: ev.timestamp,
          errorMessage: "",
          stepsCompleted: active?.dispatchedSteps ?? (p.steps_completed as number) ?? 0,
          totalSteps: active?.totalSteps ?? (p.total_steps as number) ?? 0,
        };
        break;
      }
      case "orchestrator.failed": {
        const p = ev.payload;
        const planId = (p.plan_id as string) ?? ev.request_id;
        const active = activeMap.get(planId);
        activeMap.delete(planId);
        lastCompleted = {
          planId,
          title: active?.title ?? planId,
          status: "failed",
          timestamp: ev.timestamp,
          errorMessage: (p.error as string) ?? "Unknown failure",
          stepsCompleted: active?.dispatchedSteps ?? 0,
          totalSteps: active?.totalSteps ?? (p.total_steps as number) ?? 0,
        };
        break;
      }
      case "campaign.step.routed": {
        const p = ev.payload;
        routingHistory.push({
          tier: (p.tier as string) ?? "",
          model: (p.model as string) ?? "",
          reason: (p.reason as string) ?? "",
          timestamp: ev.timestamp,
        });
        break;
      }
      case "decision.recommended": {
        const p = ev.payload;
        if (p.tier) {
          routingHistory.push({
            tier: (p.tier as string) ?? "",
            model: (p.model as string) ?? "",
            reason: (p.reasoning as string) ?? "",
            timestamp: ev.timestamp,
          });
        }
        break;
      }
    }
  }

  return {
    queuedPlans: Array.from(queuedMap.values()),
    activePlans: activeMap,
    lastCompleted,
    routingHistory: routingHistory.slice(-8),
  };
}

const TIER_COLORS: Record<string, string> = {
  planning_local: "text-blue-500",
  reasoning_local: "text-purple-500",
  code_local: "text-cyan-500",
  worker_local: "text-teal-500",
  rl_evolved: "text-orange-500",
  claude_sonnet: "text-amber-500",
  claude_opus: "text-red-500",
};

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function OrchestratorPanel() {
  const events = useDrvpStore((s) => s.events);
  const { queuedPlans, activePlans, lastCompleted, routingHistory } = useMemo(
    () => extractOrchestratorState(events),
    [events],
  );

  const activePlanList = Array.from(activePlans.values());

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
        <GitBranch className="h-4 w-4" />
        Orchestrator
        {activePlanList.length > 0 && (
          <span className="ml-auto rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-900 dark:text-blue-300">
            {activePlanList.length} active
          </span>
        )}
      </div>

      {/* Plan queue */}
      {queuedPlans.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-zinc-400">
            Queue ({queuedPlans.length})
          </div>
          {queuedPlans.map((plan) => (
            <div
              key={plan.planId}
              className="flex items-center gap-1.5 rounded bg-zinc-50 px-2 py-1 text-xs dark:bg-zinc-800"
            >
              <FileText className="h-3 w-3 text-zinc-400" />
              <span className="truncate text-zinc-600 dark:text-zinc-300">
                {plan.filename}
              </span>
              {plan.parseError ? (
                <AlertTriangle className="ml-auto h-3 w-3 shrink-0 text-red-400" />
              ) : plan.parsed ? (
                <CheckCircle2 className="ml-auto h-3 w-3 shrink-0 text-green-400" />
              ) : (
                <Clock className="ml-auto h-3 w-3 shrink-0 text-zinc-400" />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Active plans */}
      {activePlanList.length > 0 ? (
        <div className="mb-3 space-y-2">
          {activePlanList.map((plan) => (
            <div key={plan.planId} className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
              <div className="flex items-center gap-2 text-xs">
                <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                <span className="font-medium text-zinc-700 dark:text-zinc-200 truncate">
                  {plan.title}
                </span>
                <span className="ml-auto text-[10px] text-zinc-400">
                  {formatTimestamp(plan.startedAt)}
                </span>
              </div>
              {plan.totalSteps > 0 && (
                <div className="mt-1.5">
                  <div className="h-1.5 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-700">
                    <div
                      className="h-full rounded bg-blue-500 transition-all"
                      style={{
                        width: `${(plan.dispatchedSteps / plan.totalSteps) * 100}%`,
                      }}
                    />
                  </div>
                  <div className="mt-0.5 text-right text-[10px] text-zinc-400">
                    {plan.dispatchedSteps}/{plan.totalSteps} steps
                  </div>
                </div>
              )}
              {/* Latest dispatched step detail */}
              {plan.stepDetails.length > 0 && (
                <div className="mt-1 text-[10px] text-zinc-500">
                  Last: {plan.stepDetails[plan.stepDetails.length - 1].taskType}
                  {plan.stepDetails[plan.stepDetails.length - 1].target && (
                    <span className="ml-1 text-zinc-400">
                      → {plan.stepDetails[plan.stepDetails.length - 1].target}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        !lastCompleted &&
        queuedPlans.length === 0 && (
          <p className="mb-3 text-xs text-zinc-400">No active plans</p>
        )
      )}

      {/* Last completed plan */}
      {lastCompleted && (
        <div className="mb-3 flex items-center gap-1.5 rounded bg-zinc-50 px-2 py-1.5 text-xs dark:bg-zinc-800">
          {lastCompleted.status === "completed" ? (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-500" />
          ) : (
            <XCircle className="h-3.5 w-3.5 shrink-0 text-red-500" />
          )}
          <div className="min-w-0 flex-1">
            <span className="font-medium text-zinc-600 dark:text-zinc-300 truncate block">
              {lastCompleted.title}
            </span>
            {lastCompleted.errorMessage && (
              <span className="text-[10px] text-red-400 truncate block">
                {lastCompleted.errorMessage}
              </span>
            )}
          </div>
          <span className="shrink-0 text-[10px] text-zinc-400">
            {lastCompleted.stepsCompleted}/{lastCompleted.totalSteps}
          </span>
        </div>
      )}

      {/* Routing history */}
      {routingHistory.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-400">
            Routing
          </div>
          {routingHistory.map((entry, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-[11px]">
              <Zap
                className={`mt-0.5 h-3 w-3 shrink-0 ${TIER_COLORS[entry.tier] ?? "text-zinc-400"}`}
              />
              <div className="min-w-0">
                <span className="font-medium">{entry.tier}</span>
                {entry.model && (
                  <span className="ml-1 text-zinc-500">({entry.model})</span>
                )}
                {entry.reason && (
                  <p className="text-zinc-400 truncate">{entry.reason}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
