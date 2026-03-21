/**
 * React hook that manages the DRVP SSE connection lifecycle.
 *
 * Creates a DrvpSseClient, connects to the Leader SSE endpoint,
 * and dispatches each incoming event via dispatchDrvpEvent.
 */
import { useEffect, useRef } from "react";
import { DrvpSseClient } from "@/drvp/drvp-client";
import { dispatchDrvpEvent } from "@/drvp/drvp-consumer";

interface UseDrvpConnectionOptions {
  /** Leader FastAPI base URL (e.g. "http://192.168.23.25:8100"). Empty string disables. */
  leaderUrl: string;
  /** Paperclip company UUID. Empty string disables. */
  companyId: string;
}

export function useDrvpConnection({ leaderUrl, companyId }: UseDrvpConnectionOptions): void {
  const clientRef = useRef<DrvpSseClient | null>(null);

  useEffect(() => {
    if (!leaderUrl || !companyId) {
      return;
    }

    const client = new DrvpSseClient();
    clientRef.current = client;

    const unsub = client.onEvent(dispatchDrvpEvent);
    client.connect(leaderUrl, companyId);

    return () => {
      unsub();
      client.disconnect();
      clientRef.current = null;
    };
  }, [leaderUrl, companyId]);
}
