/* global React, ReactDOM */
// ──────────────────────────────────────────────────────────────────────────
// EVALFLOW · TUI Redesign — app shell (sidebar, status bar, help overlay)
// ──────────────────────────────────────────────────────────────────────────
const { useState, useEffect, useCallback } = React;
const { GooseMark, KBD, StatusDot } = window;

const NAV = [
  { id: "pull",        label: "Pull",        key: "1", hint: "download runs" },
  { id: "results",     label: "Results",     key: "2", hint: "browse responses" },
  { id: "leaderboard", label: "Leaderboard", key: "3", hint: "model ranking" },
  { id: "merge",       label: "Merge",       key: "4", hint: "build datasets" },
  { id: "publish",     label: "Publish",     key: "5", hint: "upload to kaggle" },
  { id: "monitor",     label: "Monitor",     key: "6", hint: "daily watchers" },
];

const APP_VERSION = "0.2.0";

function Sidebar({ active, onSelect, onHelp, onWizard }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__mark">
          <GooseMark size={20} color="var(--accent)" />
        </div>
        <div className="sidebar__name">
          <div className="sidebar__title">evalflow</div>
          <div className="sidebar__ver">v{APP_VERSION}</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        {NAV.map((n) => (
          <button
            key={n.id}
            className={`navitem ${active === n.id ? "navitem--active" : ""}`}
            onClick={() => onSelect(n.id)}
          >
            <span className="navitem__rail" />
            <span className="navitem__key">{n.key}</span>
            <span className="navitem__label">{n.label}</span>
            <span className="navitem__hint">{n.hint}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar__foot">
        <button className="navitem navitem--small" onClick={onHelp}>
          <span className="navitem__rail" />
          <span className="navitem__key">?</span>
          <span className="navitem__label">Help</span>
        </button>
        <button className="navitem navitem--small" onClick={onWizard}>
          <span className="navitem__rail" />
          <span className="navitem__key">w</span>
          <span className="navitem__label">Setup wizard</span>
        </button>
        <div className="navitem navitem--small navitem--info">
          <span className="navitem__rail" />
          <span className="navitem__key">q</span>
          <span className="navitem__label muted">Quit</span>
        </div>
      </div>
    </aside>
  );
}

function StatusBar({ active }) {
  const view = NAV.find((n) => n.id === active);
  return (
    <footer className="statusbar">
      <div className="statusbar__l">
        <span className="statusbar__pill">
          <StatusDot tone="ok" /> kaggle · authenticated
        </span>
        <span className="statusbar__pill">
          <StatusDot tone="ok" /> github · linked
        </span>
        <span className="statusbar__sep">·</span>
        <span className="muted">outputs/ · 16 run files</span>
      </div>
      <div className="statusbar__c muted">
        <span><KBD>1</KBD>–<KBD>6</KBD> tabs</span>
        <span><KBD>↑</KBD><KBD>↓</KBD> navigate</span>
        <span><KBD>⏎</KBD> select</span>
        <span><KBD>?</KBD> help</span>
        <span><KBD>q</KBD> quit</span>
      </div>
      <div className="statusbar__r muted">
        evalflow · {view?.label || ""}
      </div>
    </footer>
  );
}

function HelpOverlay({ open, onClose }) {
  if (!open) return null;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="overlay__panel" onClick={(e) => e.stopPropagation()}>
        <div className="overlay__head">
          <div>
            <div className="overlay__title">Keyboard reference</div>
            <div className="overlay__sub muted">Every action in evalflow is keyboard-first.</div>
          </div>
          <button className="overlay__close" onClick={onClose}>esc</button>
        </div>

        <div className="overlay__grid">
          <div className="overlay__group">
            <div className="overlay__group-title">Navigation</div>
            <Row k="1 – 6" desc="switch tab" />
            <Row k="?"     desc="open / close this panel" />
            <Row k="w"     desc="re-open setup wizard" />
            <Row k="q"     desc="quit evalflow" />
            <Row k="Esc"   desc="unfocus current field" />
          </div>
          <div className="overlay__group">
            <div className="overlay__group-title">Within a page</div>
            <Row k="↑ / ↓"  desc="move between fields" />
            <Row k="← / →"  desc="cycle between action buttons / filters" />
            <Row k="⏎"      desc="confirm / activate" />
            <Row k="Ctrl+R" desc="refresh data (Results, Leaderboard, Monitor)" />
          </div>
          <div className="overlay__group">
            <div className="overlay__group-title">Workflow</div>
            <Row desc="1. Pull → paste your benchmark slug, hit ⏎" />
            <Row desc="2. Results → inspect responses & failures" />
            <Row desc="3. Leaderboard → cross-model accuracy" />
            <Row desc="4. Merge → build SFT + preference CSVs" />
            <Row desc="5. Publish → upload to Kaggle Datasets" />
            <Row desc="6. Monitor → set up daily auto-runs" />
          </div>
        </div>

        <div className="overlay__foot muted">
          Press <KBD>?</KBD> or <KBD>esc</KBD> to dismiss.
        </div>
      </div>
    </div>
  );
}

function Row({ k, desc }) {
  return (
    <div className="kbrow">
      <div className="kbrow__k">{k && <KBD>{k}</KBD>}</div>
      <div className="kbrow__d">{desc}</div>
    </div>
  );
}

function App() {
  const [active, setActive] = useState("pull");
  const [help,   setHelp]   = useState(false);
  const [toast,  setToast]  = useState(null);

  // Keyboard nav
  const onKey = useCallback((e) => {
    if (e.target && /(INPUT|TEXTAREA)/.test(e.target.tagName)) return;
    if (e.key === "?")          { setHelp((h) => !h); return; }
    if (e.key === "Escape")     { setHelp(false); return; }
    if (e.key === "w")          { setToast("setup wizard launched (mock)"); return; }
    if (e.key === "q")          { setToast("byye 👋 — quit invoked"); return; }
    const n = NAV.find((x) => x.key === e.key);
    if (n) { setActive(n.id); }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 1800);
    return () => clearTimeout(t);
  }, [toast]);

  const Screen = window.SCREENS[active];

  return (
    <div className="app">
      <Sidebar
        active={active}
        onSelect={setActive}
        onHelp={() => setHelp(true)}
        onWizard={() => setToast("setup wizard launched (mock)")}
      />
      <main className="content">
        <div className="content__inner">
          <Screen key={active} />
        </div>
      </main>
      <StatusBar active={active} />
      <HelpOverlay open={help} onClose={() => setHelp(false)} />
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
