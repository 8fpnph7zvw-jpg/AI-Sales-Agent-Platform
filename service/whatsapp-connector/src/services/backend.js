class BackendService {
  constructor(config, logger) {
    this.baseUrl = config.backendApiUrl;
    this.connectorId = config.backendConnectorId;
    this.token = config.backendApiToken;
    this.logger = logger;
  }

  async forwardInbound(payload) {
    if (!this.baseUrl) {
      throw new Error('BACKEND_API_URL is required before forwarding messages');
    }
    if (!this.connectorId) {
      throw new Error('BACKEND_CONNECTOR_ID is required before forwarding messages');
    }

    const response = await fetch(`${this.baseUrl}/conversations/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-WhatsApp-Gateway-Token': this.token,
      },
      body: JSON.stringify({
        ...payload,
        connector_id: this.connectorId,
      }),
      signal: AbortSignal.timeout(70_000),
    });

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body?.error?.message || body?.detail || response.statusText;
      throw new Error(`FastAPI rejected WhatsApp message (${response.status}): ${detail}`);
    }
    this.logger.info('backend_message_accepted', {
      messageId: payload.message_id,
      processed: body.processed,
      duplicates: body.duplicates,
    });
    return body;
  }
}

module.exports = { BackendService };
