const QRCode = require('qrcode');
const path = require('node:path');

const { createWhatsAppClient } = require('../client');
const {
  inspectStoredSessions,
  profileLockDetails,
  sessionProfilePath,
  waitForProfileUnlock,
} = require('./session-store');

const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function serializedId(value) {
  if (typeof value === 'string') return value;
  return value?._serialized || value?.id?._serialized || null;
}

function preferredChatId(...values) {
  const ids = values.map(serializedId).filter(Boolean);
  return ids.find((id) => id.endsWith('@lid')) || ids[0] || null;
}

async function withTimeout(promise, timeoutMs, message) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

class SessionManager {
  constructor(config, backendService, logger, clientFactory = createWhatsAppClient) {
    this.config = {
      readyTimeoutMs: 120_000,
      readyRetryLimit: 1,
      browserShutdownTimeoutMs: 10_000,
      profileUnlockTimeoutMs: 5_000,
      autoRestoreSessions: false,
      autoRestoreDefaultSession: false,
      ...config,
    };
    this.config.sessionsPath ||= path.resolve(process.cwd(), 'sessions');
    this.backendService = backendService;
    this.logger = logger;
    this.clientFactory = clientFactory;
    this.sessions = new Map();
    this.profileClaims = new Map();
  }

  validateSessionId(sessionId) {
    if (typeof sessionId !== 'string' || !SESSION_ID_PATTERN.test(sessionId)) {
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

  async restoreConfiguredSessions() {
    const storedSessions = inspectStoredSessions(
      this.config.sessionsPath,
      this.config.defaultSessionId,
    );
    const restoreIds = new Set();
    if (this.config.autoRestoreSessions) {
      for (const stored of storedSessions) {
        if (!stored.isDefaultSession || this.config.autoRestoreDefaultSession) {
          restoreIds.add(stored.sessionId);
        }
      }
    }
    if (this.config.autoRestoreDefaultSession) {
      restoreIds.add(this.config.defaultSessionId);
    }

    this.logger.info('whatsapp_session_inventory', {
      sessionsPath: this.config.sessionsPath,
      defaultSessionId: this.config.defaultSessionId,
      legacyDefaultSessionPresent: storedSessions.some((item) => item.isDefaultSession),
      sessions: storedSessions.map((item) => ({
        sessionId: item.sessionId,
        status: item.status,
        isDefaultSession: item.isDefaultSession,
        willRestore: restoreIds.has(item.sessionId),
        lastModifiedAt: item.lastModifiedAt,
        locks: item.locks,
      })),
    });

    for (const sessionId of restoreIds) {
      this.logger.info('whatsapp_session_restore_started', { sessionId });
      await this.connect(sessionId, { source: 'startup_restore' });
    }
    return storedSessions;
  }

  async connect(
    sessionId = this.config.defaultSessionId,
    { source = 'api', readyRetryCount = 0 } = {},
  ) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current && ['CONNECTING', 'WAITING_QR', 'CONNECTED'].includes(current.status)) {
      return this.snapshot(sessionId);
    }
    if (current) {
      await this.#destroyEntry(current, 'replace_disconnected_client');
      this.sessions.delete(sessionId);
    }

    const profilePath = sessionProfilePath(this.config.sessionsPath, sessionId);
    const profileKey = profilePath.toLowerCase();
    const claimedBy = this.profileClaims.get(profileKey);
    if (claimedBy && claimedBy !== sessionId) {
      const error = new Error(
        `LocalAuth profile '${profilePath}' is already claimed by session '${claimedBy}'`,
      );
      error.statusCode = 409;
      throw error;
    }

    const locks = profileLockDetails(profilePath);
    if (locks.length) {
      this.logger.warn('whatsapp_profile_lock_detected', {
        sessionId,
        profilePath,
        locks,
        action: 'Chromium will validate whether the existing profile lock is stale',
      });
    }

    this.logger.info('whatsapp_session_create', {
      sessionId,
      clientId: sessionId,
      dataPath: this.config.sessionsPath,
      webVersionCachePath: this.config.webVersionCachePath,
      profilePath,
      source,
      readyRetryCount,
    });
    const client = this.clientFactory({ sessionId, config: this.config });
    const entry = {
      client,
      sessionId,
      profilePath,
      source,
      status: 'CONNECTING',
      phone: null,
      qr: null,
      qrDataUrl: null,
      replyTargets: new Map(),
      lastError: null,
      lastState: null,
      loadingPercent: null,
      authenticatedAt: null,
      readyRetryCount,
      readyTimer: null,
      browserProbeTimer: null,
      browserDiagnosticsAttached: false,
      stopping: false,
      retrying: false,
      initialization: null,
    };
    this.sessions.set(sessionId, entry);
    this.profileClaims.set(profileKey, sessionId);
    this.#bindEvents(entry);
    this.#probeBrowserDiagnostics(entry);

    this.logger.info('whatsapp_initialize_started', {
      sessionId,
      profilePath,
      source,
    });
    entry.initialization = Promise.resolve()
      .then(() => {
        if (entry.stopping) return undefined;
        return client.initialize();
      })
      .then(() => {
        if (!this.#isCurrent(entry)) return;
        this.#attachBrowserDiagnostics(entry);
        this.logger.info('whatsapp_initialize_completed', {
          sessionId,
          status: entry.status,
          profilePath,
        });
      })
      .catch(async (error) => {
        if (!this.#isCurrent(entry) || entry.stopping) return;
        entry.status = 'DISCONNECTED';
        entry.lastError = error.message || String(error);
        this.logger.error('whatsapp_initialization_failed', {
          sessionId,
          error: entry.lastError,
          profilePath,
          locks: profileLockDetails(profilePath),
        });
        this.#forwardStatus(entry);
        await this.#destroyEntry(entry, 'initialize_failed').catch((destroyError) => {
          this.logger.error('whatsapp_failed_client_cleanup_failed', {
            sessionId,
            error: destroyError.message,
          });
        });
      });
    return this.snapshot(sessionId);
  }

  async reconnect(sessionId = this.config.defaultSessionId) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current) {
      await this.#destroyEntry(current, 'manual_reconnect');
      this.sessions.delete(sessionId);
    }
    return this.connect(sessionId, { source: 'manual_reconnect' });
  }

  async disconnect(sessionId = this.config.defaultSessionId) {
    this.validateSessionId(sessionId);
    const current = this.sessions.get(sessionId);
    if (current) await this.#destroyEntry(current, 'manual_disconnect');
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
    const { targetId, source } = await this.#resolveSendTarget(entry, digits);
    this.logger.info('whatsapp_message_send_started', {
      sessionId,
      targetId,
      messageLength: message.length,
      targetSource: source,
    });
    const chat = await entry.client.getChatById(targetId);
    const result = chat
      ? await chat.sendMessage(message)
      : await entry.client.sendMessage(targetId, message);
    this.logger.info('whatsapp_message_sent', {
      sessionId,
      targetId,
      phoneSuffix: digits.slice(-4),
      messageId: result?.id?._serialized || null,
    });
    return {
      messageId: result?.id?._serialized || null,
      status: 'SENT',
    };
  }

  async shutdown() {
    await Promise.all(
      [...this.sessions.values()].map((entry) =>
        this.#destroyEntry(entry, 'gateway_shutdown').catch((error) => {
          this.logger.error('whatsapp_shutdown_client_failed', {
            sessionId: entry.sessionId,
            error: error.message,
          });
        }),
      ),
    );
    this.sessions.clear();
    this.profileClaims.clear();
  }

  #bindEvents(entry) {
    const { client, sessionId } = entry;
    client.on('qr', (qr) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      entry.status = 'WAITING_QR';
      entry.qr = qr;
      entry.qrDataUrl = null;
      QRCode.toDataURL(qr)
        .then((dataUrl) => {
          if (this.#isCurrent(entry) && !entry.stopping && entry.qr === qr) {
            entry.qrDataUrl = dataUrl;
            this.#forwardStatus(entry);
          }
        })
        .catch((error) => {
          this.logger.warn('whatsapp_qr_render_failed', { sessionId, error: error.message });
        });
      this.logger.info('whatsapp_qr_received', {
        sessionId,
        profilePath: entry.profilePath,
      });
    });
    client.on('authenticated', () => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      entry.status = 'CONNECTING';
      entry.lastError = null;
      entry.authenticatedAt = new Date().toISOString();
      this.logger.info('whatsapp_authenticated', {
        sessionId,
        profilePath: entry.profilePath,
        readyTimeoutMs: this.config.readyTimeoutMs,
      });
      this.#startReadyWatchdog(entry);
    });
    client.on('loading_screen', (percent, message) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      entry.loadingPercent = percent;
      this.logger.info('whatsapp_loading_screen', { sessionId, percent, message });
    });
    client.on('change_state', (state) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      entry.lastState = String(state);
      this.logger.info('whatsapp_change_state', { sessionId, state: entry.lastState });
    });
    client.on('ready', () => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      this.#clearReadyTimer(entry);
      entry.status = 'CONNECTED';
      entry.qr = null;
      entry.qrDataUrl = null;
      entry.lastError = null;
      entry.phone = client.info?.wid?.user || null;
      this.logger.info('whatsapp_connected', {
        sessionId,
        phone: entry.phone,
        profilePath: entry.profilePath,
        readyRetryCount: entry.readyRetryCount,
      });
      this.#forwardStatus(entry);
    });
    client.on('auth_failure', (message) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      this.#clearReadyTimer(entry);
      entry.status = 'DISCONNECTED';
      entry.lastError = String(message);
      this.logger.error('whatsapp_authentication_failed', {
        sessionId,
        error: entry.lastError,
        profilePath: entry.profilePath,
      });
      this.#forwardStatus(entry);
    });
    client.on('disconnected', (reason) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
      this.#clearReadyTimer(entry);
      entry.status = 'DISCONNECTED';
      entry.lastError = String(reason);
      entry.phone = null;
      this.logger.warn('whatsapp_disconnected', {
        sessionId,
        reason: entry.lastError,
        profilePath: entry.profilePath,
      });
      this.#forwardStatus(entry);
    });
    client.on('message', (message) => {
      if (!this.#isCurrent(entry) || entry.stopping) return;
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

    let targetId = serializedId(message.from);
    if (typeof message.getChat === 'function') {
      try {
        const chat = await message.getChat();
        targetId = preferredChatId(chat?.id, targetId);
      } catch (error) {
        this.logger.warn('whatsapp_inbound_chat_lookup_failed', {
          sessionId: entry.sessionId,
          messageId: message.id?._serialized || null,
          error: error.message,
        });
      }
    }
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
    const normalizedPhone = String(phone).replace(/\D/g, '');
    if (targetId && normalizedPhone) {
      this.#rememberReplyTarget(entry, normalizedPhone, targetId);
    }
    const timestamp = Number(message.timestamp) || Math.floor(Date.now() / 1000);
    await this.backendService.forwardInbound({
      phone: normalizedPhone,
      message: message.body.trim(),
      channel: 'whatsapp',
      timestamp,
      message_id: message.id?._serialized || `${entry.sessionId}:${timestamp}:${phone}`,
      session_id: entry.sessionId,
    });
  }

  #rememberReplyTarget(entry, phone, targetId) {
    entry.replyTargets.delete(phone);
    entry.replyTargets.set(phone, targetId);
    if (entry.replyTargets.size > 10_000) {
      entry.replyTargets.delete(entry.replyTargets.keys().next().value);
    }
    this.logger.info('whatsapp_reply_target_saved', {
      sessionId: entry.sessionId,
      targetId,
      source: 'inbound_chat',
    });
  }

  async #resolveSendTarget(entry, digits) {
    const remembered = entry.replyTargets.get(digits);
    if (remembered) {
      return { targetId: remembered, source: 'inbound_chat' };
    }

    const numberId = await entry.client.getNumberId(digits);
    const phoneId = serializedId(numberId);
    if (!phoneId) {
      const error = new Error(`No WhatsApp user found for phone ending ${digits.slice(-4)}`);
      error.statusCode = 422;
      throw error;
    }

    if (typeof entry.client.getContactLidAndPhone === 'function') {
      const identities = await entry.client.getContactLidAndPhone([phoneId]);
      const identity = Array.isArray(identities) ? identities[0] : null;
      const lid = serializedId(identity?.lid);
      const resolvedPhoneId = serializedId(identity?.pn);
      if (lid) return { targetId: lid, source: 'lid_lookup' };
      if (resolvedPhoneId) return { targetId: resolvedPhoneId, source: 'phone_lookup' };
    }

    return { targetId: phoneId, source: 'number_lookup' };
  }

  #startReadyWatchdog(entry) {
    this.#clearReadyTimer(entry);
    entry.readyTimer = setTimeout(() => {
      this.#handleReadyTimeout(entry).catch((error) => {
        this.logger.error('whatsapp_ready_recovery_failed', {
          sessionId: entry.sessionId,
          error: error.message,
        });
      });
    }, this.config.readyTimeoutMs);
    entry.readyTimer.unref?.();
  }

  async #handleReadyTimeout(entry) {
    if (!this.#isCurrent(entry) || entry.stopping || entry.status === 'CONNECTED') return;
    const diagnostics = await this.#collectDiagnostics(entry);
    this.logger.error('whatsapp_ready_timeout', {
      sessionId: entry.sessionId,
      authenticatedAt: entry.authenticatedAt,
      loadingPercent: entry.loadingPercent,
      lastState: entry.lastState,
      readyRetryCount: entry.readyRetryCount,
      diagnostics,
    });

    if (entry.readyRetryCount >= this.config.readyRetryLimit) {
      entry.status = 'DISCONNECTED';
      entry.lastError = `authenticated but ready was not emitted within ${this.config.readyTimeoutMs}ms`;
      this.#forwardStatus(entry);
      return;
    }

    entry.retrying = true;
    this.logger.warn('whatsapp_ready_retry_started', {
      sessionId: entry.sessionId,
      nextRetry: entry.readyRetryCount + 1,
      profilePath: entry.profilePath,
      action: 'restart_client_with_existing_localauth_profile',
    });
    const { sessionId, readyRetryCount } = entry;
    await this.#destroyEntry(entry, 'ready_timeout');
    if (this.sessions.get(sessionId) === entry) this.sessions.delete(sessionId);
    await delay(250);
    await this.connect(sessionId, {
      source: 'ready_timeout_retry',
      readyRetryCount: readyRetryCount + 1,
    });
  }

  async #destroyEntry(entry, reason) {
    if (entry.stopping) return;
    entry.stopping = true;
    this.#clearReadyTimer(entry);
    clearInterval(entry.browserProbeTimer);
    const browserProcess = entry.client.pupBrowser?.process?.();
    const browserPid = browserProcess?.pid || null;
    this.logger.info('whatsapp_session_destroy_started', {
      sessionId: entry.sessionId,
      reason,
      browserPid,
      profilePath: entry.profilePath,
    });

    try {
      await withTimeout(
        Promise.resolve(entry.client.destroy()),
        this.config.browserShutdownTimeoutMs,
        `Chromium did not stop within ${this.config.browserShutdownTimeoutMs}ms`,
      );
    } catch (error) {
      if (browserPid) {
        this.logger.warn('whatsapp_browser_force_kill', {
          sessionId: entry.sessionId,
          browserPid,
          reason: error.message,
        });
        try {
          process.kill(browserPid, 'SIGKILL');
        } catch (killError) {
          if (killError.code !== 'ESRCH') throw killError;
        }
      } else {
        throw error;
      }
    }

    const remainingLocks = await waitForProfileUnlock(
      entry.profilePath,
      this.config.profileUnlockTimeoutMs,
    );
    if (remainingLocks.length) {
      const error = new Error(
        `Chromium profile lock was not released for session '${entry.sessionId}'`,
      );
      error.statusCode = 409;
      this.logger.error('whatsapp_profile_lock_not_released', {
        sessionId: entry.sessionId,
        profilePath: entry.profilePath,
        locks: remainingLocks,
      });
      throw error;
    }
    this.profileClaims.delete(entry.profilePath.toLowerCase());
    this.logger.info('whatsapp_session_destroyed', {
      sessionId: entry.sessionId,
      reason,
      profilePath: entry.profilePath,
    });
  }

  #probeBrowserDiagnostics(entry) {
    let attempts = 0;
    entry.browserProbeTimer = setInterval(() => {
      attempts += 1;
      if (!this.#isCurrent(entry) || entry.stopping || this.#attachBrowserDiagnostics(entry)) {
        clearInterval(entry.browserProbeTimer);
      } else if (attempts >= 300) {
        clearInterval(entry.browserProbeTimer);
      }
    }, 100);
    entry.browserProbeTimer.unref?.();
  }

  #attachBrowserDiagnostics(entry) {
    if (entry.browserDiagnosticsAttached) return true;
    const page = entry.client.pupPage;
    const browser = entry.client.pupBrowser;
    if (!page || !browser) return false;
    entry.browserDiagnosticsAttached = true;
    const browserPid = browser.process?.()?.pid || null;
    this.logger.info('whatsapp_browser_started', {
      sessionId: entry.sessionId,
      browserPid,
      profilePath: entry.profilePath,
    });
    Promise.resolve(browser.version?.())
      .then((version) => {
        if (version) {
          this.logger.info('whatsapp_browser_version', { sessionId: entry.sessionId, version });
        }
      })
      .catch((error) => {
        this.logger.warn('whatsapp_browser_version_failed', {
          sessionId: entry.sessionId,
          error: error.message,
        });
      });
    page.on?.('console', (message) => {
      const type = message.type?.() || 'log';
      if (!['error', 'warning', 'warn'].includes(type)) return;
      this.logger.warn('whatsapp_browser_console', {
        sessionId: entry.sessionId,
        type,
        text: message.text?.() || String(message),
      });
    });
    page.on?.('pageerror', (error) => {
      this.logger.error('whatsapp_browser_page_error', {
        sessionId: entry.sessionId,
        error: error.message || String(error),
        stack: error.stack || null,
      });
    });
    page.on?.('error', (error) => {
      this.logger.error('whatsapp_browser_page_crashed', {
        sessionId: entry.sessionId,
        error: error.message || String(error),
      });
    });
    browser.on?.('disconnected', () => {
      if (entry.stopping) return;
      this.logger.warn('whatsapp_browser_disconnected', {
        sessionId: entry.sessionId,
        browserPid,
      });
    });
    return true;
  }

  async #collectDiagnostics(entry) {
    this.#attachBrowserDiagnostics(entry);
    const page = entry.client.pupPage;
    let pageState = null;
    if (page && !page.isClosed?.()) {
      try {
        pageState = await withTimeout(
          page.evaluate(() => ({
            url: window.location.href,
            title: document.title,
            debugVersion: window.Debug?.VERSION || null,
            socketState: window.require?.('WAWebSocketModel')?.Socket?.state || null,
            hasWWebJS: typeof window.WWebJS !== 'undefined',
            hasStore: typeof window.Store !== 'undefined',
          })),
          5_000,
          'browser diagnostics timed out',
        );
      } catch (error) {
        pageState = { error: error.message || String(error) };
      }
    }
    let clientState = null;
    try {
      clientState = entry.client.getState
        ? await withTimeout(entry.client.getState(), 5_000, 'getState timed out')
        : null;
    } catch (error) {
      clientState = `error: ${error.message || String(error)}`;
    }
    return {
      clientState,
      pageState,
      browserPid: entry.client.pupBrowser?.process?.()?.pid || null,
      browserConnected: entry.client.pupBrowser?.isConnected?.() ?? null,
      profilePath: entry.profilePath,
      profileLocks: profileLockDetails(entry.profilePath),
    };
  }

  #clearReadyTimer(entry) {
    clearTimeout(entry.readyTimer);
    entry.readyTimer = null;
  }

  #isCurrent(entry) {
    return this.sessions.get(entry.sessionId) === entry;
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
