/**
 * Compact list of active Paperclip issues for the sidebar.
 * Shows status, identifier, title, priority badge, assignee, and time ago.
 */
import { useTranslation } from "react-i18next";
import type { PaperclipIssue } from "@/paperclip/paperclip-types";
import { usePaperclipStore } from "@/store/console-stores/paperclip-store";

const STATUS_COLORS: Record<string, string> = {
  in_progress: "#3b82f6",
  blocked: "#ef4444",
  in_review: "#f97316",
  todo: "#6b7280",
  backlog: "#9ca3af",
  done: "#22c55e",
  cancelled: "#9ca3af",
};

const PRIORITY_CONFIG: Record<string, { label: string; className: string }> = {
  critical: { label: "P0", className: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
  high: { label: "P1", className: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300" },
  medium: { label: "P2", className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300" },
  low: { label: "P3", className: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400" },
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "<1m";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

interface ActiveIssuesListProps {
  issues: PaperclipIssue[];
  paperclipUrl?: string;
}

export function ActiveIssuesList({ issues, paperclipUrl }: ActiveIssuesListProps) {
  const { t } = useTranslation("panels");
  const agents = usePaperclipStore((s) => s.agents);

  // Build a quick lookup: agentId → name
  const agentNames = new Map(agents.map((a) => [a.id, a.name]));

  if (issues.length === 0) {
    return (
      <p className="px-2 py-3 text-center text-xs text-gray-400 dark:text-gray-500">
        {t("paperclip.noActiveIssues")}
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      {issues.map((issue) => {
        const priority = PRIORITY_CONFIG[issue.priority];
        const assigneeName = issue.assigneeAgentId
          ? agentNames.get(issue.assigneeAgentId)
          : undefined;

        return (
          <a
            key={issue.id}
            href={paperclipUrl ? `${paperclipUrl}/issues/${issue.id}` : undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 border-b border-gray-50 px-2 py-1.5 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800"
          >
            {/* Status dot */}
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[issue.status] ?? "#6b7280" }}
            />
            {/* Identifier badge */}
            <span className="shrink-0 rounded bg-blue-100 px-1 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
              {issue.identifier}
            </span>
            {/* Priority badge */}
            {priority && issue.priority !== "medium" && (
              <span className={`shrink-0 rounded px-1 text-[10px] font-semibold ${priority.className}`}>
                {priority.label}
              </span>
            )}
            {/* Title */}
            <span className="min-w-0 flex-1 truncate text-xs text-gray-600 dark:text-gray-300">
              {issue.title}
            </span>
            {/* Assignee (short) */}
            {assigneeName && (
              <span
                className="shrink-0 max-w-[60px] truncate text-[10px] text-gray-400 dark:text-gray-500"
                title={assigneeName}
              >
                {assigneeName.split(" ").pop()}
              </span>
            )}
            {/* Time ago */}
            <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500">
              {timeAgo(issue.createdAt)}
            </span>
          </a>
        );
      })}
    </div>
  );
}
