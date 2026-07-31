const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const test = require('node:test');

const { SessionManager } = require('../src/services/session-manager');

class FakeClient extends EventEmitter {
  constructor() {
    super();
    this.info = { wid: { user: '15550001111' } };
    this.destroyed = false;
  }

  async initialize() {}

  async destroy() {
    this.destroyed = true;
  }

  async sendMessage(chatId, message) {
    this.sent = { chatId, message };
    return { id: { _serialized: 'outbound-1' } };
  }
}

function fixture() {
  const client = new FakeClient();
  const forwarded = [];
  const manager = new SessionManager(
    {
      defaultSessionId: 'customer001',
      acceptGroupMessages: false,
    },
    {
      async forwardInbound(payload) {
        forwarded.push(payload);
      },
    },
    { info() {}, warn() {}, error() {} },
    () => client,
  );
  return { client, forwarded, manager };
}

test('connect tracks LocalAuth lifecycle and sends messages', async () => {
  const { client, manager } = fixture();
  assert.equal((await manager.connect()).status, 'CONNECTING');

  client.emit('ready');
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
