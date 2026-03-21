import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AgentStream } from "@/gateway/types";
import type { DRVPEvent, DRVPEventType } from "@/drvp/drvp-types";
import { STATUS_COLORS } from "@/lib/constants";
import { useOfficeStore } from "@/store/office-store";
import { useDrvpStore } from "@/store/console-stores/drvp-store";

const STREAM_ICONS: Record<AgentStream, string> = {
  lifecycle: "●",
  tool: "🔧",
  assistant: "💬",
  error: "⚠",
};

const DRVP_ICONS: Partial<Record<DRVPEventType, string>> = {
  "request.created": "▶",
  "request.completed": "✓",
  "request.failed": "✕",
  "agent.activated": "⚡",
  "agent.thinking": "💭",
  "agent.speaking": "💬",
  "agent.idle": "○",
  "agent.error": "⚠",
  "handoff.started": "↗",
  "handoff.completed": "↘",
  "tool.call.started": "🔧",
  "tool.call.completed": "✓",
  "tool.call.failed": "✕",
  "llm.call.started": "🧠",
  "llm.call.completed": "✓",
  "llm.call.boosted": "⚡",
  "llm.stream.token": "·",
  "memory.read": "📖",
  "memory.write": "📝",
  "budget.check": "💰",
  "budget.warning": "💰",
  "budget.exhausted": "🚫",
  "browser.navigate": "🌐",
  "browser.action": "🖱",
  "browser.blocked": "🛡",
  "campaign.step.started": "▶",
  "campaign.step.completed": "✓",
  "campaign.approval.required": "⏸",
  "campaign.approved": "✅",
};

interface UnifiedEvent {
  source: "openclaw" | "drvp";
  timestamp: number;
  agentName: string;
  agentId?: string;
  icon: string;
  summary: string;
  detail?: string;
  stream?: AgentStream;
}

/** Extract a human-readable detail line from DRVP event payloads. */
function extractDrvpDetail(event: DRVPEvent): string | undefined {
  const p = event.payload;
  const type = event.event_type;

  switch (type) {
    case "handoff.started":
      return p.to_agent ? `→ ${p.to_agent}` : undefined;
    case "handoff.completed":
      return p.to_agent ? `${p.from_agent || event.agent_name} → ${p.to_agent}` : undefined;

    case "tool.call.started":
      return p.tool_name ? `${p.tool_name}` : undefined;
    case "tool.call.completed":
      return p.tool_name ? `${p.tool_name} ok` : undefined;
    case "tool.call.failed":
      return p.tool_name
        ? `${p.tool_name}: ${(p.error as string) || "failed"}`
        : undefined;

    case "llm.call.completed": {
      const model = p.model as string | undefined;
      const cost = p.cost_cents as number | undefined;
      const input = p.input_tokens as number | undefined;
      const output = p.output_tokens as number | undefined;
      const parts: string[] = [];
      if (model) parts.push(model.split("/").pop() || model);
      if (input != null || output != null)
        parts.push(`${input ?? 0}→${output ?? 0} tok`);
      if (cost != null && cost > 0) parts.push(`$${(cost / 100).toFixed(2)}`);
      return parts.length > 0 ? parts.join(" · ") : undefined;
    }

    case "llm.call.boosted": {
      const bModel = p.model as string | undefined;
      const bInput = p.input_tokens as number | undefined;
      const bOutput = p.output_tokens as number | undefined;
      const bProvider = p.provider as string | undefined;
      const parts: string[] = ["BOOST"];
      if (bModel) parts.push(bModel.split("/").pop() || bModel);
      if (bProvider) parts.push(`via ${bProvider}`);
      if (bInput != null || bOutput != null)
        parts.push(`${bInput ?? 0}→${bOutput ?? 0} tok`);
      return parts.join(" · ");
    }

    case "budget.warning": {
      const pct = p.utilization_percent as number | undefined;
      const remaining = p.remaining_cents as number | undefined;
      if (pct != null) return `${pct.toFixed(0)}% used`;
      if (remaining != null) return `$${(remaining / 100).toFixed(2)} remaining`;
      return undefined;
    }
    case "budget.exhausted":
      return `${event.agent_name} budget exhausted`;

    case "campaign.step.started": {
      const step = p.step_number as number | undefined;
      const total = p.total_steps as number | undefined;
      const title = p.step_title as string | undefined;
      if (step != null && total != null) return `${step}/${total} ${title || ""}`.trim();
      return title || undefined;
    }
    case "campaign.step.completed": {
      const step = p.step_number as number | undefined;
      const total = p.total_steps as number | undefined;
      const score = p.quality_score as number | undefined;
      const parts: string[] = [];
      if (step != null && total != null) parts.push(`${step}/${total}`);
      if (score != null) parts.push(`Q:${(score * 100).toFixed(0)}%`);
      return parts.length > 0 ? parts.join(" · ") : undefined;
    }
    case "campaign.approval.required": {
      const title = (p.campaign_title as string) || (p.title as string);
      return title ? `"${title}" needs approval` : "needs CEO approval";
    }

    case "browser.navigate": {
      const url = p.url as string | undefined;
      if (!url) return undefined;
      try {
        return new URL(url).hostname;
      } catch {
        return url;
      }
    }
    case "browser.action": {
      const action = p.action as string | undefined;
      return action || undefined;
    }
    case "browser.blocked": {
      const domain = p.domain as string | undefined;
      return domain ? `${domain} blocked by allowlist` : "domain blocked";
    }

    case "request.created": {
      const title = (p.title as string) || (p.summary as string);
      return title || undefined;
    }
    case "request.failed": {
      const error = p.error as string | undefined;
      return error || undefined;
    }

    case "memory.read":
      return p.query ? `"${p.query}"` : undefined;
    case "memory.write":
      return p.key ? `${p.key}` : undefined;

    default:
      return undefined;
  }
}

const MAX_DISPLAY = 80;

export function EventTimeline() {
  const { t } = useTranslation("panels");
  const eventHistory = useOfficeStore((s) => s.eventHistory);
  const selectAgent = useOfficeStore((s) => s.selectAgent);
  const drvpEvents = useDrvpStore((s) => s.events);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showDrvp, setShowDrvp] = useState(true);
  const prevLenRef = useRef(0);

  const merged = useMemo(() => {
    const unified: UnifiedEvent[] = [];

    // OpenClaw events
    for (const evt of eventHistory) {
      unified.push({
        source: "openclaw",
        timestamp: evt.timestamp,
        agentName: evt.agentName,
        agentId: evt.agentId,
        icon: STREAM_ICONS[evt.stream] ?? "·",
        summary: evt.summary,
        stream: evt.stream,
      });
    }

    // DRVP events
    if (showDrvp) {
      for (const evt of drvpEvents) {
        unified.push({
          source: "drvp",
          timestamp: new Date(evt.timestamp).getTime(),
          agentName: evt.agent_name,
          icon: DRVP_ICONS[evt.event_type] ?? "·",
          summary: evt.event_type.replace(/\./g, " "),
          detail: extractDrvpDetail(evt),
        });
      }
    }

    // Sort by timestamp, newest last
    unified.sort((a, b) => a.timestamp - b.timestamp);

    return unified.slice(-MAX_DISPLAY);
  }, [eventHistory, drvpEvents, showDrvp]);

  const totalLen = eventHistory.length + (showDrvp ? drvpEvents.length : 0);

  useEffect(() => {
    if (autoScroll && scrollRef.current && totalLen > prevLenRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    prevLenRef.current = totalLen;
  }, [totalLen, autoScroll]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 30;
    setAutoScroll(atBottom);
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Filter header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-1 dark:border-gray-800">
        <button
          type="button"
          onClick={() => setShowDrvp((v) => !v)}
          className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition-colors ${
            showDrvp
              ? "bg-teal-50 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400"
              : "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500"
          }`}
        >
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: showDrvp ? "#14b8a6" : "#9ca3af" }}
          />
          DRVP
        </button>
      </div>

      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        {!autoScroll && totalLen > 0 && (
          <div className="sticky top-0 z-10 flex justify-end bg-white/80 px-2 py-0.5 backdrop-blur-sm dark:bg-gray-900/80">
            <button
              onClick={() => {
                setAutoScroll(true);
                if (scrollRef.current) {
                  scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                }
              }}
              className="rounded bg-blue-600 px-1.5 py-0.5 text-[10px] text-white"
            >
              {t("eventTimeline.newEvents")}
            </button>
          </div>
        )}
        {merged.map((evt, i) => (
          <button
            key={`${evt.source}-${evt.timestamp}-${evt.agentName}-${i}`}
            onClick={() => evt.agentId && selectAgent(evt.agentId)}
            className="flex w-full items-start gap-1.5 border-b border-gray-100 px-3 py-1 text-left text-xs hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800"
          >
            {/* Source dot */}
            <span
              className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full"
              style={{
                backgroundColor: evt.source === "drvp" ? "#14b8a6" : "#3b82f6",
              }}
            />
            {/* Timestamp */}
            <span className="mt-0.5 shrink-0 text-gray-400">
              {new Date(evt.timestamp).toLocaleTimeString("en-US", {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            {/* Icon */}
            <span className="shrink-0">{evt.icon}</span>
            {/* Agent name */}
            <span
              className="shrink-0 font-medium"
              style={{
                color:
                  STATUS_COLORS[
                    evt.stream === "error" || evt.summary.includes("error") || evt.summary.includes("failed")
                      ? "error"
                      : "thinking"
                  ],
              }}
            >
              {evt.agentName}
            </span>
            {/* Summary + Detail */}
            <span className="min-w-0 flex-1 truncate text-gray-500 dark:text-gray-400">
              {evt.summary}
              {evt.detail && (
                <span className="ml-1 text-gray-400 dark:text-gray-500">
                  — {evt.detail}
                </span>
              )}
            </span>
          </button>
        ))}
        {merged.length === 0 && (
          <div className="py-3 text-center text-xs text-gray-400 dark:text-gray-500">
            {t("common:empty.noEvents")}
          </div>
        )}
      </div>
    </div>
  );
}
