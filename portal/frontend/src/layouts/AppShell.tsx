import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { FloatingHelpButton } from "../components/FloatingHelpButton";

const navItems = [
  { label: "Tests", to: "/tests" },
  { label: "Runs", to: "/runs" },
  { label: "Insights", to: "/insights" },
  { label: "Models & Settings", to: "/models-settings" },
  { label: "Artifacts", to: "/artifacts" },
];

export const AppShell = () => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!menuRef.current) {
        return;
      }
      if (!menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("click", handleClick);
    return () => window.removeEventListener("click", handleClick);
  }, []);

  const goSettings = () => {
    setMenuOpen(false);
    navigate("/settings");
  };

  const goShortcuts = () => {
    setMenuOpen(false);
    navigate("/shortcuts");
  };

  const goAbout = () => {
    setMenuOpen(false);
    navigate("/about");
  };

  return (
    <div className="kp-root kp-bg-forest kp-shell">
      <header className="kp-nav" aria-label="Kaizen Portal navigation">
        <div className="kp-nav-board">
          <button
            type="button"
            className="kp-nav-brand"
            onClick={() => navigate("/dashboard")}
          >
            Kaizen
          </button>
          <div className="kp-nav-items">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  isActive
                    ? "kp-nav-link kp-nav-link-active"
                    : "kp-nav-link"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <div className="kp-nav-spacer" />
          <div className="kp-nav-user" ref={menuRef}>
            <button
              type="button"
              className="kp-nav-user-button"
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen((open) => !open);
              }}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              Local User ▾
            </button>
            {menuOpen ? (
              <div
                className="kp-nav-user-menu"
                role="menu"
                aria-label="User menu"
              >
                <button
                  type="button"
                  className="kp-nav-user-menu-item"
                  onClick={goSettings}
                  role="menuitem"
                >
                  Settings
                </button>
                <button
                  type="button"
                  className="kp-nav-user-menu-item"
                  onClick={goShortcuts}
                  role="menuitem"
                >
                  Keyboard Shortcuts
                </button>
                <button
                  type="button"
                  className="kp-nav-user-menu-item"
                  onClick={goAbout}
                  role="menuitem"
                >
                  About
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>
      <main className="kp-shell-main">
        <Outlet />
      </main>
      <FloatingHelpButton />
    </div>
  );
};
