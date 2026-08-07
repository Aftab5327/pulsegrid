import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useLiveData } from '../hooks/useLiveData';
import { timeLabel } from '../utils/formatTime';

interface EnergyCardProps {
  className?: string;
}

const EnergyCard: React.FC<EnergyCardProps> = ({ className }) => {
  const cardClassName = ['card', 'card-energy', className].filter(Boolean).join(' ');
  const { history } = useLiveData();

  const points = history.energy;

  const option = useMemo(
    () => ({
      tooltip: { show: false },
      grid: { left: 10, right: 10, top: 20, bottom: 24 },
      xAxis: {
        type: 'category',
        data: points.map((point) => timeLabel(point.ts)),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#6b7280', fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        show: false,
      },
      series: [
        {
          type: 'bar',
          data: points.map((point) => point.value),
          barWidth: 24,
          itemStyle: {
            borderRadius: [10, 10, 10, 10],
            color: '#00ffd1',
          },
        },
      ],
    }),
    [points],
  );

  return (
    <div className={cardClassName}>
      <header className="card-header">
        <div className="card-header-left">
          <img
            src="/ui_design_resources/flash.png"
            alt="Energy"
            className="card-icon"
          />
          <span className="card-title">Energy Consumption</span>
        </div>
        <div className="card-header-right">
          <span className="chip">Live</span>
        </div>
      </header>
      <div className="chart-container">
        <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
      </div>
    </div>
  );
};

export default EnergyCard;
