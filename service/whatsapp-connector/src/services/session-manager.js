const QRCode = require('qrcode');

const { createWhatsAppClient } = require('../client');

const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

class SessionManager {
  constructor(config, backendService, logger, clientFactory = createWhatsAppClient) {
    this.config = config;
    this.backendService = backendService;
    this.logger = logger;
    this.clientFactory = clientFactory;
    this.sessions = new Map();
  }

  validateSessionId(sessionId) {
    if (!SESSION_ID_PATTERN.test(sessionId)) {
      throw new Error('sessionId must contain only letters, digits, underscores, or hyphens');
    }
    return sessionId;
  }

  snapshot(sessionId) {
    const entry = this.sessions.get(sessionId);
    if (!entry) {
      return {
        sessionId,
        status: 'DISCONNECTED',
        phone: null,
        lastError: null,
      };
    }
    return {
      sessionId,
      status: entry.status,
      phone: entry.phone,
      lastError: entry.lastError,
    };
  }

  qr(sessionId) {
    const entry = this.sessions.get(sessionId);
    return {
      ...this.snapshot(sessionId),
      qr: entry?.qr || null,
      dataUrl: entry?.qrDataUrl || null,
    };
  }

  async connect(sessionId = this.config.defaultSessionId) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current && ['CONNECTING', 'WAITING_QR', 'CONNECTED'].includes(current.status)) {
      return this.snapshot(sessionId);
    }
    if (current) await this.#destroyEntry(current);

    const client = this.clientFactory({ sessionId, config: this.config });
    const entry = {
      client,
      sessionId,
      status: 'CONNECTING',
      phone: null,
      qr: null,
      qrDataUrl: null,
      lastError: null,
      initialization: null,
    };
    this.sessions.set(sessionId, entry);
    this.#bindEvents(entry);

    entry.initialization = client.initialize().catch((error) => {
      entry.status = 'DISCONNECTED';
      entry.lastError = error.message;
      this.logger.error('whatsapp_initialization_failed', {
        sessionId,
        error: error.message,
      });
    });
    this.logger.info('whatsapp_initialization_started', { sessionId });
    return this.snapshot(sessionId);
  }

  async reconnect(sessionId = this.config.defaultSessionId) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current) {
      await this.#destroyEntry(current);
      this.sessions.delete(sessionId);
    }
    return this.connect(sessionId);
  }

  async disconnect(sessionId = this.config.defaultSessionId) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current) await this.#destroyEntry(current);
    this.sessions.delete(sessionId);
    return this.snapshot(sessionId);
  }

  async send({ sessionId = this.config.defaultSessionId, phone, message }) {
    this.validateSessionId(sessionId);
    const entry = this.sessions.get(sessionId);
    if (!entry || entry.status !== 'CONNECTED') {
      const error = new Error(`WhatsApp session '${sessionId}' is not connected`);
      error.statusCode = 409;
      throw error;
    }
    const digits = String(phone).replace(/\D/g, '');
    if (digits.length < 5 || digits.length > 20) {
      const error = new Error('phone must contain 5 to 20 digits including country code');
      error.statusCode = 422;
      throw error;
    }
    const result = await entry.client.sendMessage(`${digits}@c.us`, message);
    this.logger.info('whatsapp_message_sent', {
      sessionId,
      phoneSuffix: digits.slice(-4),
      messageId: result?.id?._serialized || null,
    });
    return {
      messageId: result?.id?._serialized || null,
      status: 'SENT',
    };
  }

  async shutdown() {
    await Promise.all([...this.sessions.values()].map((entry) => this.#destroyEntry(entry)));
    this.sessions.clear();
  }

  #bindEvents(entry) {
    const { client, sessionId } = entry;
    client.on('qr', (qr) => {
      entry.status = 'WAITING_QR';
      entry.qr = qr;
      entry.qrDataUrl = null;
      QRCode.toDataURL(qr)
        .then((dataUrl) => {
          if (entry.qr === qr) {
            entry.qrDataUrl = dataUrl;
            this.#forwardStatus(entry);
          }
        })
        .catch((error) => {
          this.logger.warn('whatsapp_qr_render_failed', { sessionId, error: error.message });
        });
      this.logger.info('whatsapp_qr_received', { sessionId });
    });
    client.on('authenticated', () => {
      entry.status = 'CONNECTING';
      entry.lastError = null;
      this.logger.info('whatsapp_authenticated', { sessionId });
    });
    client.on('ready', () => {
      entry.status = 'CONNECTED';
      entry.qr = null;
      entry.qrDataUrl = null;
      entry.lastError = null;
      entry.phone = client.info?.wid?.user || null;
      this.logger.info('whatsapp_connected', { sessionId, phone: entry.phone });
      this.#forwardStatus(entry);
    });
    client.on('auth_failure', (message) => {
      entry.status = 'DISCONNECTED';
      entry.lastError = String(message);
      this.logger.error('whatsapp_authentication_failed', { sessionId, error: entry.lastError });
      this.#forwardStatus(entry);
    });
    client.on('disconnected', (reason) => {
      entry.status = 'DISCONNECTED';
      entry.lastError = String(reason);
      entry.phone = null;
      this.logger.warn('whatsapp_disconnected', { sessionId, reason: entry.lastError });
      this.#forwardStatus(entry);
    });
    client.on('message', (message) => {
      this.#handleInbound(entry, message).catch((error) => {
        this.logger.error('whatsapp_inbound_processing_failed', {
          sessionId,
          messageId: message.id?._serialized || null,
          error: error.message,
        });
      });
    });
  }

  async #handleInbound(entry, message) {
    if (message.fromMe || !message.body?.trim()) return;
    if (!this.config.acceptGroupMessages && message.from.endsWith('@g.us')) return;

    let phone = message.from.split('@')[0];
    try {
      const contact = await message.getContact();
      phone = contact.number || phone;
    } catch (error) {
      this.logger.warn('whatsapp_contact_lookup_failed', {
        sessionId: entry.sessionId,
        error: error.message,
      });
    }
    const timestamp = Number(message.timestamp) || Math.floor(Date.now() / 1000);
    await this.backendService.forwardInbound({
      phone: String(phone).replace(/\D/g, ''),
      message: message.body.trim(),
      channel: 'whatsapp',
      timestamp,
      message_id: message.id?._serialized || `${entry.sessionId}:${timestamp}:${phone}`,
      session_id: entry.sessionId,
    });
  }

  async #destroyEntry(entry) {
    try {
      await entry.client.destroy();
    } catch (error) {
      this.logger.warn('whatsapp_client_destroy_failed', {
        sessionId: entry.sessionId,
        error: error.message,
      });
    }
  }

  #forwardStatus(entry) {
    this.backendService.forwardStatus({
      session_id: entry.sessionId,
      status: entry.status,
      phone: entry.phone,
      last_error: entry.lastError,
      data_url: entry.qrDataUrl,
    }).catch((error) => {
      this.logger.warn('whatsapp_status_forward_failed', {
        sessionId: entry.sessionId,
        error: error.message,
      });
    });
  }
}

module.exports = { SessionManager };
