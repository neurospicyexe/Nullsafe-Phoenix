#!/usr/bin/env pwsh
# Phoenix v2 - Smoke Test
# Validates end-to-end message flow with Brain online/offline

param(
    [string]$RelayUrl = "http://127.0.0.1:8000",
    [string]$BrainUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Phoenix v2 - Smoke Test" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Brain Health
Write-Host "[Test 1] Checking Brain health..." -ForegroundColor Yellow
try {
    $brainHealth = Invoke-RestMethod -Uri "$BrainUrl/health" -Method GET
    if ($brainHealth.status -eq "ok") {
        Write-Host "  ✓ Brain is healthy" -ForegroundColor Green
    } else {
        throw "Brain health check failed"
    }
} catch {
    Write-Host "  ✗ Brain is offline: $_" -ForegroundColor Red
    exit 1
}

# Test 2: Relay Status (Brain should be online)
Write-Host "[Test 2] Checking Relay status..." -ForegroundColor Yellow
try {
    $relayStatus = Invoke-RestMethod -Uri "$RelayUrl/status" -Method GET
    if ($relayStatus.brain_status -eq "online") {
        Write-Host "  ✓ Relay sees Brain as online" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Relay sees Brain as: $($relayStatus.brain_status)" -ForegroundColor Yellow
    }

    Write-Host "  Queue depths:" -ForegroundColor Cyan
    Write-Host "    Incoming: $($relayStatus.queue_lengths.incoming)" -ForegroundColor Cyan
    Write-Host "    Inflight: $($relayStatus.queue_lengths.inflight)" -ForegroundColor Cyan
    Write-Host "    Deadletter: $($relayStatus.queue_lengths.deadletter)" -ForegroundColor Cyan
    Write-Host "    Outbox (drevan): $($relayStatus.queue_lengths.outbox.drevan)" -ForegroundColor Cyan
    Write-Host "    Outbox (cypher): $($relayStatus.queue_lengths.outbox.cypher)" -ForegroundColor Cyan
    Write-Host "    Outbox (gaia): $($relayStatus.queue_lengths.outbox.gaia)" -ForegroundColor Cyan
} catch {
    Write-Host "  ✗ Relay status check failed: $_" -ForegroundColor Red
    exit 1
}

# Test 3: Send packet with Brain online (fast path)
Write-Host "[Test 3] Sending packet with Brain online (fast path)..." -ForegroundColor Yellow
$packet1 = @{
    packet_id = [guid]::NewGuid().ToString()
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    source = "system"
    user_id = "smoke_test:user1"
    thread_id = "smoke_test_thread"
    agent_id = "cypher"
    message = "Hello from smoke test (fast path)"
    metadata = @{
        test = "smoke_fast"
    }
}

try {
    $reply1 = Invoke-RestMethod -Uri "$RelayUrl/ingest" -Method POST -Body ($packet1 | ConvertTo-Json) -ContentType "application/json"

    if ($reply1.status -eq "ok") {
        $replyPreview = $reply1.reply_text.Substring(0, [Math]::Min(50, $reply1.reply_text.Length))
        Write-Host "  ✓ Fast path success: $replyPreview..." -ForegroundColor Green
    } else {
        Write-Host "  ✗ Unexpected status: $($reply1.status)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ✗ Fast path test failed: $_" -ForegroundColor Red
    exit 1
}

# Test 4: Stop Brain and send packet (queued path)
Write-Host "[Test 4] Please STOP the Brain service now and press Enter..." -ForegroundColor Yellow
Read-Host

Write-Host "[Test 4] Sending packet with Brain offline (queued)..." -ForegroundColor Yellow
$packet2 = @{
    packet_id = [guid]::NewGuid().ToString()
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    source = "system"
    user_id = "smoke_test:user2"
    thread_id = "smoke_test_thread"
    agent_id = "gaia"
    message = "Hello from smoke test (queued path)"
    metadata = @{
        test = "smoke_queued"
    }
}

try {
    $reply2 = Invoke-RestMethod -Uri "$RelayUrl/ingest" -Method POST -Body ($packet2 | ConvertTo-Json) -ContentType "application/json"

    if ($reply2.status -eq "queued") {
        Write-Host "  ✓ Packet queued successfully" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Expected 'queued', got: $($reply2.status)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ✗ Queued path test failed: $_" -ForegroundColor Red
    exit 1
}

# Test 5: Verify queue depth increased
Write-Host "[Test 5] Verifying queue depth..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
$statusAfterQueue = Invoke-RestMethod -Uri "$RelayUrl/status" -Method GET

if ($statusAfterQueue.queue_lengths.incoming -gt 0) {
    Write-Host "  ✓ Incoming queue has packets: $($statusAfterQueue.queue_lengths.incoming)" -ForegroundColor Green
} else {
    Write-Host "  ✗ Expected packets in queue, found: $($statusAfterQueue.queue_lengths.incoming)" -ForegroundColor Red
    exit 1
}

# Test 6: Restart Brain and wait for drain
Write-Host "[Test 6] Please RESTART the Brain service now and press Enter..." -ForegroundColor Yellow
Read-Host

Write-Host "[Test 6] Waiting for drainer to process queue (max 30s)..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 2
    $waited += 2

    $statusCheck = Invoke-RestMethod -Uri "$RelayUrl/status" -Method GET

    if ($statusCheck.queue_lengths.incoming -eq 0) {
        Write-Host "  ✓ Queue drained successfully (took ${waited}s)" -ForegroundColor Green
        break
    }

    Write-Host "  Waiting... (${waited}s / ${maxWait}s) Queue: $($statusCheck.queue_lengths.incoming)" -ForegroundColor Cyan
}

if ($statusCheck.queue_lengths.incoming -gt 0) {
    Write-Host "  ✗ Queue not drained after ${maxWait}s" -ForegroundColor Red
    exit 1
}

# Test 7: Verify reply in outbox
Write-Host "[Test 7] Verifying reply in outbox..." -ForegroundColor Yellow
$finalStatus = Invoke-RestMethod -Uri "$RelayUrl/status" -Method GET

$totalOutbox = $finalStatus.queue_lengths.outbox.drevan + $finalStatus.queue_lengths.outbox.cypher + $finalStatus.queue_lengths.outbox.gaia

if ($totalOutbox -gt 0) {
    Write-Host "  ✓ Reply in outbox (total: $totalOutbox)" -ForegroundColor Green
    Write-Host "    Drevan: $($finalStatus.queue_lengths.outbox.drevan)" -ForegroundColor Cyan
    Write-Host "    Cypher: $($finalStatus.queue_lengths.outbox.cypher)" -ForegroundColor Cyan
    Write-Host "    Gaia: $($finalStatus.queue_lengths.outbox.gaia)" -ForegroundColor Cyan
} else {
    Write-Host "  ⚠ No replies in outbox (may have been consumed)" -ForegroundColor Yellow
}

# Test 8: Duplicate packet test
Write-Host "[Test 8] Testing deduplication..." -ForegroundColor Yellow
try {
    # Send same packet again
    $dupReply = Invoke-RestMethod -Uri "$RelayUrl/ingest" -Method POST -Body ($packet1 | ConvertTo-Json) -ContentType "application/json"

    if ($dupReply.status -eq "queued" -and $dupReply.trace.dedupe) {
        Write-Host "  ✓ Duplicate packet rejected correctly" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Duplicate handling unclear: $($dupReply.status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ Duplicate test failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Smoke Test Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
