import { useNavigate } from "react-router-dom";

const DOCS_URL = "/docs";

export const LandingPage = () => {
  const navigate = useNavigate();

  const handleEnterPortal = () => {
    navigate("/dashboard");
  };

  const handleOpenDocs = () => {
    window.open(DOCS_URL, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="kp-root kp-bg-forest">
      <main className="kp-hero">
        <section className="kp-hero-card" aria-labelledby="kp-hero-title">
          <header className="kp-hero-header">
            <h1 id="kp-hero-title" className="kp-hero-title">
              Kaizen Portal
            </h1>
            <p className="kp-hero-tagline">Streamline Your Testing Efforts</p>
          </header>

          <section
            className="kp-signboard"
            aria-label="Main actions for Kaizen Portal"
          >
            <button
              type="button"
              className="kp-btn kp-btn-primary"
              onClick={handleEnterPortal}
            >
              Enter Portal
            </button>
            <button
              type="button"
              className="kp-btn kp-btn-secondary"
              onClick={handleOpenDocs}
            >
              Documentation
            </button>
          </section>

          <section
            className="kp-signboard kp-signboard-secondary"
            aria-label="Additional links"
          >
            <button
              type="button"
              className="kp-btn kp-btn-ghost"
              onClick={() => navigate("/settings")}
            >
              Settings
            </button>
            <button
              type="button"
              className="kp-btn kp-btn-ghost"
              onClick={() => navigate("/shortcuts")}
            >
              Shortcuts
            </button>
            <button
              type="button"
              className="kp-btn kp-btn-ghost"
              onClick={() => navigate("/about")}
            >
              About
            </button>
          </section>

          <section className="kp-auth-hint" aria-live="polite">
            {/* SaaS-ready auth block - hidden in MVP but structured for future use */}
            {/* TODO: Wire real authentication and validation when SaaS mode is enabled. */}
          </section>
        </section>
      </main>
    </div>
  );
};
