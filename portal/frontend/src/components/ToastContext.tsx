import type { ReactNode } from "react";
import React, { createContext, useContext, useState, useCallback } from "react";

type ToastKind = "success" | "info" | "error";

type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

type ToastContextValue = {
  showToast: (kind: ToastKind, message: string) => void;
};

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export const ToastProvider = ({ children }: { children: ReactNode }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((kind: ToastKind, message: string) => {
    setToasts((current) => {
      const id = (current[current.length - 1]?.id ?? 0) + 1;
      return [...current, { id, kind, message }];
    });
    // auto-dismiss after 4s
    setTimeout(() => {
      setToasts((current) => current.slice(1));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="kp-toast-container" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={
              toast.kind === "success"
                ? "kp-toast kp-toast-success"
                : toast.kind === "error"
                ? "kp-toast kp-toast-error"
                : "kp-toast kp-toast-info"
            }
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
};
