const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { createWhatsAppClient } = require('../src/client');

test('LocalAuth maps each clientId to its own session directory', async (t) => {
  const sessionsPath = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-localauth-'));
  t.after(() => fs.rmSync(sessionsPath, { recursive: true, force: true }));
  const client = createWhatsAppClient({
    sessionId: '01KYRNYVXKJ4Y03FJSY4G4T7FC',
    config: {
      sessionsPath,
      puppeteerNoSandbox: false,
      puppeteerHeadless: true,
      puppeteerExecutablePath: undefined,
    },
  });

  assert.equal(client.authStrategy.clientId, '01KYRNYVXKJ4Y03FJSY4G4T7FC');
  assert.equal(client.authStrategy.dataPath, sessionsPath);
  assert.deepEqual(client.options.webVersionCache, {
    type: 'local',
    path: path.join(sessionsPath, '.wwebjs_cache'),
  });
  await client.authStrategy.beforeBrowserInitialized();
  assert.equal(
    client.options.puppeteer.userDataDir,
    path.join(sessionsPath, 'session-01KYRNYVXKJ4Y03FJSY4G4T7FC'),
  );
});
