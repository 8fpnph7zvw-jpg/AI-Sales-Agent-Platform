# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim

ENV NODE_ENV=production \
    CI=true \
    HUSKY=0 \
    NODE_OPTIONS=--preserve-symlinks \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates dumb-init \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/service/whatsapp-connector

COPY service/whatsapp-web.js ../whatsapp-web.js
COPY service/whatsapp-connector/package.json service/whatsapp-connector/package-lock.json ./
COPY service/whatsapp-connector/scripts ./scripts
RUN node scripts/install-dependencies.js --production \
    && npm cache clean --force

COPY --chown=node:node service/whatsapp-connector/src ./src
RUN mkdir -p ./sessions && chown -R node:node ./sessions

USER node

EXPOSE 3001

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3001/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]

ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "src/server.js"]
