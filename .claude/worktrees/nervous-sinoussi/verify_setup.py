#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification script for Nullsafe Phoenix v2 Day One Kernel setup.
Validates that contracts work correctly.
"""

import sys
from datetime import datetime, timezone

# Ensure UTF-8 output
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from shared.contracts import AgentReply, QueueEnvelope, ThoughtPacket


def main():
    print("=" * 60)
    print("Nullsafe Phoenix v2 - Contract Verification")
    print("=" * 60)
    print()

    # Test ThoughtPacket creation
    print("[OK] Creating ThoughtPacket...")
    packet = ThoughtPacket(
        packet_id="123e4567-e89b-12d3-a456-426614174000",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="discord",
        user_id="discord:12345",
        thread_id="channel_123",
        agent_id="cypher",
        message="Test message from verification script",
        metadata={
            "channel_id": "channel_123",
            "guild_id": "guild_456",
            "platform": "discord"
        },
        lane="praxis",
        priority=7
    )
    print(f"  - packet_id: {packet.packet_id}")
    print(f"  - agent_id: {packet.agent_id}")
    print(f"  - source: {packet.source}")
    print()

    # Test AgentReply creation
    print("[OK] Creating AgentReply...")
    reply = AgentReply(
        packet_id=packet.packet_id,
        agent_id=packet.agent_id,
        status="ok",
        reply_text="Verification successful!",
        trace={"repro_stamp": datetime.now(timezone.utc).isoformat()}
    )
    print(f"  - status: {reply.status}")
    print(f"  - reply_text: {reply.reply_text}")
    print()

    # Test JSON serialization
    print("[OK] Testing JSON serialization...")
    packet_json = packet.to_json()
    print(f"  - ThoughtPacket JSON length: {len(packet_json)} bytes")

    reply_json = reply.to_json()
    print(f"  - AgentReply JSON length: {len(reply_json)} bytes")
    print()

    # Test JSON deserialization
    print("[OK] Testing JSON deserialization...")
    restored_packet = ThoughtPacket.from_json(packet_json)
    assert restored_packet.message == packet.message
    print(f"  - Restored packet matches original [OK]")

    restored_reply = AgentReply.from_json(reply_json)
    assert restored_reply.reply_text == reply.reply_text
    print(f"  - Restored reply matches original [OK]")
    print()

    # Test QueueEnvelope
    print("[OK] Creating QueueEnvelope...")
    import json
    now = datetime.now(timezone.utc).isoformat()
    envelope = QueueEnvelope(
        packet=json.loads(packet_json),
        attempts=0,
        first_attempt_ts=now,
        last_attempt_ts=now
    )
    print(f"  - attempts: {envelope.attempts}")
    print(f"  - wrapped packet_id: {envelope.packet['packet_id']}")
    print()

    # Test envelope retry simulation
    print("[OK] Simulating retry logic...")
    envelope.attempts += 1
    envelope.last_attempt_ts = datetime.now(timezone.utc).isoformat()
    print(f"  - attempts incremented to: {envelope.attempts}")
    envelope_json = envelope.to_json()
    restored_envelope = QueueEnvelope.from_json(envelope_json)
    assert restored_envelope.attempts == 1
    print(f"  - Envelope survives serialization roundtrip [OK]")
    print()

    print("=" * 60)
    print("All contract validations passed! [OK]")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Implement Brain service (services/brain/)")
    print("  2. Implement Relay service (services/relay/)")
    print("  3. Implement Discord bot (services/discord_bot/)")
    print()


if __name__ == "__main__":
    main()
