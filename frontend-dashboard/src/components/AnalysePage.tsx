import React, { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { METRICS, useLiveData } from '../hooks/useLiveData';
import type { HistoryPoint, Metric } from '../hooks/useLiveData';
import { METRIC_META, MIX_SLICES, formatValue } from '../utils/metrics';
import { timeLabelWithSeconds } from '../utils/formatTime';

const PRIMARY_COLOR = '#00ffd1';
/** Taken from the carbon mix palette so the second series stays on-brand. */
const COMPARE_COLOR = '#a56bff';

interface Stats {
  current: number;
  min: number;
  max: number;
  average: number;
}

/**
 * Single pass rather than Math.min(...values): the history window is sized by
 * the backend, and spreading a large array into a call blows the stack.
 */
function summarise(points: HistoryPoint[]): Stats | null {
  if (points.length === 0) return null;

  let min = Infinity;
  let max = -Infinity;
  let sum = 0;
  for (const point of points) {
    if (point.value < min) min = point.value;
    if (point.value > max) max = point.value;
    sum += point.value;
  }

  return {
    current: points[points.length - 1].value,
    min,
    max,
    average: sum / points.length,
  };
}

const AnalysePage: React.FC = () => {
  const { latest, history } = useLiveData();

  const [metric, setMetric] = useState<Metric>('energy');
  const [compareOn, setCompareOn] = useState(false);
  const [compareMetric, setCompareMetric] = useState<Metric>('footfall');

  // Selecting the metric that is currently the compare target would otherwise
  // plot it against itself and leave the dropdown showing nothing, since that
  // option is filtered out. Fall back to the first other metric instead.
  const effectiveCompare =
    compareMetric === metric
      ? (METRICS.find((id) => id !== metric) as Metric)
      : compareMetric;

  const points = history[metric];
  const comparePoints = history[effectiveCompare];

  const unit = latest[metric]?.unit ?? METRIC_META[metric].unit;
  const compareUnit = latest[effectiveCompare]?.unit ?? METRIC_META[effectiveCompare].unit;

  const stats = useMemo(() => summarise(points), [points]);

  const option = useMemo(() => {
    // The two metrics are sampled independently, so their timestamps do not
    // line up. The primary series owns the axis; the compare series is aligned
    // to its tail, which is what "same window" means here.
    const labels = points.map((point) => timeLabelWithSeconds(point.ts));
    const compareData = compareOn ? comparePoints.slice(-points.length) : [];

    return {
      grid: { left: 56, right: compareOn ? 62 : 20, top: 24, bottom: 46 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(6, 12, 18, 0.95)',
        borderColor: 'rgba(18, 243, 208, 0.25)',
        textStyle: { color: '#f8ffff', fontSize: 12 },
        axisPointer: { type: 'line', lineStyle: { color: 'rgba(18, 243, 208, 0.35)' } },
      },
      legend: {
        show: compareOn,
        top: 0,
        right: 0,
        textStyle: { color: '#8f9bb5', fontSize: 11 },
        icon: 'roundRect',
        itemWidth: 10,
        itemHeight: 4,
      },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.2)' } },
        axisTick: { show: false },
        axisLabel: { color: '#6b7280', fontSize: 10, hideOverlap: true },
      },
      yAxis: [
        {
          type: 'value',
          scale: true,
          name: unit,
          nameTextStyle: { color: '#6b7280', fontSize: 10, align: 'right' },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.1)' } },
          axisLabel: { color: '#6b7280', fontSize: 10 },
        },
        {
          type: 'value',
          scale: true,
          show: compareOn,
          name: compareOn ? compareUnit : '',
          nameTextStyle: { color: '#6b7280', fontSize: 10, align: 'left' },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { color: '#6b7280', fontSize: 10 },
        },
      ],
      series: [
        {
          name: METRIC_META[metric].label,
          type: 'line',
          yAxisIndex: 0,
          data: points.map((point) => point.value),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: PRIMARY_COLOR },
          itemStyle: { color: PRIMARY_COLOR },
          areaStyle: { color: 'rgba(0, 255, 209, 0.12)' },
        },
        {
          // Always present, empty when off: keeps the series count stable so
          // ECharts does not leave a stale line behind when compare is toggled.
          name: METRIC_META[effectiveCompare].label,
          type: 'line',
          yAxisIndex: 1,
          data: compareData.map((point) => point.value),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: COMPARE_COLOR },
          itemStyle: { color: COMPARE_COLOR },
        },
      ],
    };
  }, [points, comparePoints, compareOn, metric, effectiveCompare, unit, compareUnit]);

  const mix = latest.carbon?.mix;

  return (
    <div className="analyse-page">
      <div className="analyse-toolbar">
        <div className="metric-pills" role="tablist" aria-label="Select metric">
          {METRICS.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={metric === id}
              className={`metric-pill ${metric === id ? 'metric-pill-active' : ''}`}
              onClick={() => setMetric(id)}
            >
              {METRIC_META[id].label}
            </button>
          ))}
        </div>

        <div className="compare-controls">
          <label className="card-toggle">
            <input
              type="checkbox"
              checked={compareOn}
              onChange={() => setCompareOn((on) => !on)}
            />
            <span>Compare</span>
          </label>
          <select
            className="compare-select"
            value={effectiveCompare}
            disabled={!compareOn}
            aria-label="Metric to compare against"
            onChange={(event) => setCompareMetric(event.target.value as Metric)}
          >
            {METRICS.filter((id) => id !== metric).map((id) => (
              <option key={id} value={id}>
                {METRIC_META[id].label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="stat-row">
        {(
          [
            ['Current', stats?.current],
            ['Min', stats?.min],
            ['Max', stats?.max],
            ['Average', stats?.average],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="card stat-tile">
            <div className="stat-label">{label}</div>
            <div className="stat-value">
              {value === undefined ? '--' : formatValue(value, metric)}
              {value !== undefined && <span className="stat-unit">{unit}</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="card analyse-chart-card">
        <header className="card-header">
          <div className="card-header-left">
            <span className="card-title">{METRIC_META[metric].label} history</span>
          </div>
          <div className="card-header-right">
            <span className="chip">{points.length} readings</span>
          </div>
        </header>
        <div className="analyse-chart-body">
          {points.length === 0 ? (
            <div className="analyse-empty">Waiting for data…</div>
          ) : (
            <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
          )}
        </div>
      </div>

      {metric === 'carbon' && (
        <div className="card mix-panel">
          <header className="card-header">
            <div className="card-header-left">
              <span className="card-title">Generation mix</span>
            </div>
            <div className="card-header-right">
              <span className="chip">Live</span>
            </div>
          </header>
          {mix ? (
            <div className="mix-list">
              {MIX_SLICES.map((slice) => (
                <div key={slice.key} className="mix-item">
                  <span className="mix-swatch" style={{ background: slice.color }} />
                  <span className="mix-name">{slice.name}</span>
                  <span className="mix-value">{(mix[slice.key] ?? 0).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="analyse-empty">Waiting for data…</div>
          )}
        </div>
      )}
    </div>
  );
};

export default AnalysePage;
