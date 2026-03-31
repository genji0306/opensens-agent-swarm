/**
 * ClusterStatusPanel — displays node health, queue depth, and scheduler status.
 * Reads node-related DRVP events from the drvp-store.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Server, Activity, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";

const STATE_ICONS: Record<string, typeof CheckCircle> = {
  online: CheckCircle,
  degraded: AlertTriangle,
  offline: XCircle,
  unknown: Activity,
};

const STATE_COLORS: Record<string, string> = {
  online: "text-green-500",
  degraded: "text-amber-500",
  offline: "text-red-500",
  unknown: "text-gray-400",
};

interface NodeData {
  node_id: string;
  state: string;
  active_tasks: number;
  capabilities: string[];
}

export function ClusterStatusPanel() {
  const events = useDrvpStore((s) => s.events);

  // Extract latest node status from DRVP events
  const nodes = useMemo(() => {
    const nodeMap = new Map<string, NodeData>();

    // Default nodes
    for (const id of ["leader", "academic", "experiment"]) {
      nodeMap.set(id, { node_id: id, state: "unknown", active_tasks: 0, capabilities: [] });
    }

    // Scan events for node-related data
    for (const ev of events) {
      if (ev.event_type === "agent.activated" || ev.event_type === "agent.idle") {
        const device = ev.device;
        if (nodeMap.has(device)) {
          const node = nodeMap.get(device)!;
          node.state = "online";
          if (ev.event_type === "agent.activated") {
            node.active_tasks = Math.max(node.active_tasks, 1);
          }
        }
      }
    }

    return Array.from(nodeMap.values());
  }, [events]);

  const onlineCount = nodes.filter((n) => n.state === "online").length;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-cyan-500" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Cluster Status
          </h3>
        </div>
        <span className="text-xs text-gray-400">
          {onlineCount}/{nodes.length} online
        </span>
      </div>

      <div className="space-y-2">
        {nodes.map((node) => {
          const Icon = STATE_ICONS[node.state] || Activity;
          const color = STATE_COLORS[node.state] || "text-gray-400";

          return (
            <div
              key={node.node_id}
              className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 dark:bg-gray-700/50"
            >
              <div className="flex items-center gap-2">
                <Icon className={`h-3.5 w-3.5 ${color}`} />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300 capitalize">
                  {node.node_id}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {node.active_tasks > 0 && (
                  <span className="text-xs text-gray-500">
                    {node.active_tasks} task{node.active_tasks > 1 ? "s" : ""}
                  </span>
                )}
                <span className={`text-xs capitalize ${color}`}>
                  {node.state}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
