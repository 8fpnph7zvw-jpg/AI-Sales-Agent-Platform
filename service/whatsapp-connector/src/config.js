const path = require('node:path');

require('dotenv').config();

function booleanValue(name, fallback) {
  const value = process.env[name];
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
}

function integerValue(name, fallback) {
  const value = Number.parseInt(process.env[name] || String(fallback), 10);
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return value;
}

function boundedIntegerValue(name, fallback, minimum, maximum) {
  const value = Number.parseInt(process.env[name] || String(fallback), 10);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

function optionalUrl(name) {
  const value = (process.env[name] || '').trim();
  if (!value) return '';
  try {
    return new URL(value).toString().replace(/\/$/, '');
  } catch {
    throw new Error(`${name} must be a valid URL`);
  }
}

const sessionsPath = path.resolve(
  process.cwd(),
  process.env.WHATSAPP_SESSIONS_PATH || './sessions',
);
const webVersionCachePath = path.resolve(
  sessionsPath,
  process.env.WHATSAPP_WEB_VERSION_CACHE_PATH || '.wwebjs_cache',
);

module.exports = Object.freeze({
  host: process.env.HOST || '0.0.0.0',
  port: integerValue('PORT', 3001),
  logLevel: (process.env.LOG_LEVEL || 'info').toLowerCase(),
  backendApiUrl: optionalUrl('BACKEND_API_URL'),
  backendApiToken: process.env.BACKEND_API_TOKEN || '',
  difyBaseUrl: optionalUrl('DIFY_BASE_URL'),
  difyApiKey: process.env.DIFY_API_KEY || '',
  connectorApiToken: process.env.CONNECTOR_API_TOKEN || '',
  defaultSessionId: process.env.WHATSAPP_SESSION_ID || 'customer001',
  autoRestoreSessions: booleanValue('WHATSAPP_AUTO_RESTORE_SESSIONS', true),
  autoRestoreDefaultSession: booleanValue('WHATSAPP_AUTO_RESTORE_DEFAULT_SESSION', false),
  sessionsPath,
  webVersionCachePath,
  readyTimeoutMs: boundedIntegerValue('WHATSAPP_READY_TIMEOUT_MS', 120_000, 10_000, 600_000),
  readyRetryLimit: boundedIntegerValue('WHATSAPP_READY_RETRY_LIMIT', 1, 0, 5),
  browserShutdownTimeoutMs: boundedIntegerValue(
    'WHATSAPP_BROWSER_SHUTDOWN_TIMEOUT_MS',
    10_000,
    1_000,
    60_000,
  ),
  profileUnlockTimeoutMs: boundedIntegerValue(
    'WHATSAPP_PROFILE_UNLOCK_TIMEOUT_MS',
    5_000,
    500,
    60_000,
  ),
  acceptGroupMessages: booleanValue('WHATSAPP_ACCEPT_GROUP_MESSAGES', false),
  puppeteerExecutablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
  puppeteerHeadless: booleanValue('PUPPETEER_HEADLESS', true),
  puppeteerNoSandbox: booleanValue('PUPPETEER_NO_SANDBOX', false),
  corsOrigin: process.env.CORS_ORIGIN || '',
});
