import React from 'react';
import { useLiveData } from '../hooks/useLiveData';

interface WaterCardProps {
  className?: string;
}

const WaterCard: React.FC<WaterCardProps> = ({ className }) => {
  const cardClassName = ['card', 'card-water', className].filter(Boolean).join(' ');
  const { latest, history } = useLiveData();

  const value = latest.water?.value;
  const unit = latest.water?.unit ?? 'm3';

  // The telemetry contract has no day-over-day comparison, so the footer trend
  // is derived from the live window: current reading vs the oldest one held.
  const points = history.water;
  const delta =
    value !== undefined && points.length > 1 ? value - points[0].value : undefined;
  const usedLess = delta !== undefined && delta <= 0;

  return (
    <div className={cardClassName}>
      <header className="card-header">
        <div className="card-header-left">
          <img
            src="/ui_design_resources/drop.png"
            alt="Water"
            className="card-icon"
          />
          <span className="card-title">Water Consumption</span>
        </div>
        <div className="card-header-right">
          <span className="chip">Live</span>
        </div>
      </header>
      <div className="water-main">
        <div className="water-icon" />
        <div className="water-value">
          {value === undefined ? '--' : `${value.toFixed(2)} ${unit}`}
        </div>
      </div>
      <footer className="water-footer">
        <span className="trend-icon">{usedLess ? 'v' : '^'}</span>
        <span className="trend-text">
          {delta === undefined
            ? '--'
            : `${Math.abs(delta).toFixed(2)} ${unit} ${usedLess ? 'less' : 'more'} than at the start of the window`}
        </span>
      </footer>
    </div>
  );
};

export default WaterCard;
