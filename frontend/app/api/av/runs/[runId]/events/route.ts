import { NextRequest } from "next/server";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * SSE Proxy endpoint - forwards events from backend to frontend
 *
 * The frontend connects to this endpoint, which proxies SSE events
 * from the backend orchestrator running in AKS.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;

  // Validate runId is a UUID to prevent path traversal
  if (!UUID_RE.test(runId)) {
    return new Response(
      JSON.stringify({ error: "Invalid run ID format" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const backendUrl = process.env.BACKEND_URL || "http://localhost:5002";
  const query = request.nextUrl.search || "";
  const sseUrl = `${backendUrl}/api/av/runs/${runId}/events${query}`;

  console.log(`[SSE Proxy] Connecting to backend for run ${runId}`);

  try {
    // Use request.signal to detect client disconnect and abort the backend fetch
    const backendResponse = await fetch(sseUrl, {
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
        ...(request.headers.get("last-event-id")
          ? { "Last-Event-ID": request.headers.get("last-event-id") as string }
          : {}),
      },
      cache: "no-store",
      signal: request.signal,
    });

    if (!backendResponse.ok) {
      console.error(`[SSE Proxy] Backend error: ${backendResponse.status}`);
      return new Response(
        JSON.stringify({ error: "Backend connection failed", status: backendResponse.status }),
        { status: backendResponse.status, headers: { "Content-Type": "application/json" } }
      );
    }

    if (!backendResponse.body) {
      console.error("[SSE Proxy] No response body from backend");
      return new Response(
        JSON.stringify({ error: "No response body" }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    // Create a TransformStream to forward SSE events
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const reader = backendResponse.body.getReader();
    const decoder = new TextDecoder();

    // Abort backend stream when client disconnects
    const onAbort = () => {
      reader.cancel().catch(() => {});
      writer.close().catch(() => {});
    };
    request.signal.addEventListener("abort", onAbort);

    // Forward events from backend to client
    (async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log(`[SSE Proxy] Backend stream ended for run ${runId}`);
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          await writer.write(new TextEncoder().encode(chunk));
        }
      } catch (error) {
        if (request.signal.aborted) {
          console.log(`[SSE Proxy] Client disconnected for run ${runId}`);
        } else {
          console.error("[SSE Proxy] Stream error:", error);
        }
      } finally {
        request.signal.removeEventListener("abort", onAbort);
        try {
          await writer.close();
        } catch {
          // Writer might already be closed
        }
      }
    })();

    return new Response(readable, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }

    console.error("[SSE Proxy] Connection error:", error);

    return new Response(
      JSON.stringify({
        error: "Backend connection failed",
        message: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
