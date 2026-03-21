/**
 * DRVP Issue Auto-Linker
 *
 * Subscribes to Paperclip LiveEvents of type "drvp.event" and automatically:
 *
 * 1. Creates Paperclip issues for new DRVP requests (request.created)
 * 2. Records cost events from LLM calls (llm.call.completed)
 * 3. Creates approval requests for campaigns (campaign.approval.required)
 * 4. Updates issue status on request completion/failure
 *
 * Maintains an in-memory `requestIssueMap` so subsequent events for the
 * same request_id can reference the created issue.
 */
import { eq, and } from "drizzle-orm";
import type { Db } from "@paperclipai/db";
import { agents, issues } from "@paperclipai/db";
import { subscribeCompanyLiveEvents } from "./live-events.js";
import { issueService } from "./issues.js";
import { costService } from "./costs.js";
import { approvalService } from "./approvals.js";
import { logActivity } from "./activity-log.js";
import { logger } from "../middleware/logger.js";

interface DrvpPayload {
  event_id?: string;
  event_type?: string;
  request_id?: string;
  agent_name?: string;
  issue_id?: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
}

export interface DrvpIssueLinker {
  stop: () => void;
}

export function startDrvpIssueLinker(db: Db, companyId: string): DrvpIssueLinker {
  const issueSvc = issueService(db);
  const costs = costService(db);
  const approvalSvc = approvalService(db);

  // Maps request_id → { issueId, issueIdentifier, createdAt }
  const requestIssueMap = new Map<string, { issueId: string; identifier: string; createdAt: number }>();
  // Maps agent_name → agent row (id) — cached to avoid repeated lookups
  const agentIdCache = new Map<string, string>();

  // Evict stale entries older than 24 hours every 30 minutes
  const ENTRY_TTL_MS = 24 * 60 * 60 * 1000;
  const evictionInterval = setInterval(() => {
    const now = Date.now();
    for (const [key, val] of requestIssueMap) {
      if (now - val.createdAt > ENTRY_TTL_MS) {
        requestIssueMap.delete(key);
      }
    }
  }, 30 * 60 * 1000);

  const unsubscribe = subscribeCompanyLiveEvents(companyId, (event) => {
    if (event.type !== "drvp.event") return;

    const drvp = event.payload as DrvpPayload;
    if (!drvp.event_type || !drvp.request_id) return;

    void handleDrvpEvent(drvp).catch((err) => {
      logger.warn({ err, eventType: drvp.event_type }, "DRVP issue linker: error processing event");
    });
  });

  async function resolveAgentId(agentName: string | undefined): Promise<string | undefined> {
    if (!agentName) return undefined;

    const cached = agentIdCache.get(agentName);
    if (cached) return cached;

    try {
      const agentRow = await db
        .select({ id: agents.id })
        .from(agents)
        .where(and(eq(agents.companyId, companyId), eq(agents.name, agentName)))
        .then((rows) => rows[0] ?? null);
      if (agentRow) {
        agentIdCache.set(agentName, agentRow.id);
        return agentRow.id;
      }
    } catch {
      // Non-fatal
    }
    return undefined;
  }

  async function findIssueByBillingCode(requestId: string): Promise<{ id: string; identifier: string } | null> {
    try {
      const row = await db
        .select({ id: issues.id, identifier: issues.identifier })
        .from(issues)
        .where(and(eq(issues.companyId, companyId), eq(issues.billingCode, requestId)))
        .then((rows) => rows[0] ?? null);
      return row;
    } catch {
      return null;
    }
  }

  async function handleDrvpEvent(drvp: DrvpPayload) {
    const requestId = drvp.request_id!;
    const eventType = drvp.event_type!;

    switch (eventType) {
      case "request.created":
        await handleRequestCreated(drvp, requestId);
        break;
      case "request.completed":
        await handleRequestTerminal(requestId, "done");
        break;
      case "request.failed":
        await handleRequestTerminal(requestId, "blocked");
        break;
      case "llm.call.completed":
        await handleLlmCallCompleted(drvp, requestId);
        break;
      case "llm.call.boosted":
        await handleLlmCallBoosted(drvp, requestId);
        break;
      case "campaign.approval.required":
        await handleCampaignApprovalRequired(drvp, requestId);
        break;
      default:
        break;
    }
  }

  // ─── request.created ───────────────────────────────────────────────

  async function handleRequestCreated(drvp: DrvpPayload, requestId: string) {
    // Idempotency: skip if already has an issue_id from the event
    if (drvp.issue_id) {
      requestIssueMap.set(requestId, { issueId: drvp.issue_id, identifier: drvp.issue_id, createdAt: Date.now() });
      return;
    }

    // Skip if we already created an issue for this request
    if (requestIssueMap.has(requestId)) return;

    // Check DB in case of restart
    const existing = await findIssueByBillingCode(requestId);
    if (existing) {
      requestIssueMap.set(requestId, { ...existing, createdAt: Date.now() });
      return;
    }

    const assigneeAgentId = await resolveAgentId(drvp.agent_name);

    const payload = drvp.payload ?? {};
    const title =
      (payload.title as string) ||
      (payload.summary as string) ||
      `Request from ${drvp.agent_name || "unknown agent"}`;

    try {
      const newIssue = await issueSvc.create(companyId, {
        title,
        description: payload.description as string | undefined,
        status: assigneeAgentId ? "in_progress" : "todo",
        priority: "medium",
        assigneeAgentId,
        billingCode: requestId,
      });

      requestIssueMap.set(requestId, { issueId: newIssue.id, identifier: newIssue.identifier, createdAt: Date.now() });

      await logActivity(db, {
        companyId,
        actorType: "system",
        actorId: "drvp-auto-linker",
        action: "created",
        entityType: "issue",
        entityId: newIssue.id,
        details: {
          drvpEventId: drvp.event_id,
          drvpRequestId: requestId,
          agentName: drvp.agent_name,
        },
      });

      logger.info(
        { identifier: newIssue.identifier, requestId, agent: drvp.agent_name },
        "DRVP auto-linker: created issue",
      );
    } catch (err) {
      logger.warn(
        { err, requestId, agent: drvp.agent_name },
        "DRVP auto-linker: failed to create issue",
      );
    }
  }

  // ─── request.completed / request.failed ────────────────────────────

  async function handleRequestTerminal(requestId: string, targetStatus: "done" | "blocked") {
    const mapped = requestIssueMap.get(requestId);
    const dbIssue = !mapped ? await findIssueByBillingCode(requestId) : null;
    const issueId = mapped?.issueId ?? dbIssue?.id;
    requestIssueMap.delete(requestId);

    if (!issueId) return;

    try {
      await issueSvc.update(issueId, { status: targetStatus });

      await logActivity(db, {
        companyId,
        actorType: "system",
        actorId: "drvp-auto-linker",
        action: "updated",
        entityType: "issue",
        entityId: issueId,
        details: {
          drvpRequestId: requestId,
          newStatus: targetStatus,
        },
      });

      logger.info(
        { issueId, requestId, status: targetStatus },
        `DRVP auto-linker: marked issue ${targetStatus}`,
      );
    } catch (err) {
      logger.warn(
        { err, requestId, status: targetStatus },
        "DRVP auto-linker: failed to update issue status",
      );
    }
  }

  // ─── llm.call.completed ────────────────────────────────────────────

  async function handleLlmCallCompleted(drvp: DrvpPayload, requestId: string) {
    const payload = drvp.payload ?? {};

    const provider = (payload.provider as string) || "unknown";
    const model = (payload.model as string) || "unknown";
    const inputTokens = typeof payload.input_tokens === "number" ? payload.input_tokens : 0;
    const outputTokens = typeof payload.output_tokens === "number" ? payload.output_tokens : 0;
    const costCents = typeof payload.cost_cents === "number" ? payload.cost_cents : 0;

    // Skip zero-cost events
    if (costCents === 0 && inputTokens === 0 && outputTokens === 0) return;

    const agentId = await resolveAgentId(drvp.agent_name);
    if (!agentId) {
      logger.warn(
        { agent: drvp.agent_name, requestId },
        "DRVP auto-linker: skipping cost event — agent not found",
      );
      return;
    }

    // Resolve issue ID for cross-linking
    const mapped = requestIssueMap.get(requestId);
    const dbIssue = !mapped ? await findIssueByBillingCode(requestId) : null;
    const issueId = mapped?.issueId ?? dbIssue?.id;

    try {
      await costs.createEvent(companyId, {
        agentId,
        issueId: issueId || null,
        billingCode: requestId,
        provider,
        model,
        inputTokens,
        outputTokens,
        costCents,
        occurredAt: drvp.timestamp ? new Date(drvp.timestamp) : new Date(),
      });

      logger.debug(
        { agent: drvp.agent_name, requestId, costCents, model },
        "DRVP auto-linker: recorded cost event",
      );
    } catch (err) {
      logger.warn(
        { err, agent: drvp.agent_name, requestId },
        "DRVP auto-linker: failed to record cost event",
      );
    }
  }

  // ─── llm.call.boosted (AIClient — zero-cost, record as activity) ──

  async function handleLlmCallBoosted(drvp: DrvpPayload, requestId: string) {
    const payload = drvp.payload ?? {};

    const provider = (payload.provider as string) || "aiclient";
    const model = (payload.model as string) || "unknown";
    const inputTokens = typeof payload.input_tokens === "number" ? payload.input_tokens : 0;
    const outputTokens = typeof payload.output_tokens === "number" ? payload.output_tokens : 0;

    const agentId = await resolveAgentId(drvp.agent_name);
    if (!agentId) return;

    // Record as a zero-cost event for tracking token usage without billing
    const mapped = requestIssueMap.get(requestId);
    const dbIssue = !mapped ? await findIssueByBillingCode(requestId) : null;
    const issueId = mapped?.issueId ?? dbIssue?.id;

    try {
      await costs.createEvent(companyId, {
        agentId,
        issueId: issueId || null,
        billingCode: requestId,
        provider,
        model,
        inputTokens,
        outputTokens,
        costCents: 0, // Boosted calls are free
        occurredAt: drvp.timestamp ? new Date(drvp.timestamp) : new Date(),
      });

      await logActivity(db, {
        companyId,
        actorType: "system",
        actorId: "drvp-auto-linker",
        action: "llm.call.boosted",
        entityType: "cost_event",
        entityId: drvp.event_id || requestId,
        details: {
          drvpRequestId: requestId,
          agentName: drvp.agent_name,
          provider,
          model,
          inputTokens,
          outputTokens,
        },
      });

      logger.debug(
        { agent: drvp.agent_name, requestId, model, provider },
        "DRVP auto-linker: recorded boosted call (zero cost)",
      );
    } catch (err) {
      logger.warn(
        { err, agent: drvp.agent_name, requestId },
        "DRVP auto-linker: failed to record boosted call",
      );
    }
  }

  // ─── campaign.approval.required ────────────────────────────────────

  async function handleCampaignApprovalRequired(drvp: DrvpPayload, requestId: string) {
    const payload = drvp.payload ?? {};
    const agentId = await resolveAgentId(drvp.agent_name);

    const campaignTitle = (payload.campaign_title as string) || (payload.title as string) || "Campaign approval";
    const steps = payload.steps as unknown[] | undefined;
    const estimatedCost = payload.estimated_cost as number | undefined;

    try {
      const approval = await approvalSvc.create(companyId, {
        type: "approve_ceo_strategy",
        requestedByAgentId: agentId || null,
        status: "pending",
        payload: {
          campaignTitle,
          requestId,
          agentName: drvp.agent_name,
          steps: steps ?? [],
          estimatedCost: estimatedCost ?? null,
          description: (payload.description as string) || null,
        },
      });

      await logActivity(db, {
        companyId,
        actorType: "system",
        actorId: "drvp-auto-linker",
        action: "created",
        entityType: "approval",
        entityId: approval.id,
        details: {
          drvpEventId: drvp.event_id,
          drvpRequestId: requestId,
          agentName: drvp.agent_name,
          campaignTitle,
        },
      });

      logger.info(
        { approvalId: approval.id, requestId, agent: drvp.agent_name, campaignTitle },
        "DRVP auto-linker: created campaign approval request",
      );
    } catch (err) {
      logger.warn(
        { err, requestId, agent: drvp.agent_name },
        "DRVP auto-linker: failed to create approval request",
      );
    }
  }

  logger.info({ companyId }, "DRVP issue auto-linker started");

  return {
    stop: () => {
      unsubscribe();
      clearInterval(evictionInterval);
      requestIssueMap.clear();
      agentIdCache.clear();
      logger.info("DRVP issue auto-linker stopped");
    },
  };
}
