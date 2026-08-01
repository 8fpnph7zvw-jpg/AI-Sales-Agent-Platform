const crypto = require('node:crypto');
const express = require('express');

function secureEqual(left, right) {
  const leftBuffer = Buffer.from(left || '');
  const rightBuffer = Buffer.from(right || '');
  return leftBuffer.length === rightBuffer.length && crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

function createWhatsAppRouter({ config, manager }) {
  const router = express.Router();

  router.use((request, response, next) => {
    if (!config.connectorApiToken) return next();
    const supplied = request.get('X-WhatsApp-Gateway-Token') || '';
    if (!secureEqual(supplied, config.connectorApiToken)) {
      return response.status(401).json({ error: 'Invalid gateway token' });
    }
    return next();
  });

  router.post('/connect', async (request, response, next) => {
    try {
      const sessionId = request.body?.sessionId || config.defaultSessionId;
      return response.status(202).json(await manager.connect(sessionId));
    } catch (error) {
      return next(error);
    }
  });

  router.get('/status', (request, response, next) => {
    try {
      const sessionId = request.query.sessionId || config.defaultSessionId;
      manager.validateSessionId(sessionId);
      return response.json(manager.snapshot(sessionId));
    } catch (error) {
      return next(error);
    }
  });

  router.get('/qr', (request, response, next) => {
    try {
      const sessionId = request.query.sessionId || config.defaultSessionId;
      manager.validateSessionId(sessionId);
      return response.json(manager.qr(sessionId));
    } catch (error) {
      return next(error);
    }
  });

  router.post('/reconnect', async (request, response, next) => {
    try {
      const sessionId = request.body?.sessionId || config.defaultSessionId;
      return response.status(202).json(await manager.reconnect(sessionId));
    } catch (error) {
      return next(error);
    }
  });

  router.delete('/session', async (request, response, next) => {
    try {
      const sessionId = request.body?.sessionId || config.defaultSessionId;
      return response.json(await manager.disconnect(sessionId));
    } catch (error) {
      return next(error);
    }
  });

  router.post('/send', async (request, response, next) => {
    try {
      const { phone, message } = request.body || {};
      if (typeof message !== 'string' || !message.trim() || message.length > 20_000) {
        return response.status(422).json({ error: 'message must contain 1 to 20000 characters' });
      }
      if (typeof phone !== 'string' && typeof phone !== 'number') {
        return response.status(422).json({ error: 'phone is required' });
      }
      const result = await manager.send({
        sessionId: request.body.sessionId || config.defaultSessionId,
        phone: String(phone),
        message: message.trim(),
      });
      return response.status(202).json(result);
    } catch (error) {
      return next(error);
    }
  });

  return router;
}

module.exports = { createWhatsAppRouter };
