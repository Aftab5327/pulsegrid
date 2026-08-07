import type { Metric } from '../hooks/useLiveData';

/** Display metadata per metric. `unit` is only a fallback — the live reading's
 *  own unit wins whenever one has arrived. */
export const METRIC_META: Record<Metric, { label: string; decimals: number; unit: string }> = {
  lights: { label: 'Lights', decimals: 0, unit: 'k' },
  water: { label: 'Water', decimals: 2, unit: 'm3' },
  carbon: { label: 'Carbon', decimals: 1, unit: 'gCO2/kWh' },
  energy: { label: 'Energy', decimals: 0, unit: 'kWh' },
  footfall: { label: 'Footfall', decimals: 0, unit: 'people' },
};

/**
 * Generation-mix slice order and colours — the single source for both the Home
 * donut (CarbonCard) and the Analyse mix panel.
 *
 * `key` is the lowercase source name the carbon sensor publishes in its `mix`
 * object; `name` is the display label.
 */
export const MIX_SLICES = [
  { key: 'coal', name: 'Coal', color: '#8f4e44' },
  { key: 'hydro', name: 'Hydro', color: '#f2a14a' },
  { key: 'nuclear', name: 'Nuclear', color: '#a56bff' },
  { key: 'wind', name: 'Wind', color: '#27e5d4' },
  { key: 'solar', name: 'Solar', color: '#f15f61' },
] as const;

export function formatValue(value: number, metric: Metric): string {
  return value.toFixed(METRIC_META[metric].decimals);
}
