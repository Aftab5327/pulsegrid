import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useLiveData } from '../hooks/useLiveData';

interface CarbonCardProps {
  className?: string;
}

/** Keyed by source so a reordered mix keeps its colour. */
const SOURCE_COLORS: Record<string, string> = {
  Coal: '#8f4e44',
  Hydro: '#f2a14a',
  Nuclear: '#a56bff',
  Wind: '#27e5d4',
  Solar: '#f15f61',
};
const FALLBACK_COLOR = '#6b7280';

/**
 * The generation-mix breakdown has no source in the current telemetry contract
 * — the carbon sensor publishes a single intensity value and no mix. The donut
 * therefore renders empty rather than showing an invented split. Once the
 * sensor publishes a mix, populate `mix` below and the chart lights up.
 */
type MixSlice = { name: string; value: number };
const mix: MixSlice[] = [];

const CarbonCard: React.FC<CarbonCardProps> = ({ className }) => {
  const cardClassName = ['card', 'card-carbon', className].filter(Boolean).join(' ');
  const { latest } = useLiveData();

  const value = latest.carbon?.value;

  const option = useMemo(
    () => ({
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {d}%',
      },
      legend: { show: false },
      series: [
        {
          type: 'pie',
          radius: ['60%', '85%'],
          avoidLabelOverlap: false,
          label: {
            show: true,
            formatter: '{d}%\n{b}',
            color: '#fff',
            fontSize: 11,
            fontWeight: 600,
            lineHeight: 14,
          },
          labelLine: {
            show: true,
            length: 10,
            length2: 8,
          },
          data: mix,
          color: mix.map((slice) => SOURCE_COLORS[slice.name] ?? FALLBACK_COLOR),
        },
      ],
    }),
    [],
  );

  return (
    <div className={cardClassName}>
      <header className="card-header">
        <div className="card-header-left">
          <img
            src="/ui_design_resources/air.png"
            alt="Carbon"
            className="card-icon"
          />
          <span className="card-title">Carbon Intensity</span>
        </div>

        <div className="card-header-right">
          <span className="chip">Current</span>
        </div>
      </header>

      <div className="carbon-chart-wrapper">
        <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
        <div className="carbon-center">
          <div className="carbon-value">
            {value === undefined ? '--' : `${Math.round(value)}gm`}
          </div>
          <div className="carbon-sub">CO2/kWh</div>
        </div>
      </div>
    </div>
  );
};

export default CarbonCard;
