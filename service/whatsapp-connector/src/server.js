const express = require('express');

const config = require('./config');
const { createLogger } = require('./logger');
const { createWhatsAppRouter } = require('./routes/whatsapp');
const { BackendService } = require('./services/backend');
const { SessionManager } = require('./services/session-manager');
const whatsappWebJsVersion = require('whatsapp-web.js/package.json').version;

const logger = createLogger(config.logLevel);
const backendService = new BackendService(config, logger);
const manager = new SessionManager(config, backendService, logger);
const app = express();

app.disable('x-powered-by');
app.use(express.json({ limit: '256kb' }));
app.use((request, response, next) => {
  if (config.corsOrigin) {
    response.set('Access-Control-Allow-Origin', config.corsOrigin);
    response.set('Vary', 'Origin');
    response.set('Access-Control-Allow-Headers', 'Content-Type, X-WhatsApp-Gateway-Token');
    response.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  }
  if (request.method === 'OPTIONS') return response.sendStatus(204);
  return next();
});

app.get('/health', (_request, response) => {
  response.json({ status: 'ok' });
});
app.use('/api/whatsapp', createWhatsAppRouter({ config, manager }));

app.use((error, request, response, _next) => {
  const statusCode = error.statusCode || 500;
  logger.error('http_request_failed', {
    method: request.method,
    path: request.path,
    statusCode,
    error: error.message,
  });
  response.status(statusCode).json({ error: error.message || 'Internal server error' });
});

const server = app.listen(config.port, config.host, () => {
  logger.info('whatsapp_connector_started', {
    host: config.host,
    port: config.port,
    sessionsPath: config.sessionsPath,
    webVersionCachePath: config.webVersionCachePath,
    whatsappWebJsVersion,
    autoRestoreSessions: config.autoRestoreSessions,
    autoRestoreDefaultSession: config.autoRestoreDefaultSession,
  });
  manager.restoreConfiguredSessions().catch((error) => {
    logger.error('whatsapp_session_restore_failed', { error: error.message });
  });
});

async function shutdown(signal) {
  logger.info('whatsapp_connector_stopping', { signal });
  server.close();
  await manager.shutdown();
  process.exit(0);
}

process.once('SIGTERM', () => shutdown('SIGTERM'));
process.once('SIGINT', () => shutdown('SIGINT'));
