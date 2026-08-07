import React, { useMemo, useState } from 'react';
import './style.css';
import { useConnected } from './hooks/useLiveData';
import Logo from './components/Logo';
import LightsCard from './components/LightsCard';
import WaterCard from './components/WaterCard';
import CarbonCard from './components/CarbonCard';
import EnergyCard from './components/EnergyCard';
import FootfallCard from './components/FootfallCard';
import { toggleCardVisibility } from './store/dashboardSlice';
import { useAppDispatch, useAppSelector } from './store/hooks';

type Section = 'home' | 'analyse' | 'control';
type CardId = 'lights' | 'water' | 'carbon' | 'energy' | 'footfall';

interface CardDefinition {
  id: CardId;
  label: string;
  render: () => React.ReactElement;
}

const App: React.FC = () => {
  const dispatch = useAppDispatch();
  const visibility = useAppSelector((state) => state.dashboard.cardVisibility);
  const [activeSection, setActiveSection] = useState<Section>('home');
  const connected = useConnected();

  const cards: CardDefinition[] = useMemo(
    () => [
      { id: 'lights', label: 'Lights', render: () => <LightsCard /> },
      { id: 'water', label: 'Water', render: () => <WaterCard /> },
      { id: 'carbon', label: 'Carbon', render: () => <CarbonCard /> },
      { id: 'energy', label: 'Energy', render: () => <EnergyCard /> },
      { id: 'footfall', label: 'Footfall', render: () => <FootfallCard /> },
    ],
    [],
  );

  const visibleCards = cards.filter((card) => visibility[card.id]);

  return (
    <div className="app-root">
      <header className="top-bar">
        <div className="brand">
          <Logo className="brand-logo" />
        </div>
        <div className="top-right">
          <div
            className={`live-status ${connected ? 'live-status-on' : 'live-status-off'}`}
            role="status"
            aria-live="polite"
          >
            <span className="live-status-dot" />
            <span>{connected ? 'LIVE' : 'offline'}</span>
          </div>
          <div className="user-avatar" />
        </div>
      </header>

      <aside className="sidebar">
        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeSection === 'home' ? 'nav-item-active' : ''}`}
            type="button"
            onClick={() => setActiveSection('home')}
          >
            <img
              src="/ui_design_resources/nav-icons/home.svg"
              alt="Home"
              className="nav-icon"
            />
            <span className="nav-label">Home</span>
          </button>
          <button
            className={`nav-item ${activeSection === 'analyse' ? 'nav-item-active' : ''}`}
            type="button"
            onClick={() => setActiveSection('analyse')}
          >
            <img
              src="/ui_design_resources/nav-icons/pie.svg"
              alt="Analyse"
              className="nav-icon"
            />
            <span className="nav-label">Analyse</span>
          </button>
          <button
            className={`nav-item ${activeSection === 'control' ? 'nav-item-active' : ''}`}
            type="button"
            onClick={() => setActiveSection('control')}
          >
            <img
              src="/ui_design_resources/nav-icons/tiles.svg"
              alt="Control"
              className="nav-icon"
            />
            <span className="nav-label">Control</span>
          </button>
        </nav>
        <div className="sidebar-fade" />
      </aside>

      <div className="main-shell">
        <main className="dashboard">
          {activeSection === 'home' && (
            <>
              <section className="card-controls" aria-label="Card visibility controls">
                {cards.map((card) => (
                  <label key={card.id} className="card-toggle">
                    <input
                      type="checkbox"
                      checked={visibility[card.id]}
                      onChange={() => dispatch(toggleCardVisibility(card.id))}
                    />
                    <span>{card.label}</span>
                  </label>
                ))}
              </section>

              <section className="grid card-grid">
                {visibleCards.map((card) => (
                  <React.Fragment key={card.id}>{card.render()}</React.Fragment>
                ))}
              </section>
            </>
          )}

          {activeSection === 'analyse' && (
            <div className="placeholder-screen">
              <h2>Analyse</h2>
              <p>Detailed analytics view can be plugged in here.</p>
            </div>
          )}

          {activeSection === 'control' && (
            <div className="placeholder-screen">
              <h2>Control</h2>
              <p>Device control view can be implemented here.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;


