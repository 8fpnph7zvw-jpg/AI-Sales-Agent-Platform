const LEVELS = Object.freeze({ debug: 10, info: 20, warn: 30, error: 40 });

function createLogger(levelName = 'info') {
  const threshold = LEVELS[levelName] || LEVELS.info;

  function write(level, message, fields = {}) {
    if (LEVELS[level] < threshold) return;
    const record = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...fields,
    };
    const output = JSON.stringify(record);
    if (level === 'error') console.error(output);
    else if (level === 'warn') console.warn(output);
    else console.log(output);
  }

  return {
    debug: (message, fields) => write('debug', message, fields),
    info: (message, fields) => write('info', message, fields),
    warn: (message, fields) => write('warn', message, fields),
    error: (message, fields) => write('error', message, fields),
  };
}

module.exports = { createLogger };
