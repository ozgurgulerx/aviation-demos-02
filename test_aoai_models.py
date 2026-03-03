"""
Quick smoke test for Azure OpenAI deployments: gpt-5-nano and gpt-5-mini.
Uses the openai SDK directly with api-key auth.
"""

import os
import sys
import time

# Load .env manually
env_path = os.path.join(os.path.dirname(__file__), ".env")
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

from openai import AzureOpenAI

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

DEPLOYMENTS = ["gpt-5-nano", "gpt-5-mini"]

PROMPT = "You are a helpful assistant. Reply in one sentence."
USER_MSG = "What is the ICAO code for London Heathrow airport?"


def test_deployment(client: AzureOpenAI, deployment: str) -> dict:
    """Call a single deployment and return timing + response."""
    print(f"\n{'='*60}")
    print(f"  Testing: {deployment}")
    print(f"  Endpoint: {ENDPOINT}")
    print(f"  API Version: {API_VERSION}")
    print(f"{'='*60}")

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": USER_MSG},
            ],
            max_completion_tokens=100,
        )
        elapsed = time.perf_counter() - t0
        content = response.choices[0].message.content
        usage = response.usage
        print(f"  Status:  OK")
        print(f"  Latency: {elapsed:.2f}s")
        print(f"  Tokens:  prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
        print(f"  Reply:   {content}")
        return {"deployment": deployment, "status": "OK", "latency": elapsed, "reply": content}
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  Status:  FAILED")
        print(f"  Latency: {elapsed:.2f}s")
        print(f"  Error:   {type(e).__name__}: {e}")
        return {"deployment": deployment, "status": "FAILED", "latency": elapsed, "error": str(e)}


def main():
    if not ENDPOINT:
        print("ERROR: AZURE_OPENAI_ENDPOINT not set")
        sys.exit(1)
    if not API_KEY:
        print("ERROR: AZURE_OPENAI_API_KEY not set")
        sys.exit(1)

    print(f"Azure OpenAI Deployment Smoke Test")
    print(f"Endpoint: {ENDPOINT}")
    print(f"API Version: {API_VERSION}")
    print(f"Auth: api-key (key={'*'*4}{API_KEY[-4:]})")

    client = AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_key=API_KEY,
        api_version=API_VERSION,
    )

    results = []
    for dep in DEPLOYMENTS:
        results.append(test_deployment(client, dep))

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    all_ok = True
    for r in results:
        status_icon = "PASS" if r["status"] == "OK" else "FAIL"
        print(f"  [{status_icon}] {r['deployment']:20s}  {r['latency']:.2f}s")
        if r["status"] != "OK":
            all_ok = False

    if all_ok:
        print("\nAll deployments responding correctly.")
    else:
        print("\nSome deployments FAILED — check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
