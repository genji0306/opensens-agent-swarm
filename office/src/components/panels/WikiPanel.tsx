/**
 * WikiPanel — OAS knowledge wiki status card (Phase 25).
 *
 * Shows:
 * - Ingestion rate (pages/claims added in last hour)
 * - Last /wiki-compile run summary
 * - Conflict detection badge (auto-resolved vs pending)
 * - Lint issue count + clean/dirty indicator
 *
 * Consumes DRVP events:
 *   knowledge.ingested, knowledge.page.compiled,
 *   knowledge.conflict.detected, knowledge.conflict.auto_resolved,
 *   wiki.sync.completed, wiki.lint.completed
 */
import { useMemo } from "react";
import { BookOpen, AlertTriangle, CheckCircle2, FileText, GitMerge } from "lucide-react";
import { useDrvpStore } from "@/store/console-stores/drvp-store";
import type { DRVPEvent } from "@/drvp/drvp-types";

interface WikiState {
  entityCount: number;
  claimCount: number;
  pageCount: number;
  ingestedThisSession: number;
  conflictsDetected: number;
  conflictsResolved: number;
  lintIssues: number;
  lintClean: boolean | null;
  lastCompile: string;
  lastIngest: string;
}

function extractWikiState(events: readonly DRVPEvent[]): WikiState {
  let entityCount = 0;
  let claimCount = 0;
  let pageCount = 0;
  let ingestedThisSession = 0;
  let conflictsDetected = 0;
  let conflictsResolved = 0;
  let lintIssues = 0;
  let lintClean: boolean | null = null;
  let lastCompile = "";
  let lastIngest = "";

  for (const ev of events) {
    switch (ev.event_type) {
      case "knowledge.ingested": {
        ingestedThisSession += 1;
        lastIngest = ev.timestamp;
        break;
      }
      case "knowledge.page.compiled": {
        pageCount = (ev.payload.page_count as number) ?? pageCount;
        break;
      }
      case "knowledge.conflict.detected": {
        conflictsDetected += 1;
        break;
      }
      case "knowledge.conflict.auto_resolved": {
        conflictsResolved += 1;
        break;
      }
      case "wiki.sync.completed": {
        entityCount = (ev.payload.entity_count as number) ?? entityCount;
        claimCount = (ev.payload.claim_count as number) ?? claimCount;
        lastCompile = ev.timestamp;
        break;
      }
      case "wiki.lint.completed": {
        lintIssues = (ev.payload.issue_count as number) ?? 0;
        lintClean = lintIssues === 0;
        break;
      }
    }
  }

  return {
    entityCount,
    claimCount,
    pageCount,
    ingestedThisSession,
    conflictsDetected,
    conflictsResolved,
    lintIssues,
    lintClean,
    lastCompile,
    lastIngest,
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

export function WikiPanel() {
  const events = useDrvpStore((s) => s.events);
  const state = useMemo(() => extractWikiState(events), [events]);

  const pendingConflicts = state.conflictsDetected - state.conflictsResolved;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
        <BookOpen className="h-4 w-4" />
        Knowledge Wiki
        {state.lintClean !== null && (
          <span
            className={`ml-auto rounded px-1.5 py-0.5 text-xs ${
              state.lintClean
                ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
            }`}
          >
            {state.lintClean ? "Clean" : `${state.lintIssues} issue${state.lintIssues !== 1 ? "s" : ""}`}
          </span>
        )}
      </div>

      {/* Stat grid */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
          <div className="text-[10px] uppercase text-zinc-500">Pages</div>
          <div className="text-lg font-semibold text-zinc-700 dark:text-zinc-200">
            {state.pageCount}
          </div>
        </div>
        <div className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
          <div className="text-[10px] uppercase text-zinc-500">Entities</div>
          <div className="text-lg font-semibold text-zinc-700 dark:text-zinc-200">
            {state.entityCount}
          </div>
        </div>
        <div className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
          <div className="text-[10px] uppercase text-zinc-500">Claims</div>
          <div className="text-lg font-semibold text-zinc-700 dark:text-zinc-200">
            {state.claimCount}
          </div>
        </div>
      </div>

      {/* Ingestion rate */}
      <div className="mb-2 flex items-center gap-1.5 text-xs text-zinc-500">
        <FileText className="h-3 w-3" />
        {state.ingestedThisSession > 0 ? (
          <>
            {state.ingestedThisSession} ingested this session
            {state.lastIngest && (
              <span className="ml-auto text-[10px] text-zinc-400">
                {formatTimestamp(state.lastIngest)}
              </span>
            )}
          </>
        ) : (
          <span className="text-zinc-400">No ingestions yet this session</span>
        )}
      </div>

      {/* Conflicts */}
      {state.conflictsDetected > 0 && (
        <div className="mb-2 flex items-center gap-1.5 text-xs">
          <GitMerge className="h-3 w-3 text-amber-400" />
          <span className="text-zinc-600 dark:text-zinc-300">
            {state.conflictsResolved}/{state.conflictsDetected} conflicts resolved
          </span>
          {pendingConflicts > 0 && (
            <span className="ml-auto rounded bg-amber-100 px-1.5 text-[10px] text-amber-700 dark:bg-amber-900 dark:text-amber-300">
              {pendingConflicts} pending
            </span>
          )}
        </div>
      )}

      {/* Last compile */}
      <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
        {state.lintClean === true ? (
          <CheckCircle2 className="h-3 w-3 text-green-500" />
        ) : (
          <AlertTriangle className="h-3 w-3 text-zinc-400" />
        )}
        Last compile: {state.lastCompile ? formatTimestamp(state.lastCompile) : "never"}
      </div>
    </div>
  );
}
