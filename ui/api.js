// API client. Talks to the engine on the same origin, or to mock.js when the engine
// is unreachable or the URL has ?mock=1.
let mode = 'live';
let mock = null;

export const apiMode = () => mode;
export const mockModule = () => mock;

export async function initApi() {
  const q = new URLSearchParams(location.search);
  if (q.get('mock') === '1') return useMock();
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    const ct = r.headers.get('content-type') || '';
    if (ct.includes('json')) return 'live';      // engine is there (even if it answered with an error)
    return useMock();                            // e.g. python http.server returning a 404 page
  } catch {
    return useMock();
  }
}

async function useMock() {
  mock = await import('./mock.js');
  mode = 'mock';
  return mode;
}

function httpError(status, json) {
  const fallback = {
    409: 'Cyberpunk 2077 is running. Close the game first.',
    423: 'Another apply is already running.',
    501: 'The engine doesn’t support this yet.',
  }[status] || `The engine answered with an error (${status}).`;
  const e = new Error(json?.error || fallback);
  e.status = status;
  return e;
}

async function request(method, path, body, raw = false) {
  if (mode === 'mock') {
    const { status, json } = await mock.handle(method, path, body);
    if (status >= 300) throw httpError(status, json);
    return json;
  }
  let res;
  try {
    res = await fetch(path, {
      method,
      cache: 'no-store',
      headers: raw ? { 'Content-Type': 'application/octet-stream' } : body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: raw ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    const e = new Error('Can’t reach the mod engine.');
    e.network = true;
    throw e;
  }
  let json = null;
  try { json = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw httpError(res.status, json);
  return json ?? {};
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body = {}) => request('POST', path, body),
  put: (path, blob) => request('PUT', path, blob, true),
};
