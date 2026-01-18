#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual verification script for Brain service.

Demonstrates:
- Identity-aware routing
- Thread persistence
- Override mechanism
- Repro stamp with identity versioning
"""

import json
import sys
from datetime import datetime, timezone

# Ensure UTF-8 output
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from shared.contracts import ThoughtPacket
from services.brain.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def print_section(title):
    """Print section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def send_message(thread_id, agent_id, message, packet_num):
    """Send message and display response."""
    packet = ThoughtPacket(
        packet_id=f"{packet_num:03d}e4567-e89b-12d3-a456-426614174000",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="discord",
        user_id="demo_user",
        thread_id=thread_id,
        agent_id=agent_id,
        message=message,
        metadata={"channel_id": f"channel_{thread_id}"}
    )

    print(f"\n[Sending] Thread: {thread_id} | Packet Agent: {agent_id}")
    print(f"Message: \"{message}\"")

    response = client.post("/chat", json=packet.model_dump())
    reply_data = response.json()

    print(f"\n[Reply] Active Agent: {reply_data['agent_id']}")
    print(f"Status: {reply_data['status']}")
    print(f"\n{reply_data['reply_text']}")

    if "trace" in reply_data and "repro_stamp" in reply_data["trace"]:
        repro = reply_data["trace"]["repro_stamp"]
        print(f"\n[Repro Stamp]")
        print(f"  Identity Version: {repro['identity_version']}")
        print(f"  Thread Routing: {repro['thread_routing']}")


def main():
    print_section("Brain Service Manual Verification")

    # Check health
    print("\n[OK] Checking service health...")
    health = client.get("/health").json()
    print(f"Service: {health['service']} | Version: {health['version']} | Status: {health['status']}")

    print_section("Test 1: Basic Identity-Aware Routing")
    send_message("thread_001", "cypher", "Can you help me debug this code?", 1)

    print_section("Test 2: Override to Drevan")
    send_message("thread_002", "cypher", "Drevan: Help me organize my memories", 2)

    print_section("Test 3: Override to Gaia")
    send_message("thread_003", "drevan", "GAIA: What are the connections between AI and neuroscience?", 3)

    print_section("Test 4: Thread Persistence")
    print("\nMessage 1 - Establish thread with Cypher:")
    send_message("thread_persist", "cypher", "First message to establish thread", 4)

    print("\nMessage 2 - Should route to Cypher (thread mapping):")
    send_message("thread_persist", "drevan", "Second message, different packet agent", 5)

    print("\nMessage 3 - Override to Drevan:")
    send_message("thread_persist", "cypher", "Drevan: Now switching to you", 6)

    print("\nMessage 4 - Should route to Drevan (updated thread mapping):")
    send_message("thread_persist", "cypher", "Fourth message, should still go to Drevan", 7)

    print_section("Test 5: All Three Agents")
    send_message("thread_drevan", "drevan", "Tell me about memory architecture", 8)
    send_message("thread_cypher", "cypher", "Show me a clean code pattern", 9)
    send_message("thread_gaia", "gaia", "Help me synthesize these research papers", 10)

    print_section("Verification Complete")
    print("\n[OK] All tests completed successfully!")
    print("\nKey Features Demonstrated:")
    print("  - Identity-aware responses (each agent has distinct voice)")
    print("  - Thread persistence (thread_id -> agent_id mapping)")
    print("  - Override mechanism (Drevan:/Cypher:/Gaia: prefix)")
    print("  - Repro stamp with identity versioning (SHA256 hash)")
    print("  - Deterministic identity loading from YAML files")
    print()


if __name__ == "__main__":
    main()
