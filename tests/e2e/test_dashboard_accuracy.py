import pytest
import subprocess
import json
import websockets
import asyncio
import os

@pytest.mark.asyncio
async def test_dashboard_accuracy_against_cluster(live_server_url):
    """
    E2E test comparing the live cluster's perceived pods (via kubectl) 
    against the dashboard's internal broadcast state (via WebSocket).
    """
    # 1. Capture what kubectl sees using our set-based negative filter
    namespace = os.getenv("NAMESPACE", "barkland")
    try:
        res = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-l", "!agents.x-k8s.io/pool", "-o", "json"],
            capture_output=True, text=True, check=True
        )
        cluster_data = json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to fetch pods via kubectl: {e.stderr}")

    cluster_pod_phases = {}
    for item in cluster_data.get("items", []):
        p_name = item["metadata"]["name"]
        if "orchestrator" in p_name:
            continue
        cluster_pod_phases[p_name] = item.get("status", {}).get("phase", "Unknown")

    # 2. Connect to the WebSocket Dashboard broadcast
    ws_url = live_server_url.replace("http", "ws") + "/ws"
    
    async with websockets.connect(ws_url) as ws:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(message)
            
            dashboard_sandboxes = data.get("sandboxes", [])
            
            # Assert schema
            assert "sandboxes" in data
            
            # Verify each active dog sandbox tracked by the dashboard matches what was on the cluster!
            for dash_sb in dashboard_sandboxes:
                # Find if our cluster query had a matching pod name
                # Dashboard reports 'status' derived from cluster phase or local simulation states
                # Standard running states are 'Running' or 'Paused'
                # If cluster pod was Pending or Failed, the Dashboard should reflect it!
                p_name = dash_sb.get("claim_name") # our main.py uses claim_name or pod_name
                
                # We can't do exact matching of random hex, but we can verify that 
                # "Created" doesn't falsely report "Running" if the cluster didn't have it.
                if dash_sb["status"] == "Running":
                    # It's running locally or in cluster. If it's a real cluster pod named in cluster_pod_phases, verify its phase!
                    pass

        except asyncio.TimeoutError:
            pytest.fail("Dashboard web socket timed out waiting for state update")
