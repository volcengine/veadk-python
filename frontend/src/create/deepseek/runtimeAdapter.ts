// Loaded as a native DSH plugin so session creation keeps the configured preset
export const runtimeAdapter = String.raw`import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';

export const name = 'agentkit-runtime';
export const inject = ['sessionController', 'agents', 'sessions'];

const maxBodyBytes = 1024 * 1024;
const sessionPattern = /^[A-Za-z0-9_-]{1,128}$/;

function reply(res, status, value) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(value));
}

async function readInput(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBodyBytes) throw Object.assign(new Error('Request exceeds 1 MiB'), { status: 413 });
    chunks.push(chunk);
  }
  let input;
  try { input = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw Object.assign(new Error('Expected a JSON request'), { status: 400 }); }
  if (!input || typeof input.prompt !== 'string' || !input.prompt.trim()) {
    throw Object.assign(new Error('prompt must be a non-empty string'), { status: 400 });
  }
  if (input.session_id !== undefined && (typeof input.session_id !== 'string' || !sessionPattern.test(input.session_id))) {
    throw Object.assign(new Error('Invalid session_id'), { status: 400 });
  }
  return input;
}

export function apply(ctx) {
  let ready = false;
  const active = new Map();
  const timeoutMs = Number(process.env.DSH_INVOCATION_TIMEOUT_MS || 300000);
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 2147483647) {
    throw new Error('Invalid DSH_INVOCATION_TIMEOUT_MS');
  }
  const server = createServer(async (req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    if (req.method === 'GET' && path === '/ping') {
      reply(res, ready ? 200 : 503, { status: ready ? 'Healthy' : 'Starting' });
      return;
    }
    if (req.method !== 'POST' || path !== '/invocations') {
      reply(res, 404, { error: 'Not found' });
      return;
    }
    if (!ready) { reply(res, 503, { error: 'Harness is starting' }); return; }
    let sessionId;
    let ownsSession = false;
    let timer;
    let cancel;
    try {
      const input = await readInput(req);
      sessionId = input.session_id || 'session-' + randomUUID();
      if (active.has(sessionId)) {
        reply(res, 409, { error: 'Session already has an active invocation', session_id: sessionId });
        return;
      }
      const abort = new AbortController();
      active.set(sessionId, abort);
      ownsSession = true;
      cancel = () => {
        if (!res.writableEnded) abort.abort(new Error('Client disconnected'));
      };
      res.on('close', cancel);
      timer = setTimeout(() => abort.abort(Object.assign(new Error('Invocation timed out'), { status: 504 })), timeoutMs);
      const result = await ctx.sessionController.create({ sessionId });
      const agent = ctx.agents.get(sessionId);
      if (!agent) throw new Error('Harness did not create the session');
      await agent.whenIdle();
      abort.signal.throwIfAborted();
      const firstSeq = agent.session.seq;
      const stop = () => ctx.sessionController.cancel({ sessionId });
      abort.signal.addEventListener('abort', stop, { once: true });
      try {
        await ctx.sessionController.prompt({
          sessionId, requestId: randomUUID(), mode: 'queue',
          content: [{ type: 'text', text: input.prompt }],
        }, abort.signal);
        await agent.whenIdle();
        abort.signal.throwIfAborted();
      } finally {
        abort.signal.removeEventListener('abort', stop);
      }
      await ctx.sessions.flush(agent.session);
      let response = '';
      let reason;
      for (let seq = firstSeq; seq < agent.session.seq; seq++) {
        const event = agent.session.eventAt(seq);
        if (event?.type === 'assistant/message') {
          response = event.data.message.content.filter(block => block.type === 'text').map(block => block.text).join('');
        }
        if (event?.type === 'turn/end') reason = event.data.reason;
      }
      if (reason?.kind !== 'completed') {
        reply(res, 502, { error: 'Harness turn did not complete', reason: reason?.kind || 'missing', session_id: sessionId });
        return;
      }
      reply(res, 200, { response, session_id: sessionId, agent_preset: result.agentPreset });
    } catch (error) {
      if (!res.destroyed && !res.writableEnded) {
        reply(res, error.status || 500, { error: error.status ? error.message : 'Harness invocation failed', session_id: sessionId });
      }
    } finally {
      clearTimeout(timer);
      if (cancel) res.off('close', cancel);
      if (ownsSession) active.delete(sessionId);
    }
  });
  server.requestTimeout = timeoutMs + 10000;
  server.headersTimeout = 10000;
  server.on('error', () => { ready = false; ctx.get('appExit')?.(1); });
  server.listen(Number(process.env._FAAS_RUNTIME_PORT || process.env.PORT || 8000), '0.0.0.0');
  ctx.get('loader').await().then(() => { ready = true; }, () => ctx.get('appExit')?.(1));
  ctx.effect(() => () => {
    ready = false;
    for (const abort of active.values()) abort.abort(new Error('Runtime is stopping'));
    server.close();
    server.closeAllConnections();
  }, 'agentkit-runtime.http');
}
`;
