/**
 * React hook that periodically refreshes Paperclip governance data.
 *
 * Initializes the PaperclipRestClient and polls the Paperclip REST API
 * on a configurable interval (default 30s).
 */
import { useEffect } from "react";
import { usePaperclipStore } from "@/store/console-stores/paperclip-store";

interface UsePaperclipPollingOptions {
  /** Paperclip server base URL (e.g. "http://192.168.23.25:3100"). Empty string disables. */
  baseUrl: string;
  /** Paperclip company UUID. Empty string disables. */
  companyId: string;
  /** Optional API key for authenticated access. */
  apiKey?: string;
  /** Polling interval in ms (default 30000). */
  intervalMs?: number;
}

export function usePaperclipPolling({
  baseUrl,
  companyId,
  apiKey,
  intervalMs = 30_000,
}: UsePaperclipPollingOptions): void {
  useEffect(() => {
    if (!baseUrl || !companyId) return;

    const store = usePaperclipStore.getState();
    store.init(baseUrl, companyId, apiKey);
    void store.refresh();

    const id = setInterval(() => {
      void usePaperclipStore.getState().refresh();
    }, intervalMs);

    return () => clearInterval(id);
  }, [baseUrl, companyId, apiKey, intervalMs]);
}
