import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useLiveData } from '../hooks/useLiveData';
import { timeLabel } from '../utils/formatTime';

interface FootfallCardProps {
  className?: string;
}

const FootfallCard: React.FC<FootfallCardProps> = ({ className }) => {
  const cardClassName = ['card', 'card-footfall', className].filter(Boolean).join(' ');
  const { history } = useLiveData();

  const points = history.footfall;

  const option = useMemo(
    () => ({
      tooltip: { show: false },
      grid: { left: 28, right: 12, top: 10, bottom: 28 },
      xAxis: {
        type: 'category',
        data: points.map((point) => timeLabel(point.ts)),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#6b7280', fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          show: true,
          lineStyle: { color: 'rgba(148, 163, 184, 0.1)' },
        },
        axisLabel: {
          color: '#6b7280',
          fontSize: 9,
        },
      },
      series: [
        {
          type: 'line',
          data: points.map((point) => point.value),
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: {
            width: 2,
            color: '#00ffd1',
          },
          itemStyle: {
            color: '#00ffd1',
          },
          areaStyle: {
            color: 'rgba(0, 255, 209, 0.12)',
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
            src="/ui_design_resources/users.png"
            alt="Footfall"
            className="card-icon"
          />
          <span className="card-title">Footfall</span>
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

export default FootfallCard;
