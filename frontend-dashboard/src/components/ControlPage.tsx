import React, { useEffect, useRef, useState } from 'react';
import { useLiveData } from '../hooks/useLiveData';
import { sendCommand } from '../utils/api';
import type { DeviceCommand } from '../utils/api';
import { METRIC_META } from '../utils/metrics';

const SCALE_MIN = 2700;
const SCALE_MAX = 5000;
const SLIDER_STEP = 50;
const DEFAULT_TARGET = 4300;
/** Dragging a range input fires continuously; only the settled value is sent. */
const SEND_DEBOUNCE_MS = 250;

/** Devices with no control surface yet, listed so the page is honest about scope. */
const READ_ONLY = ['water', 'carbon', 'energy', 'footfall'] as const;

const ControlPage: React.FC = () => {
  const { latest, connected } = useLiveData();
  const lights = latest.lights;

  // Telemetry is the source of truth; local state is only optimism in flight.
  const liveOn = lights?.on ?? true;
  const liveTarget = lights?.target ?? null;
  const liveValue = lights?.value;

  const [pendingOn, setPendingOn] = useState<boolean | null>(null);
  const [pendingTarget, setPendingTarget] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // Drop the optimistic value once telemetry confirms the device agrees.
  useEffect(() => {
    if (pendingOn !== null && liveOn === pendingOn) setPendingOn(null);
  }, [liveOn, pendingOn]);

  useEffect(() => {
    if (pendingTarget !== null && liveTarget !== null && Math.abs(liveTarget - pendingTarget) < 1) {
      setPendingTarget(null);
    }
  }, [liveTarget, pendingTarget]);

  const shownOn = pendingOn ?? liveOn;
  const shownTarget =
    pendingTarget ??
    liveTarget ??
    (liveValue !== undefined && liveValue >= SCALE_MIN ? Math.round(liveValue) : DEFAULT_TARGET);

  const send = async (command: DeviceCommand) => {
    setError(null);
    try {
      await sendCommand('lights', command);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      // Command never landed: drop the optimism so the UI shows reality again.
      setPendingOn(null);
      setPendingTarget(null);
    }
  };

  const handleToggle = () => {
    const next = !shownOn;
    setPendingOn(next);
    void send({ on: next });
  };

  const handleSlider = (value: number) => {
    setPendingTarget(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void send({ target: value }), SEND_DEBOUNCE_MS);
  };

  const handleClearTarget = () => {
    setPendingTarget(null);
    void send({ target: null });
  };

  const disabled = !connected;
  const unit = lights?.unit ?? METRIC_META.lights.unit;

  return (
    <div className="control-page">
      <div className="control-toolbar">
        <span className="chip">
          {connected ? 'Connected — controls live' : 'Disconnected — controls disabled'}
        </span>
        {error && <span className="control-error">{error}</span>}
      </div>

      <div className="control-grid">
        <div className="card control-card">
          <header className="card-header">
            <div className="card-header-left">
              <img src="/ui_design_resources/air.png" alt="" className="card-icon" />
              <span className="card-title">Lights</span>
            </div>
            <div className="card-header-right">
              <button
                type="button"
                className="toggle-button"
                onClick={handleToggle}
                disabled={disabled}
                aria-pressed={shownOn}
                aria-label={shownOn ? 'Turn lights off' : 'Turn lights on'}
              >
                <span className={`toggle-track ${shownOn ? '' : 'toggle-track-off'}`}>
                  <span className="toggle-thumb" />
                </span>
              </button>
            </div>
          </header>

          <div className="control-body">
            <div className="control-readout">
              <span className="control-value">
                {liveValue === undefined ? '--' : `${Math.round(liveValue)}${unit}`}
              </span>
              <span className="control-state">{shownOn ? 'On' : 'Off'}</span>
            </div>

            <label className="control-slider-row">
              <span className="control-label">
                Target
                <span className="control-target">{shownTarget}k</span>
              </span>
              <input
                className="control-slider"
                type="range"
                min={SCALE_MIN}
                max={SCALE_MAX}
                step={SLIDER_STEP}
                value={shownTarget}
                disabled={disabled || !shownOn}
                onChange={(event) => handleSlider(Number(event.target.value))}
              />
              <span className="control-scale">
                <span>{SCALE_MIN}k</span>
                <span>{SCALE_MAX}k</span>
              </span>
            </label>

            <div className="control-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={handleClearTarget}
                disabled={disabled || liveTarget === null}
              >
                Clear target
              </button>
              <span className="control-hint">
                {liveTarget === null ? 'Free walk' : `Holding ${liveTarget}k`}
              </span>
            </div>
          </div>
        </div>

        <div className="card control-card">
          <header className="card-header">
            <div className="card-header-left">
              <span className="card-title">Other devices</span>
            </div>
            <div className="card-header-right">
              <span className="chip">Read-only</span>
            </div>
          </header>
          <div className="control-body">
            <ul className="readonly-list">
              {READ_ONLY.map((metric) => (
                <li key={metric} className="readonly-item">
                  <span className="readonly-name">{METRIC_META[metric].label}</span>
                  <span className="readonly-value">
                    {latest[metric] === undefined
                      ? '--'
                      : `${latest[metric]?.value} ${latest[metric]?.unit}`}
                  </span>
                </li>
              ))}
            </ul>
            <p className="control-hint">These sensors report only; no commands are exposed yet.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ControlPage;
