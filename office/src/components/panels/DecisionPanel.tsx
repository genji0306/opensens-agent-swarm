/**
 * DecisionPanel — displays the latest decision recommendation and readiness radar.
 * Reads decision engine DRVP events from the drvp-store event buffer.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Brain, Target, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";

const ACTION_ICONS: Record<string, typeof Brain> = {
  proceed_to_next_step: CheckCircle,
  handoff_to: Target,
  escalate_to_human: AlertTriangle,
  stop_insufficient_evidence: XCircle,
  retry_with_refinement: Brain,
  stay_in_module: CheckCircle,
};

const ACTION_COLORS: Record<string, string> = {
  proceed_to_next_step: "text-green-500",
  handoff_to: "text-blue-500",
  escalate_to_human: "text-amber-500",
  stop_insufficient_evidence: "text-red-500",
  retry_with_refinement: "text-purple-500",
  stay_in_module: "text-green-400",
};

interface ReadinessData {
  overall: number;
  dimensions: Record<string, { score: number; breakdown: Record<string, number> }>;
}

export function DecisionPanel() {
  const { t } = useTranslation("panels");
  const events = useDrvpStore((s) => s.events);

  // Find latest decision and readiness events
  const { latestDecision, latestReadiness } = useMemo(() => {
    let decision: Record<string, unknown> | null = null;
    let readiness: ReadinessData | null = null;

    // Scan from most recent
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (!decision && ev.event_type === "decision.recommended") {
        decision = ev.payload as Record<string, unknown>;
      }
      if (!readiness && ev.event_type === "readiness.scored") {
        readiness = ev.payload as unknown as ReadinessData;
      }
      if (decision && readiness) break;
    }
    return { latestDecision: decision, latestReadiness: readiness };
  }, [events]);

  const action = (latestDecision?.action as string) || "—";
  const confidence = (latestDecision?.confidence as number) ?? 0;
  const reasoning = (latestDecision?.reasoning as string) || "";
  const targetModule = (latestDecision?.target_module as string) || "";

  const Icon = ACTION_ICONS[action] || Brain;
  const iconColor = ACTION_COLORS[action] || "text-gray-500";

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center gap-2">
        <Brain className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Decision Engine
        </h3>
      </div>

      {!latestDecision ? (
        <p className="text-xs text-gray-400">No decisions recorded yet</p>
      ) : (
        <div className="space-y-3">
          {/* Action badge */}
          <div className="flex items-center gap-2">
            <Icon className={`h-5 w-5 ${iconColor}`} />
            <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {action.replace(/_/g, " ")}
            </span>
            {targetModule && (
              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                → {targetModule}
              </span>
            )}
          </div>

          {/* Confidence bar */}
          <div>
            <div className="mb-1 flex justify-between text-xs text-gray-500">
              <span>Confidence</span>
              <span>{(confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700">
              <div
                className="h-1.5 rounded-full bg-indigo-500 transition-all"
                style={{ width: `${confidence * 100}%` }}
              />
            </div>
          </div>

          {/* Reasoning */}
          {reasoning && (
            <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
              {reasoning}
            </p>
          )}

          {/* Readiness radar (simplified bar chart) */}
          {latestReadiness && (
            <div className="space-y-1.5 pt-1">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
                Readiness ({(latestReadiness.overall * 100).toFixed(0)}%)
              </p>
              {Object.entries(latestReadiness.dimensions).map(([dim, data]) => (
                <div key={dim} className="flex items-center gap-2">
                  <span className="w-20 text-xs text-gray-500 capitalize truncate">
                    {dim}
                  </span>
                  <div className="flex-1 h-1 rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className="h-1 rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${data.score * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-8 text-right">
                    {(data.score * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
