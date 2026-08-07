/** Chart axis label for a reading timestamp: "18:04". */
export function timeLabel(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
}

/**
 * "18:04:22" — for the Analyse chart, where readings two seconds apart would
 * otherwise share a label.
 */
export function timeLabelWithSeconds(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
