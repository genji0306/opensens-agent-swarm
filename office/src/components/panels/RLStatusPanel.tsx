/**
 * RL Training Status Panel — shows per-agent RL evolution state,
 * checkpoint history, and training metrics from DRVP events.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useDrvpStore } from "@/store/console-stores/drvp-store";

export function RLStatusPanel() {
  const { t } = useTranslation("panels");
  const events = useDrvpStore((s) => s.events);

  const rlEvents = useMemo(() => {
    return events.filter((e) => e.event_type.startsWith("rl.")).slice(-20);
  }, [events]);

  const lastCheckpoint = useMemo(() => {
    const checkpoints = rlEvents.filter(
      (e) => e.event_type === "rl.checkpoint.saved" || e.event_type === "rl.checkpoint.promoted",
    );
    return checkpoints[checkpoints.length - 1];
  }, [rlEvents]);

  const rolloutCount = useMemo(() => {
    return rlEvents.filter((e) => e.event_type === "rl.rollout.collected").length;
  }, [rlEvents]);

  const trainingSteps = useMemo(() => {
    return rlEvents.filter((e) => e.event_type === "rl.training.step").length;
  }, [rlEvents]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
        RL Self-Evolution
      </h3>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-md bg-blue-50 p-2 dark:bg-blue-900/20">
          <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
            {rolloutCount}
          </div>
          <div className="text-xs text-gray-500">Rollouts</div>
        </div>
        <div className="rounded-md bg-green-50 p-2 dark:bg-green-900/20">
          <div className="text-lg font-bold text-green-600 dark:text-green-400">
            {trainingSteps}
          </div>
          <div className="text-xs text-gray-500">Train Steps</div>
        </div>
        <div className="rounded-md bg-purple-50 p-2 dark:bg-purple-900/20">
          <div className="text-lg font-bold text-purple-600 dark:text-purple-400">
            {lastCheckpoint ? "Active" : "Idle"}
          </div>
          <div className="text-xs text-gray-500">Status</div>
        </div>
      </div>

      {lastCheckpoint && (
        <div className="mt-3 rounded-md bg-gray-50 p-2 text-xs dark:bg-gray-700">
          <div className="font-medium text-gray-700 dark:text-gray-300">
            Latest: {lastCheckpoint.event_type.replace("rl.", "")}
          </div>
          <div className="text-gray-500">
            {(lastCheckpoint.payload.agent_type as string) || lastCheckpoint.agent_name}
            {lastCheckpoint.payload.score != null && (
              <> — score: {String(lastCheckpoint.payload.score)}</>
            )}
          </div>
        </div>
      )}

      {rlEvents.length === 0 && (
        <p className="mt-2 text-xs text-gray-400">
          No RL events yet. Training starts when rollouts accumulate.
        </p>
      )}
    </div>
  );
}
