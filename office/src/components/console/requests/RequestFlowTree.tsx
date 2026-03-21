/**
 * Vertical CSS tree showing related Paperclip issues for a request.
 *
 * Nodes display identifier, agent name, status dot, duration, and cost.
 * In-progress nodes pulse using the existing `agent-pulse` keyframe.
 */
import type { PaperclipIssue } from "@/paperclip/paperclip-types";

const STATUS_COLORS: Record<string, string> = {
  in_progress: "#3b82f6",
  blocked: "#ef4444",
  in_review: "#f97316",
  todo: "#6b7280",
  backlog: "#9ca3af",
  done: "#22c55e",
  cancelled: "#9ca3af",
};

interface RequestFlowTreeProps {
  issues: PaperclipIssue[];
  paperclipUrl?: string;
}

export function RequestFlowTree({ issues, paperclipUrl }: RequestFlowTreeProps) {
  if (issues.length === 0) {
    return (
      <p className="py-2 text-center text-xs text-gray-400 dark:text-gray-500">
        No linked issues
      </p>
    );
  }

  // Build a tree: top-level issues (no parentId or parent not in set) → children
  const issueSet = new Set(issues.map((i) => i.id));
  const roots = issues.filter((i) => !i.parentId || !issueSet.has(i.parentId));
  const childrenOf = (parentId: string) => issues.filter((i) => i.parentId === parentId);

  return (
    <div className="flex flex-col gap-0.5 py-1">
      {roots.map((issue) => (
        <TreeNode
          key={issue.id}
          issue={issue}
          childrenOf={childrenOf}
          paperclipUrl={paperclipUrl}
          depth={0}
        />
      ))}
    </div>
  );
}

function TreeNode({
  issue,
  childrenOf,
  paperclipUrl,
  depth,
}: {
  issue: PaperclipIssue;
  childrenOf: (parentId: string) => PaperclipIssue[];
  paperclipUrl?: string;
  depth: number;
}) {
  const children = childrenOf(issue.id);
  const color = STATUS_COLORS[issue.status] ?? "#6b7280";
  const isActive = issue.status === "in_progress";
  const elapsed = formatElapsed(issue.createdAt);

  return (
    <div style={{ paddingLeft: depth * 16 }}>
      <a
        href={paperclipUrl ? `${paperclipUrl}/issues/${issue.id}` : undefined}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 rounded px-2 py-1 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
      >
        {/* Connector line */}
        {depth > 0 && (
          <span className="mr-1 inline-block h-3 w-px bg-gray-300 dark:bg-gray-600" />
        )}
        {/* Status dot */}
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{
            backgroundColor: color,
            animation: isActive ? "agent-pulse 1.5s ease-in-out infinite" : undefined,
          }}
        />
        {/* Identifier */}
        <span className="shrink-0 rounded bg-blue-100 px-1 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
          {issue.identifier}
        </span>
        {/* Title */}
        <span className="min-w-0 flex-1 truncate text-xs text-gray-600 dark:text-gray-300">
          {issue.title}
        </span>
        {/* Elapsed */}
        <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500">
          {elapsed}
        </span>
      </a>
      {children.map((child) => (
        <TreeNode
          key={child.id}
          issue={child}
          childrenOf={childrenOf}
          paperclipUrl={paperclipUrl}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

function formatElapsed(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "<1m";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
