import { NextResponse } from "next/server";

/**
 * GET /api/av/inventory
 *
 * Proxies inventory request to the backend to fetch full agent metadata,
 * tools, instructions, and scenario mappings.
 */
export async function GET() {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:5002";

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);

    let response: Response;
    try {
      response = await fetch(`${backendUrl}/api/av/inventory`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[Inventory Proxy] Backend error:", response.status, errorText);
      return NextResponse.json(
        { error: "Backend request failed" },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, max-age=300" },
    });
  } catch (error) {
    console.error("[Inventory Proxy] Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch inventory" },
      { status: 500 },
    );
  }
}
