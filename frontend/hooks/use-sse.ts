"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useAviationStore } from "@/store/aviation-store";
import type { WorkflowEvent } from "@/types/aviation";
import { EventKinds } from "@/types/aviation";

interface UseSSEOptions {
  runId: string;
  onEvent?: (event: WorkflowEvent) => void;
  onError?: (error: Error) => void;
  enabled?: boolean;
}

const MAX_RECONNECT_ATTEMPTS = 10;

export function useSSE({ runId, onEvent, onError, enabled = true }: UseSSEOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const staleIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);
  const retriesRef = useRef(0);
  const lastSequenceRef = useRef(0);
  const [reconnecting, setReconnecting] = useState(false);

  // Use refs for callbacks and store values to avoid stale closures
  const lastEventIdRef = useRef<string | null>(null);
  const enabledRef = useRef(enabled);
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);
  enabledRef.current = enabled;
  onEventRef.current = onEvent;
  onErrorRef.current = onError;

  const { addEvent, setConnected, noteHeartbeat, evaluateStaleness } = useAviationStore();

  // Sync lastEventId into ref (avoids recreating connect on every event)
  const lastEventId = useAviationStore((s) => s.lastEventId);
  lastEventIdRef.current = lastEventId;

  const connect = useCallback(() => {
    if (!enabled || !runId || !mountedRef.current) return;

    // Build URL with resume support
    let url = `/api/av/runs/${runId}/events`;
    if (lastEventIdRef.current) {
      url += `?since=${lastEventIdRef.current}`;
    }

    console.log("[SSE] Connecting to:", url);

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    const handleSSEEvent = (e: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const event = JSON.parse(e.data) as WorkflowEvent;
        event.stream_id = event.stream_id || e.lastEventId || undefined;

        if (event.sequence && event.sequence <= lastSequenceRef.current) {
          console.warn("[SSE] Out-of-order sequence", {
            previous: lastSequenceRef.current,
            current: event.sequence,
            kind: event.kind,
          });
        } else if (event.sequence) {
          lastSequenceRef.current = event.sequence;
        }

        if (event.kind === EventKinds.HEARTBEAT) {
          noteHeartbeat(event.ts);
          return;
        }

        console.log("[SSE] Event:", event.kind, event.message);
        addEvent(event);
        onEventRef.current?.(event);

        if (event.kind === EventKinds.RUN_COMPLETED || event.kind === EventKinds.RUN_FAILED) {
          console.log("[SSE] Run complete, closing connection");
          eventSource.close();
          setConnected(false);
        }
      } catch (err) {
        console.error("[SSE] Parse error:", err);
      }
    };

    eventSource.onopen = () => {
      if (!mountedRef.current) return;
      console.log("[SSE] Connected");
      setConnected(true);
      setReconnecting(false);
      retriesRef.current = 0;
    };

    eventSource.onmessage = handleSSEEvent;
    const eventNames = Array.from(new Set(Object.values(EventKinds)));
    for (const eventName of eventNames) {
      eventSource.addEventListener(eventName, handleSSEEvent as EventListener);
    }

    eventSource.onerror = () => {
      eventSource.close();
      if (!mountedRef.current) return;
      setConnected(false);

      // Attempt reconnect with exponential backoff
      if (enabledRef.current && retriesRef.current < MAX_RECONNECT_ATTEMPTS) {
        retriesRef.current += 1;
        const delay = Math.min(1000 * 2 ** (retriesRef.current - 1), 30000);
        setReconnecting(true);
        console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${retriesRef.current}/${MAX_RECONNECT_ATTEMPTS})`);
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      } else if (retriesRef.current >= MAX_RECONNECT_ATTEMPTS) {
        console.error("[SSE] Max reconnect attempts reached");
        setReconnecting(false);
      }

      onErrorRef.current?.(new Error("SSE connection error"));
    };
  }, [runId, enabled, addEvent, setConnected, noteHeartbeat]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (staleIntervalRef.current) {
      clearInterval(staleIntervalRef.current);
      staleIntervalRef.current = null;
    }
    setConnected(false);
    setReconnecting(false);
    retriesRef.current = 0;
  }, [setConnected]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled && runId) {
      connect();
      staleIntervalRef.current = setInterval(() => {
        evaluateStaleness(Date.now());
      }, 5000);
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [enabled, runId, connect, disconnect, evaluateStaleness]);

  return {
    reconnecting,
    disconnect,
    reconnect: connect,
  };
}
