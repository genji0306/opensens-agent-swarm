/**
 * DRVP SSE client for Agent Office.
 *
 * Connects to the Leader FastAPI SSE endpoint at
 * `GET /drvp/events/{company_id}` and emits parsed DRVP events.
 * Uses the native `EventSource` API which handles auto-reconnection.
 */
import type { DRVPEvent } from "./drvp-types";

export type DrvpEventHandler = (event: DRVPEvent) => void;

export class DrvpSseClient {
  private eventSource: EventSource | null = null;
  private handlers: Set<DrvpEventHandler> = new Set();
  private _connected = false;

  get connected(): boolean {
    return this._connected;
  }

  /**
   * Connect to the Leader DRVP SSE endpoint.
   * @param leaderUrl  Base URL of the Leader FastAPI server (e.g. "http://192.168.23.25:8100")
   * @param companyId  Paperclip company UUID
   */
  connect(leaderUrl: string, companyId: string): void {
    if (this.eventSource) {
      this.disconnect();
    }

    const url = `${leaderUrl.replace(/\/+$/, "")}/drvp/events/${companyId}`;
    const es = new EventSource(url);

    es.onopen = () => {
      this._connected = true;
    };

    es.onmessage = (msg) => {
      if (!msg.data || msg.data.trim() === "") return;
      try {
        const event = JSON.parse(msg.data) as DRVPEvent;
        for (const handler of this.handlers) {
          handler(event);
        }
      } catch {
        // Ignore malformed messages (e.g. keepalive comments are not delivered as messages)
      }
    };

    es.onerror = () => {
      this._connected = false;
      // EventSource auto-reconnects — no manual retry needed
    };

    this.eventSource = es;
  }

  /** Register a handler for incoming DRVP events. Returns unsubscribe function. */
  onEvent(handler: DrvpEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  /** Disconnect and clean up. */
  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this._connected = false;
  }
}
