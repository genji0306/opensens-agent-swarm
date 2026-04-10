/**
 * EvalPanel — OAS eval harness status card (Phase 25).
 *
 * Shows:
 * - Latest avg score across all fixtures
 * - Per-dimension breakdown (completeness, accuracy, source_quality, synthesis, cost_efficiency)
 * - Regression detection badge with delta from previous run
 * - Pass/fail ratio
 *
 * Consumes DRVP events:
 *   eval.run.completed, eval.regression.detected
 */
import { useMemo } from "react";
import { Gauge, TrendingDown, TrendingUp, Minus } from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import type { DRVPEvent } from "@/drvp/drvp-types";

const DIMENSIONS = [
  "completeness",
  "accuracy",
  "source_quality",
  "synthesis",
  "cost_efficiency",
] as const;

type Dimension = (typeof DIMENSIONS)[number];

interface EvalState {
  lastRun: string;
  total: number;
  passed: number;
  failed: number;
  avgScore: number;
  previousAvgScore: number | null;
  perDimension: Record<Dimension, number>;
  regressionDetected: boolean;
  regressionDelta: number;
}

const EMPTY_DIMS: Record<Dimension, number> = {
  completeness: 0,
  accuracy: 0,
  source_quality: 0,
  synthesis: 0,
  cost_efficiency: 0,
};

function extractEvalState(events: readonly DRVPEvent[]): EvalState {
  let lastRun = "";
  let total = 0;
  let passed = 0;
  let failed = 0;
  let avgScore = 0;
  let previousAvgScore: number | null = null;
  let perDimension: Record<Dimension, number> = { ...EMPTY_DIMS };
  let regressionDetected = false;
  let regressionDelta = 0;

  let sawRun = false;
  for (const ev of events) {
    switch (ev.event_type) {
      case "eval.run.completed": {
        if (sawRun) previousAvgScore = avgScore;
        total = (ev.payload.total as number) ?? 0;
        passed = (ev.payload.passed as number) ?? 0;
        failed = (ev.payload.failed as number) ?? 0;
        avgScore = (ev.payload.avg_score as number) ?? 0;
        const dims = ev.payload.per_dimension as Record<string, number> | undefined;
        if (dims) {
          perDimension = { ...EMPTY_DIMS };
          for (const d of DIMENSIONS) {
            if (typeof dims[d] === "number") perDimension[d] = dims[d];
          }
        }
        lastRun = ev.timestamp;
        sawRun = true;
        break;
      }
      case "eval.regression.detected": {
        regressionDetected = true;
        regressionDelta = (ev.payload.delta as number) ?? 0;
        break;
      }
    }
  }

  return {
    lastRun,
    total,
    passed,
    failed,
    avgScore,
    previousAvgScore,
    perDimension,
    regressionDetected,
    regressionDelta,
  };
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function scoreColor(score: number): string {
  if (score >= 4.0) return "bg-green-500";
  if (score >= 3.5) return "bg-lime-500";
  if (score >= 2.5) return "bg-amber-500";
  return "bg-red-500";
}

function dimensionLabel(d: Dimension): string {
  return d.replace("_", " ");
}

export function EvalPanel() {
  const events = useDrvpStore((s) => s.events);
  const state = useMemo(() => extractEvalState(events), [events]);

  const hasRun = state.total > 0;
  const scorePct = (state.avgScore / 5.0) * 100;
  const deltaFromPrev =
    state.previousAvgScore !== null ? state.avgScore - state.previousAvgScore : 0;
  const DeltaIcon =
    deltaFromPrev > 0.1 ? TrendingUp : deltaFromPrev < -0.1 ? TrendingDown : Minus;
  const deltaColor =
    deltaFromPrev > 0.1
      ? "text-green-500"
      : deltaFromPrev < -0.1
        ? "text-red-500"
        : "text-zinc-400";

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
        <Gauge className="h-4 w-4" />
        Eval Harness
        {state.regressionDetected && (
          <span className="ml-auto rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-900 dark:text-red-300">
            Regression {state.regressionDelta.toFixed(2)}
          </span>
        )}
      </div>

      {!hasRun ? (
        <p className="text-[11px] text-zinc-400">No eval runs yet this session</p>
      ) : (
        <>
          {/* Main score */}
          <div className="mb-3">
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-zinc-700 dark:text-zinc-200">
                {state.avgScore.toFixed(2)}
                <span className="text-sm font-normal text-zinc-400">/5.0</span>
              </span>
              {state.previousAvgScore !== null && (
                <span className={`flex items-center gap-0.5 text-xs ${deltaColor}`}>
                  <DeltaIcon className="h-3 w-3" />
                  {deltaFromPrev >= 0 ? "+" : ""}
                  {deltaFromPrev.toFixed(2)}
                </span>
              )}
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-700">
              <div
                className={`h-full rounded transition-all ${scoreColor(state.avgScore)}`}
                style={{ width: `${Math.min(scorePct, 100)}%` }}
              />
            </div>
          </div>

          {/* Pass/fail */}
          <div className="mb-3 flex justify-between text-xs text-zinc-500">
            <span>
              <span className="text-green-600 dark:text-green-400">{state.passed}</span> passed
            </span>
            <span>
              <span className="text-red-600 dark:text-red-400">{state.failed}</span> failed
            </span>
            <span>{state.total} total</span>
          </div>

          {/* Per-dimension bars */}
          <div className="mb-2 space-y-1">
            {DIMENSIONS.map((dim) => {
              const score = state.perDimension[dim];
              return (
                <div key={dim} className="flex items-center gap-2 text-[10px]">
                  <span className="w-20 shrink-0 capitalize text-zinc-500">
                    {dimensionLabel(dim)}
                  </span>
                  <div className="h-1 flex-1 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-700">
                    <div
                      className={`h-full rounded ${scoreColor(score)}`}
                      style={{ width: `${(score / 5.0) * 100}%` }}
                    />
                  </div>
                  <span className="w-8 text-right text-zinc-600 dark:text-zinc-300">
                    {score.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Last run */}
          <div className="text-[11px] text-zinc-400">
            Last run: {formatTimestamp(state.lastRun)}
          </div>
        </>
      )}
    </div>
  );
}
