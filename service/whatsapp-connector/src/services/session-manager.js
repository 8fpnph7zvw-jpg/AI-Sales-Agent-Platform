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
  if (value?._serialized) return value._serialized;
  if (value?.id?._serialized) return value.id._serialized;
  if (value?.user && value?.server) return `${value.user}@${value.server}`;
  return null;
}

function isLidId(value) {
  return typeof value === 'string' && value.endsWith('@lid');
}

function isPhoneId(value) {
  return typeof value === 'string' && /@(c\.us|s\.whatsapp\.net)$/.test(value);
}

function normalizedPhone(value) {
  const digits = String(value || '').replace(/\D/g, '');
  return digits.length >= 5 && digits.length <= 20 ? digits : null;
}

function phoneFromId(value) {
  const id = serializedId(value);
  if (!isPhoneId(id)) return null;
  return normalizedPhone(id.split('@')[0]);
}

function normalizedReplyTarget(value) {
  if (!value) return { phoneId: null, chatId: null, fromId: null, lid: null };
  if (typeof value === 'string') {
    return {
      phoneId: isPhoneId(value) ? value : null,
      chatId: isLidId(value) ? null : value,
      fromId: value,
      lid: isLidId(value) ? value : null,
    };
  }
  return {
    phoneId: serializedId(value.phoneId),
    chatId: serializedId(value.chatId),
    fromId: serializedId(value.fromId),
    lid: serializedId(value.lid),
  };
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
    const { candidates } = await this.#resolveSendTarget(entry, digits);
    const primaryTarget = candidates[0];
    this.logger.info('whatsapp_message_send_started', {
      sessionId,
      targetId: primaryTarget.targetId,
      messageLength: message.length,
      targetSource: primaryTarget.targetType,
    });
    const failures = [];
    let latePhoneLookupAttempted = false;
    for (let index = 0; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      const { targetId, targetType } = candidate;
      this.logger.info('whatsapp_message_send_attempt', {
        sessionId,
        targetId,
        targetType,
        messageLength: message.length,
      });

      let chat;
      try {
        chat = await entry.client.getChatById(targetId);
      } catch (error) {
        failures.push({ targetId, operation: 'getChatById', error: error.message || String(error) });
      }

      if (chat) {
        try {
          const result = await chat.sendMessage(message);
          this.#logMessageSent(entry, digits, targetId, result);
          return { messageId: result?.id?._serialized || null, status: 'SENT' };
        } catch (error) {
          failures.push({ targetId, operation: 'chat.sendMessage', error: error.message || String(error) });
          continue;
        }
      }

      try {
        const result = await entry.client.sendMessage(targetId, message);
        this.#logMessageSent(entry, digits, targetId, result);
        return { messageId: result?.id?._serialized || null, status: 'SENT' };
      } catch (error) {
        failures.push({ targetId, operation: 'client.sendMessage', error: error.message || String(error) });
      }

      const onlyLidCandidates = candidates.every((item) => isLidId(item.targetId));
      if (
        isLidId(targetId)
        && index === candidates.length - 1
        && onlyLidCandidates
        && !latePhoneLookupAttempted
      ) {
        latePhoneLookupAttempted = true;
        try {
          const fallbackPhoneId = serializedId(await entry.client.getNumberId(digits));
          if (fallbackPhoneId && !isLidId(fallbackPhoneId)) {
            candidates.push({ targetId: fallbackPhoneId, targetType: 'phoneId' });
          }
        } catch (error) {
          this.logger.warn('whatsapp_phone_fallback_lookup_failed', {
            sessionId,
            phoneSuffix: digits.slice(-4),
            error: error.message || String(error),
          });
        }
      }
    }

    const attemptedTargetIds = candidates.map((candidate) => candidate.targetId);
    this.logger.error('whatsapp_message_send_failed', {
      sessionId,
      attemptedTargetIds,
      errors: failures,
    });
    const error = new Error(
      `Unable to send WhatsApp message using targets: ${attemptedTargetIds.join(', ')}`,
    );
    error.statusCode = 500;
    throw error;
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

    const remoteId = serializedId(message.id?.remote);
    const fromId = serializedId(message.from);
    let resolvedChatId = null;
    if (typeof message.getChat === 'function') {
      try {
        const chat = await message.getChat();
        resolvedChatId = serializedId(chat?.id);
      } catch (error) {
        this.logger.warn('whatsapp_inbound_chat_lookup_failed', {
          sessionId: entry.sessionId,
          messageId: message.id?._serialized || null,
          error: error.message,
        });
      }
    }
    const inboundIds = [remoteId, fromId, resolvedChatId].filter(Boolean);
    let phoneId = inboundIds.find(isPhoneId) || null;
    const chatId = inboundIds.find((id) => !isLidId(id)) || null;
    let lid = inboundIds.find(isLidId) || null;
    let contact = null;
    try {
      contact = await message.getContact();
    } catch (error) {
      this.logger.warn('whatsapp_contact_lookup_failed', {
        sessionId: entry.sessionId,
        error: error.message,
      });
    }

    const contactId = serializedId(contact?.id);
    const contactIdPhone = phoneFromId(contact?.id);
    const contactIdUser = normalizedPhone(contact?.id?.user);
    if (contactIdPhone) phoneId = contactId;
    if (isLidId(contactId)) lid = contactId;

    const contactNumber = normalizedPhone(contact?.number);
    const knownLidUser = normalizedPhone((lid || '').split('@')[0]) || contactIdUser;
    const contactNumberIsLidUser = Boolean(
      contactNumber && knownLidUser && contactNumber === knownLidUser,
    );
    let customerPhone = contactNumberIsLidUser ? null : contactNumber;
    let phoneSource = customerPhone ? 'contact.number' : null;

    if (!customerPhone && lid && typeof entry.client.getContactLidAndPhone === 'function') {
      const identityLookupId = lid;
      if (identityLookupId) {
        try {
          const identities = await entry.client.getContactLidAndPhone([identityLookupId]);
          const identity = Array.isArray(identities) ? identities[0] : null;
          const mappedPhoneId = serializedId(identity?.pn);
          const mappedLid = serializedId(identity?.lid);
          customerPhone = phoneFromId(mappedPhoneId);
          if (customerPhone) phoneSource = 'getContactLidAndPhone';
          if (mappedPhoneId && isPhoneId(mappedPhoneId)) phoneId = mappedPhoneId;
          if (mappedLid && isLidId(mappedLid)) lid = mappedLid;
        } catch (error) {
          this.logger.warn('whatsapp_inbound_lid_phone_lookup_failed', {
            sessionId: entry.sessionId,
            lid,
            error: error.message || String(error),
          });
        }
      }
    }

    if (!customerPhone) {
      customerPhone = phoneFromId(fromId);
      if (customerPhone) phoneSource = 'message.from';
    }

    if (!customerPhone) {
      const error = new Error('Unable to resolve the real customer phone from WhatsApp contact');
      this.logger.error('whatsapp_inbound_phone_resolution_failed', {
        sessionId: entry.sessionId,
        messageId: message.id?._serialized || null,
        contactId,
        lid,
      });
      throw error;
    }

    this.logger.info('whatsapp_phone_resolved', {
      sessionId: entry.sessionId,
      originalId: fromId || remoteId || contactId || null,
      resolvedPhone: customerPhone,
      source: phoneSource,
    });

    if (chatId || fromId || phoneId || lid) {
      this.#rememberReplyTarget(entry, customerPhone, {
        phoneId,
        chatId,
        fromId,
        lid,
      });
    }
    const timestamp = Number(message.timestamp) || Math.floor(Date.now() / 1000);
    await this.backendService.forwardInbound({
      phone: customerPhone,
      whatsapp_lid: lid,
      message: message.body.trim(),
      channel: 'whatsapp',
      timestamp,
      message_id: message.id?._serialized || `${entry.sessionId}:${timestamp}:${customerPhone}`,
      session_id: entry.sessionId,
    });
  }

  #rememberReplyTarget(entry, phone, target) {
    const previous = normalizedReplyTarget(entry.replyTargets.get(phone));
    const incoming = normalizedReplyTarget(target);
    const saved = {
      phoneId: incoming.phoneId || previous.phoneId,
      chatId: incoming.chatId || previous.chatId,
      fromId: incoming.fromId || previous.fromId,
      lid: incoming.lid || previous.lid,
    };
    entry.replyTargets.delete(phone);
    entry.replyTargets.set(phone, saved);
    if (entry.replyTargets.size > 10_000) {
      entry.replyTargets.delete(entry.replyTargets.keys().next().value);
    }
    this.logger.info('whatsapp_reply_target_saved', {
      sessionId: entry.sessionId,
      phone,
      phoneId: saved.phoneId,
      chatId: saved.chatId,
      lid: saved.lid,
    });
  }

  async #resolveSendTarget(entry, digits) {
    const remembered = normalizedReplyTarget(entry.replyTargets.get(digits));
    let resolvedPhoneId = remembered.phoneId;
    let resolvedLid = remembered.lid;

    if (!resolvedPhoneId) {
      try {
        const numberLookupId = serializedId(await entry.client.getNumberId(digits));
        if (isLidId(numberLookupId)) resolvedLid = numberLookupId;
        else resolvedPhoneId = numberLookupId;
      } catch (error) {
        this.logger.warn('whatsapp_number_id_lookup_failed', {
          sessionId: entry.sessionId,
          phoneSuffix: digits.slice(-4),
          error: error.message || String(error),
        });
      }
    }

    if (resolvedPhoneId && typeof entry.client.getContactLidAndPhone === 'function') {
      try {
        const identities = await entry.client.getContactLidAndPhone([resolvedPhoneId]);
        const identity = Array.isArray(identities) ? identities[0] : null;
        const identityPhoneId = serializedId(identity?.pn);
        if (isLidId(identityPhoneId)) resolvedLid = identityPhoneId;
        else resolvedPhoneId = identityPhoneId || resolvedPhoneId;
        resolvedLid = serializedId(identity?.lid) || resolvedLid;
      } catch (error) {
        this.logger.warn('whatsapp_lid_lookup_failed', {
          sessionId: entry.sessionId,
          phoneId: resolvedPhoneId,
          error: error.message || String(error),
        });
      }
    }

    const candidates = [];
    const seen = new Set();
    const addCandidate = (targetId, targetType) => {
      if (!targetId || seen.has(targetId)) return;
      seen.add(targetId);
      candidates.push({ targetId, targetType });
    };

    if (!isLidId(remembered.chatId)) addCandidate(remembered.chatId, 'chatId');
    if (!isLidId(remembered.fromId)) addCandidate(remembered.fromId, 'fromId');
    if (!isLidId(remembered.phoneId)) addCandidate(remembered.phoneId, 'phoneId');
    if (!isLidId(resolvedPhoneId)) addCandidate(resolvedPhoneId, 'phoneId');
    addCandidate(remembered.lid, 'lid');
    if (isLidId(remembered.fromId)) addCandidate(remembered.fromId, 'lid');
    if (isLidId(remembered.chatId)) addCandidate(remembered.chatId, 'lid');
    addCandidate(resolvedLid, 'lid');

    if (!candidates.length) {
      const error = new Error(`No WhatsApp target found for phone ending ${digits.slice(-4)}`);
      error.statusCode = 422;
      throw error;
    }
    return { candidates };
  }

  #logMessageSent(entry, digits, finalTargetId, result) {
    this.logger.info('whatsapp_message_sent', {
      sessionId: entry.sessionId,
      finalTargetId,
      phoneSuffix: digits.slice(-4),
      messageId: result?.id?._serialized || null,
    });
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
