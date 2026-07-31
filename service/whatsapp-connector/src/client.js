const { Client, LocalAuth } = require('whatsapp-web.js');

function createWhatsAppClient({ sessionId, config }) {
  const args = ['--disable-dev-shm-usage'];
  if (config.puppeteerNoSandbox) {
    args.push('--no-sandbox', '--disable-setuid-sandbox');
  }

  return new Client({
    authStrategy: new LocalAuth({
      clientId: sessionId,
      dataPath: config.sessionsPath,
    }),
    puppeteer: {
      headless: config.puppeteerHeadless,
      executablePath: config.puppeteerExecutablePath,
      args,
    },
  });
}

module.exports = { createWhatsAppClient };
