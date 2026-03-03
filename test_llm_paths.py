#!/usr/bin/env python3
"""
Test every LLM call path used by the orchestrator and agents.

Tests:
  1. Agent client (gpt-5-nano)        — get_chat_client(role="agent") creation
  2. Orchestrator client (gpt-5-mini)  — get_chat_client(role="orchestrator") creation
  3. Async shared client (gpt-5-mini)  — get_shared_async_client() → chat.completions.create
  4. ChatAgent run (gpt-5-nano)        — full Agent Framework ChatAgent with tools
  5. Orchestrator planning call         — mimics engine._llm_plan_agent_selection pattern
  6. Coordinator ChatAgent run (gpt-5-mini) — recovery_coordinator with tools
"""

import asyncio
import json
import os
import sys
import time

# ── Load .env ────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from agents.client import get_chat_client, clear_client_cache
from data_sources.shared_utils import OPENAI_API_VERSION, supports_explicit_temperature

DIVIDER = "=" * 70
results = []


def report(test_name, deployment, status, latency, detail=""):
    results.append({"test": test_name, "deployment": deployment, "status": status, "latency": latency, "detail": detail})
    icon = "PASS" if status == "OK" else "FAIL"
    print(f"  [{icon}] {latency:.2f}s  {detail[:120]}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Agent client creation (gpt-5-nano)
# ─────────────────────────────────────────────────────────────────────────────
def test_agent_client():
    print(f"\n{DIVIDER}")
    print("  Test 1: Agent Client (gpt-5-nano) — get_chat_client(role='agent')")
    print(DIVIDER)

    t0 = time.perf_counter()
    try:
        client = get_chat_client(role="agent")
        elapsed = time.perf_counter() - t0
        print(f"  Client type: {type(client).__name__}")
        report("agent_client_creation", "gpt-5-nano", "OK", elapsed, f"type={type(client).__name__}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        report("agent_client_creation", "gpt-5-nano", "FAIL", elapsed, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Orchestrator client creation (gpt-5-mini)
# ─────────────────────────────────────────────────────────────────────────────
def test_orchestrator_client():
    print(f"\n{DIVIDER}")
    print("  Test 2: Orchestrator Client (gpt-5-mini) — get_chat_client(role='orchestrator')")
    print(DIVIDER)

    t0 = time.perf_counter()
    try:
        client = get_chat_client(role="orchestrator")
        elapsed = time.perf_counter() - t0
        print(f"  Client type: {type(client).__name__}")
        report("orchestrator_client_creation", "gpt-5-mini", "OK", elapsed, f"type={type(client).__name__}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        report("orchestrator_client_creation", "gpt-5-mini", "FAIL", elapsed, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Async shared client — direct chat.completions.create (gpt-5-mini)
# ─────────────────────────────────────────────────────────────────────────────
async def test_async_shared_client():
    print(f"\n{DIVIDER}")
    print("  Test 3: Async Shared Client — chat.completions.create (gpt-5-mini)")
    print(DIVIDER)

    # Reset singleton to avoid stale client from prior event loop
    import data_sources.azure_client as ac
    ac._shared_client = None
    ac._shared_auth_mode = ""

    model = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
    request_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with a one-sentence answer."},
            {"role": "user", "content": "What is the ICAO code for Istanbul Airport?"},
        ],
    }
    temp_supported = supports_explicit_temperature(model)
    if temp_supported:
        request_kwargs["temperature"] = 0
    print(f"  Model: {model}")
    print(f"  supports_explicit_temperature: {temp_supported}")

    t0 = time.perf_counter()
    try:
        client, auth_mode = await ac.get_shared_async_client(api_version=OPENAI_API_VERSION)
        response = await asyncio.wait_for(
            client.chat.completions.create(**request_kwargs),
            timeout=30,
        )
        elapsed = time.perf_counter() - t0
        content = response.choices[0].message.content
        usage = response.usage
        print(f"  Auth: {auth_mode}")
        print(f"  Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
        print(f"  Reply: {content}")
        report("async_shared_client", model, "OK", elapsed, f"auth={auth_mode} | {content[:80]}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        report("async_shared_client", model, "FAIL", elapsed, f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Full ChatAgent run (gpt-5-nano) with a tool
# ─────────────────────────────────────────────────────────────────────────────
async def test_chatagent_run():
    print(f"\n{DIVIDER}")
    print("  Test 4: ChatAgent Run (gpt-5-nano) — flight_analyst with tools")
    print(DIVIDER)

    from agents.flight_analyst import create_flight_analyst

    t0 = time.perf_counter()
    try:
        clear_client_cache()
        agent = create_flight_analyst(name="test_flight_analyst")
        print(f"  Agent: {agent.name}, type={type(agent).__name__}")

        response = await agent.run("Analyze flights AA100 and UA200. Check weather at JFK.")
        elapsed = time.perf_counter() - t0

        msg_count = len(response.messages) if response.messages else 0
        last_msg = ""
        if response.messages:
            for m in reversed(response.messages):
                text = getattr(m, "content", None) or ""
                if isinstance(text, str) and len(text) > 10:
                    last_msg = text[:200]
                    break
                # Handle list content (tool calls)
                if isinstance(text, list):
                    for part in text:
                        t = getattr(part, "text", None) or ""
                        if t and len(t) > 10:
                            last_msg = t[:200]
                            break

        print(f"  Messages: {msg_count}")
        print(f"  Last reply: {last_msg[:150]}")
        report("chatagent_run", "gpt-5-nano", "OK", elapsed, f"{msg_count} msgs | {last_msg[:60]}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        import traceback
        traceback.print_exc()
        report("chatagent_run", "gpt-5-nano", "FAIL", elapsed, f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Orchestrator planning call pattern (gpt-5-mini)
# ─────────────────────────────────────────────────────────────────────────────
async def test_orchestrator_planning():
    print(f"\n{DIVIDER}")
    print("  Test 5: Orchestrator Planning Call (gpt-5-mini) — JSON agent selection")
    print(DIVIDER)

    import data_sources.azure_client as ac

    model = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
    system_prompt = """You are an aviation orchestrator. Given a problem, select the best agents.
Return ONLY valid JSON: {"selectedAgentIds": [...], "reasoning": "..."}"""

    user_payload = {
        "problem": "Flight AA100 has a mechanical issue at gate B12. Need to assess impact.",
        "scenario": "predictive_maintenance",
        "candidateAgents": [
            {"id": "situation_assessment", "name": "Situation Assessment"},
            {"id": "fleet_recovery", "name": "Fleet Recovery"},
            {"id": "maintenance_predictor", "name": "Maintenance Predictor"},
        ],
    }

    request_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    }
    if supports_explicit_temperature(model):
        request_kwargs["temperature"] = 0

    t0 = time.perf_counter()
    try:
        client, auth_mode = await ac.get_shared_async_client(api_version=OPENAI_API_VERSION)
        response = await asyncio.wait_for(
            client.chat.completions.create(**request_kwargs),
            timeout=30,
        )
        elapsed = time.perf_counter() - t0
        raw = response.choices[0].message.content or ""
        usage = response.usage
        print(f"  Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
        print(f"  Raw: {raw[:300]}")

        import re
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', raw)
            parsed = json.loads(match.group()) if match else None

        if parsed and "selectedAgentIds" in parsed:
            print(f"  Parsed agents: {parsed['selectedAgentIds']}")
            report("orchestrator_planning", model, "OK", elapsed, f"agents={parsed['selectedAgentIds']}")
        else:
            report("orchestrator_planning", model, "OK", elapsed, f"response OK, parse partial: {raw[:80]}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        report("orchestrator_planning", model, "FAIL", elapsed, f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Coordinator ChatAgent run (gpt-5-mini) with coordinator tools
# ─────────────────────────────────────────────────────────────────────────────
async def test_coordinator_agent_run():
    print(f"\n{DIVIDER}")
    print("  Test 6: Coordinator ChatAgent Run (gpt-5-mini) — recovery_coordinator")
    print(DIVIDER)

    from agents.recovery_coordinator import create_recovery_coordinator

    t0 = time.perf_counter()
    try:
        clear_client_cache()
        agent = create_recovery_coordinator(name="test_coordinator")
        print(f"  Agent: {agent.name}, type={type(agent).__name__}")

        response = await agent.run(
            "A hub disruption at DFW is causing cascading delays. "
            "Score recovery option: swap tail N12345 and rebalance crew pairings."
        )
        elapsed = time.perf_counter() - t0

        msg_count = len(response.messages) if response.messages else 0
        last_msg = ""
        if response.messages:
            for m in reversed(response.messages):
                text = getattr(m, "content", None) or ""
                if isinstance(text, str) and len(text) > 10:
                    last_msg = text[:200]
                    break
                if isinstance(text, list):
                    for part in text:
                        t = getattr(part, "text", None) or ""
                        if t and len(t) > 10:
                            last_msg = t[:200]
                            break

        print(f"  Messages: {msg_count}")
        print(f"  Last reply: {last_msg[:150]}")
        report("coordinator_agent_run", "gpt-5-mini", "OK", elapsed, f"{msg_count} msgs | {last_msg[:60]}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        import traceback
        traceback.print_exc()
        report("coordinator_agent_run", "gpt-5-mini", "FAIL", elapsed, f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'#' * 70}")
    print("  LLM Call Path Verification — Aviation Multi-Agent System")
    print(f"{'#' * 70}")
    print(f"  Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT', 'NOT SET')}")
    print(f"  Auth mode: {os.getenv('AZURE_OPENAI_AUTH_MODE', 'auto')}")
    print(f"  Agent deployment: {os.getenv('AZURE_OPENAI_AGENT_DEPLOYMENT', 'gpt-5-nano')}")
    print(f"  Orchestrator deployment: {os.getenv('AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT', 'gpt-5-mini')}")
    print(f"  API version (shared_utils): {OPENAI_API_VERSION}")

    # Synchronous tests (client creation only)
    test_agent_client()
    test_orchestrator_client()

    # Async tests (actual LLM calls)
    await test_async_shared_client()
    await test_chatagent_run()
    await test_orchestrator_planning()
    await test_coordinator_agent_run()

    # Summary
    print(f"\n{'#' * 70}")
    print("  SUMMARY")
    print(f"{'#' * 70}")
    all_ok = True
    for r in results:
        icon = "PASS" if r["status"] == "OK" else "FAIL"
        print(f"  [{icon}] {r['test']:35s} {r['deployment']:15s} {r['latency']:6.2f}s")
        if r["status"] != "OK":
            all_ok = False
            print(f"         {r['detail'][:100]}")

    print()
    if all_ok:
        print("  All 6 LLM call paths verified successfully.")
    else:
        failed = [r for r in results if r["status"] != "OK"]
        print(f"  {len(failed)} test(s) FAILED — review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
