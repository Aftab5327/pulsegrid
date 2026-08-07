export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export interface DeviceCommand {
  on?: boolean;
  /** null clears the target and lets the device resume its free walk. */
  target?: number | null;
}

/**
 * POST a command to a device. Resolves when the backend has published it to
 * MQTT — not when the device has obeyed. Confirmation arrives later on the
 * telemetry stream, which is the source of truth.
 */
export async function sendCommand(device: string, command: DeviceCommand): Promise<void> {
  const response = await fetch(`${API_URL}/api/control/${device}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Non-JSON error body: the status line is all we have.
    }
    throw new Error(detail);
  }
}
