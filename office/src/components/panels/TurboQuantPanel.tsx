/**
 * TurboQuant Memory Panel — shows compressed KV cache pool utilization,
 * per-agent memory usage, and compression ratios from DRVP events.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useDrvpStore } from "@/store/console-stores/drvp-store";

export function TurboQuantPanel() {
  const { t } = useTranslation("panels");
  const events = useDrvpStore((s) => s.events);

  const memoryEvents = useMemo(() => {
    return events.filter((e) => e.event_type.startsWith("memory.")).slice(-10);
  }, [events]);

  const lastStatus = useMemo(() => {
    const statusEvents = memoryEvents.filter(
      (e) => e.event_type === "memory.pool.status" || e.event_type === "memory.compression.stats",
    );
    return statusEvents[statusEvents.length - 1];
  }, [memoryEvents]);

  const evictionCount = useMemo(() => {
    return memoryEvents.filter((e) => e.event_type === "memory.pool.eviction").length;
  }, [memoryEvents]);

  const poolData = lastStatus?.payload as
    | { total_agents?: number; utilization_pct?: number; compression_ratio?: number; total_memory_mb?: number }
    | undefined;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
        TurboQuant KV Cache
      </h3>

      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-md bg-cyan-50 p-2 dark:bg-cyan-900/20">
          <div className="text-lg font-bold text-cyan-600 dark:text-cyan-400">
            {poolData?.compression_ratio
              ? `${String(poolData.compression_ratio)}x`
              : "—"}
          </div>
          <div className="text-xs text-gray-500">Compression</div>
        </div>
        <div className="rounded-md bg-amber-50 p-2 dark:bg-amber-900/20">
          <div className="text-lg font-bold text-amber-600 dark:text-amber-400">
            {poolData?.total_agents ?? "—"}
          </div>
          <div className="text-xs text-gray-500">Agents</div>
        </div>
      </div>

      {poolData?.utilization_pct != null && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-xs text-gray-500">
            <span>Pool Usage</span>
            <span>{String(poolData.utilization_pct)}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-600">
            <div
              className={`h-full rounded-full transition-all ${
                (poolData.utilization_pct ?? 0) > 90
                  ? "bg-red-500"
                  : (poolData.utilization_pct ?? 0) > 70
                    ? "bg-amber-500"
                    : "bg-cyan-500"
              }`}
              style={{ width: `${Math.min(100, poolData.utilization_pct ?? 0)}%` }}
            />
          </div>
        </div>
      )}

      {evictionCount > 0 && (
        <div className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          {evictionCount} agent{evictionCount > 1 ? "s" : ""} evicted from pool
        </div>
      )}

      {memoryEvents.length === 0 && (
        <div className="mt-2 text-center">
          <p className="text-xs text-gray-400">
            4-bit KV compression enabled
          </p>
          <p className="text-xs text-gray-400">
            ~12k tokens/agent (10 active)
          </p>
        </div>
      )}
    </div>
  );
}
