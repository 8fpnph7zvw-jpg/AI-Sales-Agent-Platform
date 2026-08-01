const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { SessionManager } = require('../src/services/session-manager');

class FakeClient extends EventEmitter {
  constructor() {
    super();
    this.info = { wid: { user: '15550001111' } };
    this.destroyed = false;
    this.chatLookups = [];
    this.sendAttempts = [];
    this.chatSendErrors = new Map();
    this.directSendErrors = new Map();
  }

  async initialize() {}

  async getState() {
    return this.state || 'CONNECTED';
  }

  async destroy() {
    this.destroyed = true;
  }

  async getNumberId(number) {
    this.numberLookup = number;
    if (this.numberIdResults?.length) return this.numberIdResults.shift();
    if (Object.hasOwn(this, 'numberIdResult')) return this.numberIdResult;
    return { _serialized: `${number}@c.us` };
  }

  async getContactLidAndPhone(userIds) {
    this.identityLookup = userIds;
    return [{ lid: `${userIds[0].split('@')[0]}@lid`, pn: userIds[0] }];
  }

  async getChatById(chatId) {
    this.chatLookup = chatId;
    this.chatLookups.push(chatId);
    if (this.chatLookupErrors?.has(chatId)) throw this.chatLookupErrors.get(chatId);
    if (this.missingChats?.has(chatId)) return undefined;
    return {
      sendMessage: async (message) => {
        this.sendAttempts.push({ method: 'chat', chatId, message });
        if (this.chatSendErrors.has(chatId)) throw this.chatSendErrors.get(chatId);
        this.sent = { chatId, message };
        return { id: { _serialized: 'outbound-1' } };
      },
    };
  }

  async sendMessage(chatId, message) {
    this.sendAttempts.push({ method: 'client', chatId, message });
    if (this.directSendErrors.has(chatId)) throw this.directSendErrors.get(chatId);
    this.sent = { chatId, message };
    return { id: { _serialized: 'outbound-1' } };
  }
}

async function waitFor(predicate, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error('Timed out waiting for condition');
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function fixture() {
  const client = new FakeClient();
  const forwarded = [];
  const logs = [];
  const statuses = [];
  const manager = new SessionManager(
    {
      defaultSessionId: 'customer001',
      acceptGroupMessages: false,
    },
    {
      async forwardInbound(payload) {
        forwarded.push(payload);
      },
      async forwardStatus(payload) {
        statuses.push(payload);
      },
    },
    {
      info(message, fields) { logs.push({ message, fields }); },
      warn() {},
      error(message, fields) { logs.push({ message, fields }); },
    },
    () => client,
  );
  return { client, forwarded, logs, manager, statuses };
}

test('connect tracks LocalAuth lifecycle and resolves a phone ID before LID', async () => {
  const { client, logs, manager, statuses } = fixture();
  assert.equal((await manager.connect()).status, 'CONNECTING');

  client.emit('ready');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(manager.snapshot('customer001'), {
    sessionId: 'customer001',
    status: 'CONNECTED',
    phone: '15550001111',
    lastError: null,
  });

  const result = await manager.send({
    phone: '+1 (555) 000-2222',
    message: 'AI reply',
  });
  assert.deepEqual(result, { messageId: 'outbound-1', status: 'SENT' });
  assert.deepEqual(client.sent, {
    chatId: '15550002222@c.us',
    message: 'AI reply',
  });
  assert.equal(client.numberLookup, '15550002222');
  assert.equal(client.chatLookup, '15550002222@c.us');
  assert.deepEqual(
    logs.find((item) => item.message === 'whatsapp_message_send_started').fields,
    {
      sessionId: 'customer001',
      targetId: '15550002222@c.us',
      messageLength: 8,
      targetSource: 'phoneId',
    },
  );
  assert.deepEqual(statuses, [
    {
      session_id: 'customer001',
      status: 'CONNECTED',
      phone: '15550001111',
      last_error: null,
      data_url: null,
    },
  ]);
});

test('automatic reply saves and uses the inbound phone chat ID before LID', async () => {
  const { client, logs, manager } = fixture();
  await manager.connect();
  client.emit('ready');
  client.emit('message', {
    fromMe: false,
    from: '987654321012345@lid',
    body: 'Need help',
    timestamp: 1785376800,
    id: {
      _serialized: 'lid-inbound-1',
      remote: '18319822378@c.us',
    },
    async getChat() {
      return { id: { _serialized: '15550004444@c.us' } };
    },
    async getContact() {
      return { number: '15550004444' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  await manager.send({ phone: '15550004444', message: 'Dify reply' });

  assert.equal(client.numberLookup, undefined);
  assert.equal(client.chatLookup, '18319822378@c.us');
  assert.deepEqual(client.sent, {
    chatId: '18319822378@c.us',
    message: 'Dify reply',
  });
  assert.deepEqual(
    logs.find((item) => item.message === 'whatsapp_reply_target_saved').fields,
    {
      sessionId: 'customer001',
      phone: '15550004444',
      phoneId: '18319822378@c.us',
      chatId: '18319822378@c.us',
      lid: '987654321012345@lid',
    },
  );
});

test('automatic reply can send when the inbound conversation only exposes a LID', async () => {
  const { client, manager } = fixture();
  client.numberIdResult = null;
  await manager.connect();
  client.emit('ready');
  client.emit('message', {
    fromMe: false,
    from: '198651548852233@lid',
    body: 'Only LID is available',
    timestamp: 1785376800,
    id: { _serialized: 'lid-only-1', remote: '198651548852233@lid' },
    async getChat() {
      return { id: { _serialized: '198651548852233@lid' } };
    },
    async getContact() {
      return { number: '18319822378' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  await manager.send({ phone: '18319822378', message: 'LID reply' });

  assert.deepEqual(client.chatLookups, ['198651548852233@lid']);
  assert.deepEqual(client.sent, {
    chatId: '198651548852233@lid',
    message: 'LID reply',
  });
});

test('failed LID send retries number resolution and falls back to phoneId', async () => {
  const { client, manager } = fixture();
  const lid = '198651548852233@lid';
  const phoneId = '18319822378@c.us';
  client.numberIdResults = [null, { _serialized: phoneId }];
  client.chatLookupErrors = new Map([[lid, new Error('LID chat lookup failed')]]);
  client.directSendErrors.set(lid, new Error('LID direct send failed'));
  await manager.connect();
  client.emit('ready');
  client.emit('message', {
    fromMe: false,
    from: lid,
    body: 'Retry with phone ID',
    timestamp: 1785376800,
    id: { _serialized: 'lid-phone-fallback-1', remote: lid },
    async getChat() {
      return { id: { _serialized: lid } };
    },
    async getContact() {
      return { number: '18319822378' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  await manager.send({ phone: '18319822378', message: 'Phone fallback reply' });

  assert.deepEqual(client.chatLookups, [lid, phoneId]);
  assert.deepEqual(client.sent, {
    chatId: phoneId,
    message: 'Phone fallback reply',
  });
});

test('failed phone chat lookup and direct send fall back to the cached LID', async () => {
  const { client, logs, manager } = fixture();
  client.chatLookupErrors = new Map([
    ['18319822378@c.us', new Error('phone chat is not cached')],
  ]);
  client.directSendErrors.set('18319822378@c.us', new Error('No LID for user'));
  await manager.connect();
  client.emit('ready');
  client.emit('message', {
    fromMe: false,
    from: '198651548852233@lid',
    body: 'Need fallback',
    timestamp: 1785376800,
    id: { _serialized: 'fallback-1', remote: '18319822378@c.us' },
    async getChat() {
      return { id: { _serialized: '18319822378@c.us' } };
    },
    async getContact() {
      return { number: '18319822378' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  await manager.send({ phone: '18319822378', message: 'Fallback reply' });

  assert.deepEqual(client.chatLookups, ['18319822378@c.us', '198651548852233@lid']);
  assert.deepEqual(client.sent, {
    chatId: '198651548852233@lid',
    message: 'Fallback reply',
  });
  assert.deepEqual(
    logs
      .filter((item) => item.message === 'whatsapp_message_send_attempt')
      .map((item) => item.fields.targetId),
    ['18319822378@c.us', '198651548852233@lid'],
  );
  assert.equal(
    logs.find((item) => item.message === 'whatsapp_message_sent').fields.finalTargetId,
    '198651548852233@lid',
  );
});

test('send failure is logged only after every phone and LID target fails', async () => {
  const { client, logs, manager } = fixture();
  const phoneId = '18319822378@c.us';
  const lid = '198651548852233@lid';
  const resolvedLid = '18319822378@lid';
  client.chatLookupErrors = new Map([
    [phoneId, new Error('phone chat lookup failed')],
    [lid, new Error('LID chat lookup failed')],
    [resolvedLid, new Error('resolved LID chat lookup failed')],
  ]);
  client.directSendErrors.set(phoneId, new Error('phone direct send failed'));
  client.directSendErrors.set(lid, new Error('LID direct send failed'));
  client.directSendErrors.set(resolvedLid, new Error('resolved LID direct send failed'));
  await manager.connect();
  client.emit('ready');
  client.emit('message', {
    fromMe: false,
    from: lid,
    body: 'All targets fail',
    timestamp: 1785376800,
    id: { _serialized: 'all-fail-1', remote: phoneId },
    async getChat() {
      return { id: { _serialized: phoneId } };
    },
    async getContact() {
      return { number: '18319822378' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  await assert.rejects(
    manager.send({ phone: '18319822378', message: 'Cannot send' }),
    /Unable to send WhatsApp message using targets/,
  );

  const failure = logs.find((item) => item.message === 'whatsapp_message_send_failed');
  assert.deepEqual(failure.fields.attemptedTargetIds, [phoneId, lid, resolvedLid]);
  assert.deepEqual(
    failure.fields.errors.map(({ targetId, operation }) => ({ targetId, operation })),
    [
      { targetId: phoneId, operation: 'getChatById' },
      { targetId: phoneId, operation: 'client.sendMessage' },
      { targetId: lid, operation: 'getChatById' },
      { targetId: lid, operation: 'client.sendMessage' },
      { targetId: resolvedLid, operation: 'getChatById' },
      { targetId: resolvedLid, operation: 'client.sendMessage' },
    ],
  );
});

test('inbound customer message is forwarded with channel metadata', async () => {
  const { client, forwarded, manager } = fixture();
  await manager.connect();
  client.emit('message', {
    fromMe: false,
    from: '15550003333@c.us',
    body: 'Need a quote',
    timestamp: 1785376800,
    id: { _serialized: 'inbound-1' },
    async getContact() {
      return { number: '15550003333' };
    },
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(forwarded, [
    {
      phone: '15550003333',
      message: 'Need a quote',
      channel: 'whatsapp',
      timestamp: 1785376800,
      message_id: 'inbound-1',
      session_id: 'customer001',
    },
  ]);
});

test('reconnect replaces the runtime client and disconnect removes it', async () => {
  const clients = [];
  const manager = new SessionManager(
    { defaultSessionId: 'customer001', acceptGroupMessages: false },
    { async forwardInbound() {}, async forwardStatus() {} },
    { info() {}, warn() {}, error() {} },
    () => {
      const client = new FakeClient();
      clients.push(client);
      return client;
    },
  );

  await manager.connect('customer001');
  clients[0].emit('ready');
  assert.equal(manager.snapshot('customer001').status, 'CONNECTED');

  assert.equal((await manager.reconnect('customer001')).status, 'CONNECTING');
  assert.equal(clients[0].destroyed, true);
  assert.equal(clients.length, 2);

  assert.equal((await manager.disconnect('customer001')).status, 'DISCONNECTED');
  assert.equal(clients[1].destroyed, true);
});

test('authenticated session is restarted with the same profile when ready times out', async (t) => {
  const sessionsPath = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-ready-timeout-'));
  t.after(() => fs.rmSync(sessionsPath, { recursive: true, force: true }));
  const clients = [];
  const logs = [];
  const manager = new SessionManager(
    {
      defaultSessionId: 'formal-session',
      sessionsPath,
      acceptGroupMessages: false,
      readyTimeoutMs: 20,
      readyRetryLimit: 1,
    },
    { async forwardInbound() {}, async forwardStatus() {} },
    {
      info(message, fields) { logs.push({ message, fields }); },
      warn(message, fields) { logs.push({ message, fields }); },
      error(message, fields) { logs.push({ message, fields }); },
    },
    () => {
      const client = new FakeClient();
      clients.push(client);
      return client;
    },
  );

  await manager.connect('formal-session');
  clients[0].emit('authenticated');
  await waitFor(() => clients.length === 2);

  assert.equal(clients[0].destroyed, true);
  assert.equal(manager.snapshot('formal-session').status, 'CONNECTING');
  assert.ok(logs.some((item) => item.message === 'whatsapp_ready_timeout'));
  assert.ok(logs.some((item) => item.message === 'whatsapp_ready_retry_started'));

  clients[1].emit('authenticated');
  clients[1].emit('ready');
  assert.equal(manager.snapshot('formal-session').status, 'CONNECTED');
  await manager.shutdown();
});

test('startup restores formal sessions but skips the historical default session', async (t) => {
  const sessionsPath = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-session-restore-'));
  t.after(() => fs.rmSync(sessionsPath, { recursive: true, force: true }));
  fs.mkdirSync(path.join(sessionsPath, 'session-customer001'));
  fs.writeFileSync(path.join(sessionsPath, 'session-customer001', 'SingletonLock'), 'legacy');
  fs.mkdirSync(path.join(sessionsPath, 'session-01KYRNYVXKJ4Y03FJSY4G4T7FC'));
  const clients = [];
  const logs = [];
  const manager = new SessionManager(
    {
      defaultSessionId: 'customer001',
      sessionsPath,
      acceptGroupMessages: false,
      autoRestoreSessions: true,
      autoRestoreDefaultSession: false,
    },
    { async forwardInbound() {}, async forwardStatus() {} },
    {
      info(message, fields) { logs.push({ message, fields }); },
      warn() {},
      error() {},
    },
    ({ sessionId }) => {
      clients.push(sessionId);
      return new FakeClient();
    },
  );

  await manager.restoreConfiguredSessions();

  assert.deepEqual(clients, ['01KYRNYVXKJ4Y03FJSY4G4T7FC']);
  const inventory = logs.find((item) => item.message === 'whatsapp_session_inventory');
  assert.equal(inventory.fields.legacyDefaultSessionPresent, true);
  assert.deepEqual(
    inventory.fields.sessions.map(({ sessionId, willRestore }) => ({ sessionId, willRestore })),
    [
      { sessionId: '01KYRNYVXKJ4Y03FJSY4G4T7FC', willRestore: true },
      { sessionId: 'customer001', willRestore: false },
    ],
  );
  assert.equal(
    inventory.fields.sessions.find((item) => item.sessionId === 'customer001').status,
    'profile_locked',
  );
  await manager.shutdown();
});

test('case variants cannot claim the same LocalAuth profile concurrently', async (t) => {
  const sessionsPath = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-profile-claim-'));
  t.after(() => fs.rmSync(sessionsPath, { recursive: true, force: true }));
  const manager = new SessionManager(
    { defaultSessionId: 'customer001', sessionsPath, acceptGroupMessages: false },
    { async forwardInbound() {}, async forwardStatus() {} },
    { info() {}, warn() {}, error() {} },
    () => new FakeClient(),
  );

  await manager.connect('FormalSession');
  await assert.rejects(
    manager.connect('formalsession'),
    /already claimed by session 'FormalSession'/,
  );
  await manager.shutdown();
});
