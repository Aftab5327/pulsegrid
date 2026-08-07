import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useLiveData } from '../hooks/useLiveData';
import { MIX_SLICES } from '../utils/metrics';

interface CarbonCardProps {
  className?: string;
}

/** Ring shown before the first reading: one neutral slice, no labels. */
const PLACEHOLDER_RING = [{ name: '', value: 1 }];
const PLACEHOLDER_COLOR = 'rgba(255,255,255,0.08)';

const CarbonCard: React.FC<CarbonCardProps> = ({ className }) => {
  const cardClassName = ['card', 'card-carbon', className].filter(Boolean).join(' ');
  const { latest } = useLiveData();

  const value = latest.carbon?.value;
  const mix = latest.carbon?.mix;

  const option = useMemo(() => {
    const hasMix = Boolean(mix);
    const data = hasMix
      ? MIX_SLICES.map((slice) => ({ name: slice.name, value: mix?.[slice.key] ?? 0 }))
      : PLACEHOLDER_RING;
    const colors = hasMix ? MIX_SLICES.map((slice) => slice.color) : [PLACEHOLDER_COLOR];

    return {
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {d}%',
        show: hasMix,
      },
      legend: { show: false },
      series: [
        {
          type: 'pie',
          radius: ['60%', '85%'],
          avoidLabelOverlap: false,
          silent: !hasMix,
          label: {
            show: hasMix,
            formatter: '{d}%\n{b}',
            color: '#fff',
            fontSize: 11,
            fontWeight: 600,
            lineHeight: 14,
          },
          labelLine: {
            show: hasMix,
            length: 10,
            length2: 8,
          },
          data,
          color: colors,
        },
      ],
    };
  }, [mix]);

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
