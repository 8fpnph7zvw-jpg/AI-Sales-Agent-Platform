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
  }

  async initialize() {}

  async getState() {
    return this.state || 'CONNECTED';
  }

  async destroy() {
    this.destroyed = true;
  }

  async sendMessage(chatId, message) {
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
    { info() {}, warn() {}, error() {} },
    () => client,
  );
  return { client, forwarded, manager, statuses };
}

test('connect tracks LocalAuth lifecycle and sends messages', async () => {
  const { client, manager, statuses } = fixture();
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
