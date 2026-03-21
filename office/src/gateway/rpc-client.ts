import { uuid } from "@/lib/uuid";
import type { GatewayResponseFrame } from "./types";
import type { GatewayWsClient } from "./ws-client";

const DEFAULT_TIMEOUT_MS = 10_000;

export class RpcError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "RpcError";
  }
}

export class GatewayRpcClient {
  private pendingRequests = new Map<string, { reject: (err: RpcError) => void; cleanup: () => void }>();
  private unsubStatus: (() => void) | null = null;

  constructor(private wsClient: GatewayWsClient) {
    // Reject all pending requests when WebSocket disconnects
    this.unsubStatus = this.wsClient.onStatusChange((status) => {
      if (status === "disconnected" || status === "reconnecting") {
        this.rejectAllPending("DISCONNECTED", "WebSocket disconnected");
      }
    });
  }

  destroy(): void {
    this.rejectAllPending("DESTROYED", "RPC client destroyed");
    this.unsubStatus?.();
    this.unsubStatus = null;
  }

  request<T = unknown>(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (!this.wsClient.isConnected()) {
        reject(new RpcError("NOT_CONNECTED", "WebSocket is not connected"));
        return;
      }

      const id = uuid();
      let timer: ReturnType<typeof setTimeout> | null = null;

      const cleanup = () => {
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        this.pendingRequests.delete(id);
      };

      this.wsClient.onResponse(id, (frame: GatewayResponseFrame) => {
        cleanup();
        if (frame.ok) {
          resolve(frame.payload as T);
        } else {
          reject(new RpcError(frame.error.code, frame.error.message));
        }
      });

      this.pendingRequests.set(id, { reject, cleanup });

      timer = setTimeout(() => {
        cleanup();
        reject(new RpcError("TIMEOUT", `RPC request timed out: ${method}`));
      }, timeoutMs);

      const sent = this.wsClient.send({
        type: "req",
        id,
        method,
        params,
      });
      if (!sent) {
        cleanup();
        reject(new RpcError("SEND_FAILED", `WebSocket not open, cannot send: ${method}`));
      }
    });
  }

  private rejectAllPending(code: string, message: string): void {
    for (const [, entry] of this.pendingRequests) {
      entry.cleanup();
      entry.reject(new RpcError(code, message));
    }
    this.pendingRequests.clear();
  }
}
