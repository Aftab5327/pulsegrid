import React from 'react';
import { useLiveData } from '../hooks/useLiveData';

interface LightsCardProps {
  className?: string;
}

/** Length of the gauge arc path below, in user units. */
const ARC_LENGTH = 205;

/** The telemetry contract carries no range, so the gauge scale lives here.
 *  Keep in step with the lights sensor in backend/simulators/devices.py. */
const SCALE_MIN = 2700;
const SCALE_MAX = 5000;

const LightsCard: React.FC<LightsCardProps> = ({ className }) => {
  const cardClassName = ['card', className].filter(Boolean).join(' ');
  const { latest } = useLiveData();

  const value = latest.lights?.value;
  const unit = latest.lights?.unit ?? 'k';

  const fraction =
    value === undefined ? 0 : (value - SCALE_MIN) / (SCALE_MAX - SCALE_MIN);
  const clamped = Math.min(1, Math.max(0, fraction));

  return (
    <div className={cardClassName}>
      <header className="card-header">
        <div className="card-header-left">
          <img
            src="/ui_design_resources/air.png"
            alt="Lights"
            className="card-icon"
          />
          <span className="card-title">Lights</span>
        </div>

        <div className="card-header-right">
          <span className="toggle-track">
            <span className="toggle-thumb" />
          </span>
        </div>
      </header>

      <div className="lights-meter">
        <svg width="240" height="130" viewBox="0 0 240 130">
          <path
            d="M25 115 A95 95 0 0 1 215 115"
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="12"
          />
          <path
            d="M25 115 A95 95 0 0 1 215 115"
            fill="none"
            stroke="rgba(255,255,255,0.25)"
            strokeWidth="2"
            strokeDasharray="3 6"
          />
          <path
            d="M25 115 A95 95 0 0 1 215 115"
            fill="none"
            stroke="#00ffd1"
            strokeWidth="12"
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={ARC_LENGTH * (1 - clamped)}
            strokeLinecap="round"
          />
        </svg>

        <div className="lights-value">
          {value === undefined ? '--' : `${Math.round(value)}${unit}`}
        </div>

        <div className="lights-scale">
          <span>{SCALE_MIN}k</span>
          <span>{SCALE_MAX}k</span>
        </div>
      </div>
    </div>
  );
};

export default LightsCard;
