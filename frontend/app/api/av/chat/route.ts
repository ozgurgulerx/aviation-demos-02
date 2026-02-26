import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/av/chat
 *
 * Proxies chat messages to the backend, which kicks off
 * the multi-agent solve workflow and returns a run_id + agent metadata.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const message = body?.message;

    if (!message || typeof message !== "string" || message.length < 1 || message.length > 5000) {
      return NextResponse.json(
        { error: "Invalid request body", details: "message must be a string between 1 and 5000 characters" },
        { status: 400 }
      );
    }

    const backendUrl = process.env.BACKEND_URL || "http://localhost:5001";

    // Forward to backend solve endpoint
    const response = await fetch(`${backendUrl}/api/av/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem: message, workflow_type: "handoff" }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[Chat Proxy] Backend error:", response.status, errorText);
      return NextResponse.json(
        { error: "Backend processing failed" },
        { status: response.status }
      );
    }

    const data = await response.json();

    return NextResponse.json({
      response: `Analyzing your problem with ${data.agents?.filter((a: { included: boolean }) => a.included).length || 0} specialist agents. Scenario: ${data.scenario || "auto-detected"}.`,
      run_id: data.run_id,
      scenario: data.scenario,
      agents: data.agents || [],
      message: data.message,
    });
  } catch (error) {
    console.error("[Chat Proxy] Error:", error);
    return NextResponse.json(
      { error: "Failed to process message" },
      { status: 500 }
    );
  }
}
