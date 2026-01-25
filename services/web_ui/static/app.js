// Phoenix v2 Web UI - Client-Side JavaScript

// Global state
let sessionId = null;
let isLoading = false;
const messages = [];

// DOM elements
let messageInput, sendButton, messagesContainer;
let agentSelect, laneSelect, threadIdDisplay;

// UUID v4 generator
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Initialize session
function initSession() {
    sessionId = localStorage.getItem('phoenix_session_id');
    if (!sessionId) {
        sessionId = generateUUID();
        localStorage.setItem('phoenix_session_id', sessionId);
    }

    if (threadIdDisplay) {
        threadIdDisplay.textContent = sessionId.substring(0, 8);
    }
}

// Poll status from Relay
async function pollStatus() {
    try {
        const response = await fetch(`${RELAY_API_URL}/status`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        updateStatus(data);
        hideErrorBanner();
    } catch (error) {
        console.error('Failed to fetch status:', error);
        showErrorBanner(`⚠️ ${error.message}`);
    }
}

// Update status UI
function updateStatus(data) {
    // Relay status
    const relayStatus = document.getElementById('relay-status');
    if (relayStatus) {
        relayStatus.textContent = data.relay_status;
        relayStatus.className = `status-value ${data.relay_status === 'ok' ? 'ok' : 'error'}`;
    }

    const redisStatus = document.getElementById('redis-status');
    if (redisStatus) {
        redisStatus.textContent = data.redis_connected ? 'connected' : 'disconnected';
        redisStatus.className = `status-value ${data.redis_connected ? 'ok' : 'error'}`;
    }

    const drainerStatus = document.getElementById('drainer-status');
    if (drainerStatus) {
        drainerStatus.textContent = data.drainer_running ? 'running' : 'stopped';
        drainerStatus.className = `status-value ${data.drainer_running ? 'ok' : 'error'}`;
    }

    // Brain status
    const brainStatus = document.getElementById('brain-status');
    if (brainStatus) {
        brainStatus.textContent = data.brain_status;
        brainStatus.className = `status-value ${data.brain_status === 'online' ? 'ok' : 'warning'}`;
    }

    const brainUrl = document.getElementById('brain-url');
    if (brainUrl) {
        brainUrl.textContent = data.brain_url;
    }

    // Queue lengths
    if (data.queue_lengths) {
        const incoming = document.getElementById('queue-incoming');
        if (incoming) incoming.textContent = data.queue_lengths.incoming;

        const inflight = document.getElementById('queue-inflight');
        if (inflight) inflight.textContent = data.queue_lengths.inflight;

        const outbox = document.getElementById('queue-outbox');
        if (outbox) outbox.textContent = data.queue_lengths.outbox;

        const deadletter = document.getElementById('queue-deadletter');
        if (deadletter) {
            deadletter.textContent = data.queue_lengths.deadletter;
            deadletter.className = `status-value ${data.queue_lengths.deadletter > 0 ? 'error' : ''}`;
        }
    }

    // Update timestamp
    const lastUpdate = document.getElementById('last-update');
    if (lastUpdate) {
        const now = new Date().toLocaleTimeString();
        lastUpdate.textContent = `Last update: ${now}`;
    }
}

// Show/hide error banner
function showErrorBanner(message) {
    const banner = document.getElementById('error-banner');
    if (banner) {
        banner.textContent = message;
        banner.style.display = 'block';
    }
}

function hideErrorBanner() {
    const banner = document.getElementById('error-banner');
    if (banner) {
        banner.style.display = 'none';
    }
}

// Show/hide error message
function showErrorMessage(message) {
    const errorMsg = document.getElementById('error-message');
    if (errorMsg) {
        errorMsg.textContent = `⚠️ ${message}`;
        errorMsg.style.display = 'block';
    }
}

function hideErrorMessage() {
    const errorMsg = document.getElementById('error-message');
    if (errorMsg) {
        errorMsg.style.display = 'none';
    }
}

// Add message to chat
function addMessage(type, content, packetId = null) {
    const message = {
        id: generateUUID(),
        type: type, // 'user', 'agent', 'system'
        content: content,
        packetId: packetId,
        timestamp: new Date()
    };

    messages.push(message);
    renderMessages();
}

// Render all messages
function renderMessages() {
    if (!messagesContainer) return;

    // Clear existing messages except welcome
    messagesContainer.innerHTML = '';

    if (messages.length === 0) {
        messagesContainer.innerHTML = '<div class="welcome-message">No messages yet. Start a conversation!</div>';
        return;
    }

    messages.forEach(msg => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.type}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = msg.content;

        contentDiv.appendChild(textDiv);

        if (msg.packetId) {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'message-meta';
            metaDiv.textContent = msg.packetId.substring(0, 6);
            contentDiv.appendChild(metaDiv);
        }

        messageDiv.appendChild(contentDiv);
        messagesContainer.appendChild(messageDiv);
    });

    // Auto-scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Send message
async function sendMessage() {
    if (!messageInput || !sessionId || isLoading) return;

    const content = messageInput.value.trim();
    if (!content) return;

    const packetId = generateUUID();
    const timestamp = new Date().toISOString();
    const agent = agentSelect.value;
    const lane = laneSelect.value;

    // Add user message
    addMessage('user', content, packetId);
    messageInput.value = '';

    // Disable input
    isLoading = true;
    updateInputState();
    hideErrorMessage();

    // Construct ThoughtPacket
    const packet = {
        packet_id: packetId,
        timestamp: timestamp,
        source: 'webui',
        user_id: `webui:${sessionId}`,
        thread_id: sessionId,
        agent_id: agent,
        message: content,
        metadata: {
            platform: 'webui'
        }
    };

    // Add lane if selected
    if (lane) {
        packet.metadata.lane = lane;
    }

    try {
        // POST to Relay /ingest
        const response = await fetch(`${RELAY_API_URL}/ingest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(packet)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reply = await response.json();

        if (reply.status === 'ok') {
            // Fast path success
            addMessage('agent', reply.reply_text, reply.packet_id);
        } else if (reply.status === 'queued') {
            // Queued
            addMessage('system', `⏳ Queued (ID: ${reply.packet_id.substring(0, 8)})`, reply.packet_id);
        } else {
            // Error or other status
            throw new Error(`Unexpected status: ${reply.status}`);
        }
    } catch (error) {
        console.error('Failed to send message:', error);
        showErrorMessage(error.message);
        addMessage('system', `❌ Error: ${error.message}`);
    } finally {
        isLoading = false;
        updateInputState();
    }
}

// Update input state
function updateInputState() {
    if (messageInput) {
        messageInput.disabled = isLoading;
    }
    if (sendButton) {
        sendButton.disabled = isLoading || !messageInput || !messageInput.value.trim();
        sendButton.textContent = isLoading ? 'Sending...' : 'Send';
    }
}

// Handle Enter key
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Initialize UI
function initUI() {
    // Get DOM elements
    messageInput = document.getElementById('message-input');
    sendButton = document.getElementById('send-button');
    messagesContainer = document.getElementById('messages');
    agentSelect = document.getElementById('agent-select');
    laneSelect = document.getElementById('lane-select');
    threadIdDisplay = document.getElementById('thread-id');

    // Initialize session
    initSession();

    // Setup event listeners
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('keypress', handleKeyPress);
        messageInput.addEventListener('input', updateInputState);
    }

    // Initial UI update
    updateInputState();
    renderMessages();

    // Start status polling
    pollStatus();
    setInterval(pollStatus, 2000);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUI);
} else {
    initUI();
}
