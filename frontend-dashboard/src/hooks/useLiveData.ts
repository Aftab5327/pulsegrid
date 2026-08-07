import { useSyncExternalStore } from 'react';

/**
 * Live telemetry from the FastAPI backend.
 *
 * Backed by a module-level store rather than per-component state: every card
 * calls this hook, and five components each opening their own WebSocket would
 * be five connections to the same feed. Subscribers are ref-counted, so one
 * socket serves all of them and closes when the last one unmounts.
 *
 * Mirrors the wire format in backend/main.py.
 */

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** Matches HISTORY_SIZE in backend/main.py. */
const HISTORY_LIMIT = 120;
const RECONNECT_MS = 3000;
/** Grace period before closing, so StrictMode's remount does not cycle the socket. */
const CLOSE_GRACE_MS = 250;
/** Keepalive cadence. Under the 30s idle timeout common to proxies and load balancers. */
const PING_MS = 25000;

export const METRICS = ['lights', 'water', 'carbon', 'energy', 'footfall'] as const;
export type Metric = (typeof METRICS)[number];

export interface Reading {
  sensor_id: string;
  metric: Metric;
  value: number;
  unit: string;
  site: string;
  ts: string;
}

export interface HistoryPoint {
  ts: string;
  value: number;
}

export interface LiveData {
  /** WebSocket to the backend is open. */
  connected: boolean;
  /** Backend's own MQTT link. Null until the backend reports either way. */
  brokerConnected: boolean | null;
  latest: Partial<Record<Metric, Reading>>;
  history: Record<Metric, HistoryPoint[]>;
}

const emptyHistory = (): Record<Metric, HistoryPoint[]> => ({
  lights: [],
  water: [],
  carbon: [],
  energy: [],
  footfall: [],
});

let state: LiveData = {
  connected: false,
  brokerConnected: null,
  latest: {},
  history: emptyHistory(),
};

const listeners = new Set<() => void>();

/** getSnapshot must return a stable reference, so state is replaced, never mutated. */
const getSnapshot = (): LiveData => state;

function setState(next: LiveData): void {
  state = next;
  listeners.forEach((listener) => listener());
}

function isMetric(value: unknown): value is Metric {
  return typeof value === 'string' && (METRICS as readonly string[]).includes(value);
}

function appendReading(reading: Reading): void {
  if (!isMetric(reading.metric)) return;

  const points = state.history[reading.metric];
  const next = [...points, { ts: reading.ts, value: reading.value }];
  if (next.length > HISTORY_LIMIT) next.splice(0, next.length - HISTORY_LIMIT);

  setState({
    ...state,
    latest: { ...state.latest, [reading.metric]: reading },
    history: { ...state.history, [reading.metric]: next },
  });
}

/**
 * Current value of every metric, so the cards populate immediately on mount
 * rather than waiting for the socket's snapshot frame — and still populate if
 * the WebSocket is blocked but HTTP is not.
 *
 * A reading can arrive over the socket while this request is in flight, so the
 * newer of the two wins per metric instead of the response blindly overwriting.
 */
async function fetchLatest(signal: AbortSignal): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/api/latest`, { signal });
    if (!response.ok) return;
    const body = (await response.json()) as Record<string, Reading>;
    if (signal.aborted) return;

    const latest = { ...state.latest };
    for (const [metric, reading] of Object.entries(body)) {
      if (!isMetric(metric)) continue;
      const held = latest[metric];
      if (!held || reading.ts > held.ts) latest[metric] = reading;
    }
    setState({ ...state, latest });
  } catch {
    // Backend not up yet: the socket's snapshot frame will fill this in.
  }
}

/**
 * Backfill each metric's chart from REST, so a freshly opened dashboard shows a
 * trend immediately instead of drawing one point every two seconds.
 *
 * Readings can arrive over the socket while these requests are in flight, so
 * anything newer than the fetched tail is preserved rather than overwritten.
 */
async function seedHistory(signal: AbortSignal): Promise<void> {
  const results = await Promise.all(
    METRICS.map(async (metric) => {
      try {
        const response = await fetch(`${API_URL}/api/history/${metric}`, { signal });
        if (!response.ok) return [metric, null] as const;
        const body = (await response.json()) as { readings: Reading[] };
        const points = body.readings.map((r) => ({ ts: r.ts, value: r.value }));
        return [metric, points] as const;
      } catch {
        // Backend down or metric not seen yet: the socket will fill it in.
        return [metric, null] as const;
      }
    }),
  );

  if (signal.aborted) return;

  const history = { ...state.history };
  for (const [metric, seeded] of results) {
    if (!seeded || seeded.length === 0) continue;
    const newestSeeded = seeded[seeded.length - 1].ts;
    const live = state.history[metric].filter((point) => point.ts > newestSeeded);
    const merged = [...seeded, ...live];
    history[metric] = merged.slice(-HISTORY_LIMIT);
  }
  setState({ ...state, history });
}

// --- connection lifecycle ----------------------------------------------------

let socket: WebSocket | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let closeTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;
let bootstrapController: AbortController | null = null;
let subscriberCount = 0;

/** Pull current values and chart history over REST. Runs on mount and on every
 *  reconnect, so a socket that was down for a while comes back in sync. */
function bootstrap(): void {
  bootstrapController?.abort();
  bootstrapController = new AbortController();
  const { signal } = bootstrapController;
  void fetchLatest(signal);
  void seedHistory(signal);
}

/**
 * Application-level keepalive. Browsers cannot send protocol-level ping frames
 * from JS, so this is a plain message; the backend's receive loop drains it.
 * Without it an idle proxy can silently drop a connection that looks healthy
 * to both ends.
 */
function startPing(): void {
  stopPing();
  pingTimer = setInterval(() => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'ping' }));
    }
  }, PING_MS);
}

function stopPing(): void {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function open(): void {
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    setState({ ...state, connected: true });
    bootstrap();
    startPing();
  };

  socket.onmessage = (event) => {
    let frame: unknown;
    try {
      frame = JSON.parse(event.data as string);
    } catch {
      console.warn('[useLiveData] dropped non-JSON frame');
      return;
    }
    if (typeof frame !== 'object' || frame === null) return;

    const message = frame as Record<string, unknown>;
    switch (message.type) {
      case 'snapshot': {
        const data = message.data as Record<string, Reading>;
        setState({ ...state, latest: { ...state.latest, ...data } });
        break;
      }
      case 'reading':
        appendReading(message.data as Reading);
        break;
      case 'broker':
        setState({ ...state, brokerConnected: Boolean(message.connected) });
        break;
      default:
        console.warn('[useLiveData] unknown frame type', message.type);
    }
  };

  socket.onclose = () => {
    stopPing();
    setState({ ...state, connected: false, brokerConnected: null });
    if (subscriberCount > 0) {
      retryTimer = setTimeout(open, RECONNECT_MS);
    }
  };

  // onerror is always followed by onclose, which owns the retry.
  socket.onerror = () => socket?.close();
}

function teardown(): void {
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  stopPing();
  bootstrapController?.abort();
  bootstrapController = null;

  if (socket) {
    socket.onclose = null; // this close is intentional; do not schedule a retry
    socket.close();
    socket = null;
  }
  setState({ ...state, connected: false, brokerConnected: null });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  subscriberCount += 1;

  if (closeTimer) {
    clearTimeout(closeTimer);
    closeTimer = null;
  }
  if (subscriberCount === 1 && !socket) {
    // Fetch on mount, not only on socket open: values then appear even while
    // the WebSocket is still handshaking, or if it never connects at all.
    bootstrap();
    open();
  }

  return () => {
    listeners.delete(listener);
    subscriberCount -= 1;
    if (subscriberCount === 0) {
      closeTimer = setTimeout(() => {
        closeTimer = null;
        if (subscriberCount === 0) teardown();
      }, CLOSE_GRACE_MS);
    }
  };
}

export function useLiveData(): LiveData {
  return useSyncExternalStore(subscribe, getSnapshot);
}

/**
 * Just the connection flag. Returns a primitive, so a component using this
 * re-renders only when the socket goes up or down — not on every reading, as
 * it would if it took the whole LiveData object.
 */
export function useConnected(): boolean {
  return useSyncExternalStore(subscribe, () => state.connected);
}
