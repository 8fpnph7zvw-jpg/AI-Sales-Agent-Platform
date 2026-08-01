const { Client, LocalAuth } = require('whatsapp-web.js');
const path = require('node:path');

function createWhatsAppClient({ sessionId, config }) {
  const args = [
    '--disable-dev-shm-usage',
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
  ];
  if (config.puppeteerNoSandbox) {
    args.push('--no-sandbox', '--disable-setuid-sandbox');
  }

  return new Client({
    authStrategy: new LocalAuth({
      clientId: sessionId,
      dataPath: config.sessionsPath,
    }),
    // whatsapp-web.js persists the fetched web version after `authenticated`
    // and before `ready`. Its default ./.wwebjs_cache is not writable by the
    // unprivileged container user, so keep it on the writable sessions volume.
    webVersionCache: {
      type: 'local',
      path: config.webVersionCachePath || path.join(config.sessionsPath, '.wwebjs_cache'),
    },
    puppeteer: {
      headless: config.puppeteerHeadless,
      executablePath: config.puppeteerExecutablePath,
      handleSIGINT: false,
      handleSIGTERM: false,
      handleSIGHUP: false,
      args,
    },
  });
}

module.exports = { createWhatsAppClient };
