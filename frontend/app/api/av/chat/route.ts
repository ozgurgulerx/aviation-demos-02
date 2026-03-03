import { NextRequest, NextResponse } from "next/server";

interface AgentPayload {
  id: string;
  name: string;
  included: boolean;
  category?: string;
  description?: string;
  outputs?: string[];
  dataSources?: string[];
}

const SCENARIO_LABELS: Record<string, string> = {
  hub_disruption: "Hub Disruption Recovery",
  predictive_maintenance: "Predictive Maintenance Analysis",
  diversion: "Diversion Management",
  crew_fatigue: "Crew Fatigue Assessment",
};

function buildWorkflowSummary(scenario: string, agents: AgentPayload[]): string {
  const included = agents.filter((a) => a.included);
  const specialists = included.filter((a) => a.category !== "coordinator");
  const coordinator = included.find((a) => a.category === "coordinator");
  const scenarioLabel = SCENARIO_LABELS[scenario] || scenario.replace(/_/g, " ");

  const lines: string[] = [];

  lines.push(`Scenario: ${scenarioLabel}`);
  lines.push(
    `Recruiting ${included.length} agents (${specialists.length} specialist${specialists.length !== 1 ? "s" : ""} + ${coordinator ? "1 coordinator" : "0 coordinators"}).`
  );
  lines.push("");

  // Specialist details
  lines.push("Specialist agents:");
  for (const agent of specialists) {
    const sources = agent.dataSources?.length ? ` [${agent.dataSources.join(", ")}]` : "";
    lines.push(`  ${agent.name}${sources}`);
    if (agent.description) {
      lines.push(`    ${agent.description}`);
    }
    if (agent.outputs?.length) {
      lines.push(`    \u2192 ${agent.outputs.join("; ")}`);
    }
  }

  // Coordinator
  if (coordinator) {
    lines.push("");
    lines.push(`Coordinator: ${coordinator.name}`);
    if (coordinator.description) {
      lines.push(`  ${coordinator.description}`);
    }
  }

  // Execution plan
  lines.push("");
  lines.push("Execution plan:");
  lines.push(
    `  ${coordinator?.name || "Coordinator"} will delegate to each specialist via handoff, collect their findings, then synthesize a scored recovery plan with implementation timeline.`
  );
  lines.push("");
  lines.push("Streaming results now...");

  return lines.join("\n");
}

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

    const backendUrl = process.env.BACKEND_URL || "http://localhost:5002";

    // Forward to backend solve endpoint with 30s timeout
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);

    let response: Response;
    try {
      response = await fetch(`${backendUrl}/api/av/solve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          problem: message,
          workflow_type: "handoff",
          orchestration_mode: "llm_directed",
          max_executor_invocations: 200,
        }),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[Chat Proxy] Backend error:", response.status, errorText);
      return NextResponse.json(
        { error: "Backend processing failed" },
        { status: response.status }
      );
    }

    const data = await response.json();
    const agentList: AgentPayload[] = data.agents || [];
    const detailedResponse = buildWorkflowSummary(data.scenario || "", agentList);

    return NextResponse.json({
      response: detailedResponse,
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
