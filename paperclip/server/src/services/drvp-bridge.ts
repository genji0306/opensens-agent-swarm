/**
 * DRVP Bridge — subscribes to Redis `drvp:{companyId}` and relays events
 * as Paperclip LiveEvents so existing WebSocket clients receive them.
 *
 * Start conditionally via env vars:
 *   REDIS_URL=redis://localhost:6379
 *   DRVP_COMPANY_ID=<company-uuid>
 */
import { publishLiveEvent } from "./live-events.js";
import { logger } from "../middleware/logger.js";

export interface DrvpBridgeOptions {
  redisUrl: string;
  companyId: string;
}

export interface DrvpBridge {
  stop: () => void;
}

/**
 * Start the DRVP bridge that subscribes to Redis Pub/Sub and forwards
 * events to Paperclip's live event system.
 *
 * Returns a handle with a `stop()` method for graceful shutdown.
 */
export async function startDrvpBridge(opts: DrvpBridgeOptions): Promise<DrvpBridge> {
  // Dynamic import so the server doesn't fail if ioredis isn't installed
  let Redis: typeof import("ioredis").default;
  try {
    const mod = await import("ioredis");
    Redis = mod.default;
  } catch {
    logger.warn("ioredis not installed — DRVP bridge disabled");
    return { stop: () => {} };
  }

  const subscriber = new Redis(opts.redisUrl);
  const channel = `drvp:${opts.companyId}`;

  subscriber.on("error", (err) => {
    logger.error({ err, channel }, "DRVP bridge Redis error");
  });

  subscriber.subscribe(channel, (err) => {
    if (err) {
      logger.error({ err, channel }, "DRVP bridge: failed to subscribe");
      return;
    }
    logger.info({ channel }, "DRVP bridge: subscribed to Redis channel");
  });

  subscriber.on("message", (ch: string, message: string) => {
    if (ch !== channel) return;
    try {
      const event = JSON.parse(message);
      publishLiveEvent({
        companyId: opts.companyId,
        type: "drvp.event",
        payload: event,
      });
    } catch (err) {
      logger.warn({ err }, "DRVP bridge: failed to parse/relay event");
    }
  });

  const stop = () => {
    subscriber.unsubscribe(channel).catch(() => {});
    subscriber.disconnect();
    logger.info({ channel }, "DRVP bridge: stopped");
  };

  return { stop };
}
