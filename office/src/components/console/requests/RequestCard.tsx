/**
 * Expandable card for an active DRVP request.
 *
 * Collapsed: agent name, request ID, last event type, campaign progress, elapsed, issue badge.
 * Expanded: RequestFlowTree showing related Paperclip issues.
 */
import { useState, useEffect } from "react";
import { ChevronDown, ChevronRight, Layers, ShieldAlert } from "lucide-react";
import type { ActiveRequest } from "@/store/console-stores/drvp-store";
import type { PaperclipIssue } from "@/paperclip/paperclip-types";
import { RequestFlowTree } from "./RequestFlowTree";

interface RequestCardProps {
  request: ActiveRequest;
  relatedIssues: PaperclipIssue[];
  paperclipUrl?: string;
}

export function RequestCard({ request, relatedIssues, paperclipUrl }: RequestCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [elapsed, setElapsed] = useState(() => formatElapsed(request.startedAt));

  // Update elapsed time every 5s
  useEffect(() => {
    const id = setInterval(() => setElapsed(formatElapsed(request.startedAt)), 5_000);
    return () => clearInterval(id);
  }, [request.startedAt]);

  const campaign = request.campaign;
  const isApprovalBlocked = request.lastEventType === "campaign.approval.required";

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
        )}

        {/* Agent name */}
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
          {request.agentName}
        </span>

        {/* Request ID (truncated) */}
        <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {request.requestId.slice(0, 12)}
        </span>

        {/* Last event type */}
        <span className="min-w-0 flex-1 truncate text-xs text-gray-500 dark:text-gray-400">
          {request.lastEventType}
        </span>

        {/* Approval blocked badge */}
        {isApprovalBlocked && (
          <span className="flex shrink-0 items-center gap-0.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            <ShieldAlert className="h-3 w-3" />
            Approval
          </span>
        )}

        {/* Issue badge */}
        {request.issueId && (
          <span className="shrink-0 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
            {request.issueId}
          </span>
        )}

        {/* Elapsed */}
        <span className="shrink-0 text-xs text-gray-400 dark:text-gray-500">
          {elapsed}
        </span>
      </button>

      {/* Campaign progress bar */}
      {campaign && (
        <div className="border-t border-gray-100 px-4 py-2 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 shrink-0 text-purple-500" />
            <span className="text-[10px] font-medium text-gray-500 dark:text-gray-400">
              Step {campaign.currentStep}/{campaign.totalSteps}
            </span>
            <span className="min-w-0 flex-1 truncate text-[10px] text-gray-400 dark:text-gray-500">
              {campaign.stepTitle}
            </span>
            {campaign.qualityScore != null && (
              <span
                className={`shrink-0 rounded px-1 text-[10px] font-semibold ${
                  campaign.qualityScore >= 0.8
                    ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
                    : campaign.qualityScore >= 0.5
                      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300"
                      : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                }`}
              >
                Q:{(campaign.qualityScore * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {/* Progress bar */}
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
            <div
              className="h-full rounded-full bg-purple-500 transition-all duration-500"
              style={{ width: `${Math.min((campaign.currentStep / (campaign.totalSteps || 1)) * 100, 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-2 dark:border-gray-800">
          <RequestFlowTree issues={relatedIssues} paperclipUrl={paperclipUrl} />
        </div>
      )}
    </div>
  );
}

function formatElapsed(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h`;
}
