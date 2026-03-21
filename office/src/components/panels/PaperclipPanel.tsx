/**
 * PaperclipPanel — governance overview for the Agent Office sidebar.
 *
 * Shows budget gauges, active issues, campaign progress, and a summary of Paperclip state.
 */
import { useTranslation } from "react-i18next";
import { usePaperclipStore } from "@/store/console-stores/paperclip-store";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import { isBoostEnabled } from "@/paperclip/paperclip-types";
import { BudgetGauge } from "./BudgetGauge";
import { ActiveIssuesList } from "./ActiveIssuesList";

export function PaperclipPanel() {
  const { t } = useTranslation("panels");
  const dashboard = usePaperclipStore((s) => s.dashboard);
  const agents = usePaperclipStore((s) => s.agents);
  const activeIssues = usePaperclipStore((s) => s.activeIssues);
  const isLoading = usePaperclipStore((s) => s.isLoading);
  const error = usePaperclipStore((s) => s.error);

  // Campaign progress from DRVP store
  const activeRequests = useDrvpStore((s) => s.activeRequests);
  const campaignCount = Array.from(activeRequests.values()).filter((r) => r.campaign).length;
  const approvalBlocked = Array.from(activeRequests.values()).filter(
    (r) => r.lastEventType === "campaign.approval.required",
  ).length;

  const paperclipUrl = import.meta.env.VITE_PAPERCLIP_URL || "";

  if (isLoading && !dashboard) {
    return (
      <div className="flex flex-col gap-2 px-3 py-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-4 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        ))}
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <p className="px-3 py-3 text-xs text-red-500 dark:text-red-400">{error}</p>
    );
  }

  if (!dashboard) {
    return (
      <p className="px-3 py-3 text-center text-xs text-gray-400 dark:text-gray-500">
        {t("paperclip.noData")}
      </p>
    );
  }

  const agentsWithBudget = agents.filter((a) => a.monthlyBudgetCents > 0);

  return (
    <div className="flex flex-col gap-2 px-2 py-2">
      {/* Summary stat pills */}
      <div className="flex gap-1.5">
        <StatPill
          label={t("paperclip.spend")}
          value={`$${(dashboard.costs.totalCents / 100).toFixed(2)}`}
        />
        <StatPill
          label={t("paperclip.approvals")}
          value={String(dashboard.pendingApprovals)}
          highlight={dashboard.pendingApprovals > 0}
        />
        <StatPill
          label={t("paperclip.openIssues")}
          value={String(dashboard.issues.open + dashboard.issues.inProgress)}
        />
      </div>

      {/* Campaign, approval, and boost alerts */}
      {(() => {
        const boostedAgents = agents.filter(isBoostEnabled);
        const showAlerts = campaignCount > 0 || approvalBlocked > 0 || boostedAgents.length > 0;
        if (!showAlerts) return null;
        return (
          <div className="flex flex-wrap gap-1.5">
            {campaignCount > 0 && (
              <div className="flex items-center gap-1.5 rounded-md bg-purple-50 px-2 py-1 dark:bg-purple-900/20">
                <span className="text-[10px] text-purple-600 dark:text-purple-400">
                  {campaignCount} campaign{campaignCount !== 1 ? "s" : ""} running
                </span>
              </div>
            )}
            {approvalBlocked > 0 && (
              <div className="flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-1 dark:bg-amber-900/20">
                <span className="text-[10px] font-medium text-amber-600 dark:text-amber-400">
                  {approvalBlocked} awaiting approval
                </span>
              </div>
            )}
            {boostedAgents.length > 0 && (
              <div className="flex items-center gap-1.5 rounded-md bg-cyan-50 px-2 py-1 dark:bg-cyan-900/20">
                <span className="text-[10px] text-cyan-600 dark:text-cyan-400">
                  {boostedAgents.map((a) => a.name.split(" ").pop()).join(", ")} boosted
                </span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Budget gauges */}
      {agentsWithBudget.length > 0 && (
        <div>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            {t("paperclip.budgetGauges")}
          </h4>
          <div className="flex flex-wrap gap-2">
            {agentsWithBudget.map((agent) => (
              <BudgetGauge
                key={agent.id}
                agentName={agent.name}
                spentCents={agent.spentThisMonthCents}
                budgetCents={agent.monthlyBudgetCents}
              />
            ))}
          </div>
        </div>
      )}

      {/* Active issues */}
      <div>
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
          {t("paperclip.activeIssues")}
        </h4>
        <ActiveIssuesList issues={activeIssues} paperclipUrl={paperclipUrl} />
      </div>
    </div>
  );
}

function StatPill({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex flex-1 flex-col items-center rounded-md px-1.5 py-1 ${
        highlight
          ? "bg-amber-50 dark:bg-amber-900/30"
          : "bg-gray-50 dark:bg-gray-800"
      }`}
    >
      <span
        className={`text-sm font-bold ${
          highlight ? "text-amber-600 dark:text-amber-400" : "text-gray-700 dark:text-gray-200"
        }`}
      >
        {value}
      </span>
      <span className="text-[9px] text-gray-400 dark:text-gray-500">{label}</span>
    </div>
  );
}
