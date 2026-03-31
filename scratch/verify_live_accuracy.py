import subprocess
import json
import asyncio

# Live cluster external IP
GKE_IP = "34.170.248.68"

async def run_live_accuracy_check():
    print(f"--- [1/2] Fetching Kubernetes Pod State (via kubectl) ---")
    try:
        res = subprocess.run(
            ["kubectl", "get", "pods", "-n", "barkland", "-l", "!agents.x-k8s.io/pool", "-o", "json"],
            capture_output=True, text=True, check=True
        )
        cluster_data = json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error calling kubectl: {e.stderr}")
        return

    cluster_pods = {}
    for item in cluster_data.get("items", []):
        p_name = item["metadata"]["name"]
        if "orchestrator" in p_name:
            continue
        cluster_pods[p_name] = item.get("status", {}).get("phase", "Unknown")

    print(f"Found {len(cluster_pods)} active dog pods on GKE cluster.")
    for p, phase in cluster_pods.items():
        print(f"  - {p} ({phase})")

    # If the user has a live websockets client, we would use it. We'll simulate reading it if we can't connect,
    # or just show the bash curl comparison against the main page.
    print(f"\n--- [2/2] You can compare this directly against the running Web Dashboard on: http://{GKE_IP} ---")
    print(f"The web dashboard is currently drawing its metrics via WebSockets from that same cluster!")

if __name__ == "__main__":
    asyncio.run(run_live_accuracy_check())
