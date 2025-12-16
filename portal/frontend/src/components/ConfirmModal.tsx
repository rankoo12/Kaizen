type ConfirmModalProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export const ConfirmModal = ({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmModalProps) => {
  if (!open) return null;

  return (
    <div className="kp-modal-backdrop" aria-modal="true" role="dialog">
      <div className="kp-modal kp-confirm-modal" onClick={onCancel}>
        <div
          className="kp-plan-viewer-board"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="kp-panel-header">
            <h2 className="kp-panel-title">{title}</h2>
          </div>
          <div className="kp-panel-body">
            <p>{message}</p>
            <div className="kp-confirm-buttons">
              <button
                type="button"
                className="kp-btn kp-btn-secondary"
                onClick={onCancel}
              >
                {cancelLabel}
              </button>
              <button
                type="button"
                className="kp-btn kp-btn-primary"
                onClick={onConfirm}
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
