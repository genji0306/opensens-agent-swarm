/**
 * RequestsPage — shows active DRVP request DAGs with Paperclip issue trees.
 */
import { RefreshCw, GitBranch, Activity, CheckCircle2, Layers, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatCard } from "@/components/console/dashboard/StatCard";
import { RequestCard } from "@/components/console/requests/RequestCard";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import { usePaperclipStore } from "@/store/console-stores/paperclip-store";

export function RequestsPage() {
  const { t } = useTranslation("layout");
  const events = useDrvpStore((s) => s.events);
  const activeRequests = useDrvpStore((s) => s.activeRequests);
  const activeIssues = usePaperclipStore((s) => s.activeIssues);
  const paperclipUrl = import.meta.env.VITE_PAPERCLIP_URL || "";

  const requestList = Array.from(activeRequests.values());

  // Stats
  const completedToday = events.filter((e) => {
    if (e.event_type !== "request.completed") return false;
    const today = new Date();
    const eventDate = new Date(e.timestamp);
    return (
      eventDate.getFullYear() === today.getFullYear() &&
      eventDate.getMonth() === today.getMonth() &&
      eventDate.getDate() === today.getDate()
    );
  }).length;

  const campaignCount = requestList.filter((r) => r.campaign).length;
  const awaitingApproval = requestList.filter(
    (r) => r.lastEventType === "campaign.approval.required",
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {t("consoleNav.requests")}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Active DRVP request pipelines and linked governance issues
          </p>
        </div>
        <button
          type="button"
          onClick={() => usePaperclipStore.getState().refresh()}
          className="flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatCard
          icon={GitBranch}
          title="Active Requests"
          value={String(requestList.length)}
          color="text-blue-500"
        />
        <StatCard
          icon={CheckCircle2}
          title="Completed Today"
          value={String(completedToday)}
          color="text-green-500"
        />
        <StatCard
          icon={Activity}
          title="Total Events"
          value={String(events.length)}
          color="text-purple-500"
        />
        <StatCard
          icon={Layers}
          title="Campaigns"
          value={String(campaignCount)}
          color="text-indigo-500"
        />
        <StatCard
          icon={ShieldAlert}
          title="Awaiting Approval"
          value={String(awaitingApproval)}
          color={awaitingApproval > 0 ? "text-amber-500" : "text-gray-400"}
        />
      </div>

      {/* Request list */}
      {requestList.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 py-12 dark:border-gray-700">
          <GitBranch className="mb-3 h-8 w-8 text-gray-300 dark:text-gray-600" />
          <p className="text-sm text-gray-400 dark:text-gray-500">
            No active requests — events will appear here when agents start processing
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {requestList.map((req) => {
            // Find issues related to this request's agent or issue
            const related = activeIssues.filter(
              (issue) =>
                issue.id === req.issueId ||
                issue.parentId === req.issueId,
            );
            return (
              <RequestCard
                key={req.requestId}
                request={req}
                relatedIssues={related}
                paperclipUrl={paperclipUrl}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
