import { useState } from "react";

export const FloatingHelpButton = () => {
  const [open, setOpen] = useState(false);

  return (
    <div className="kp-help-root">
      <button
        type="button"
        className="kp-help-button"
        aria-label="Open help"
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {open ? (
        <div className="kp-help-panel">
          <h3 className="kp-help-title">Kaizen Help</h3>
          <div className="kp-help-section">
            <h4>Writing steps</h4>
            <ul>
              <li>Use clear, action-style sentences (\"Open\", \"Click\", \"Type\").</li>
              <li>Include visible text or labels when possible.</li>
              <li>Keep one action per step for better healing.</li>
            </ul>
          </div>
          <div className="kp-help-section">
            <h4>How healing works</h4>
            <ul>
              <li>Kaizen remembers past successful selectors per site.</li>
              <li>When a locator breaks, the healer searches for similar elements.</li>
              <li>High confidence matches are reused in future runs.</li>
            </ul>
          </div>
          <div className="kp-help-section">
            <h4>Common errors</h4>
            <ul>
              <li>Element not visible: add a wait step before clicking.</li>
              <li>Wrong page: confirm URLs or navigation steps.</li>
              <li>Flaky results: avoid overly generic text like \"Submit\" alone.</li>
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
};
