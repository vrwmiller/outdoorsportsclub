"use client";

interface KioskStatusOverlayProps {
  variant: "success" | "denied";
  title: string;
  detail: string;
  onDismiss: () => void;
}

export default function KioskStatusOverlay({
  variant,
  title,
  detail,
  onDismiss,
}: KioskStatusOverlayProps) {
  const titleId = "kiosk-status-overlay-title";
  const detailId = "kiosk-status-overlay-detail";
  const theme =
    variant === "success"
      ? "bg-green-700 text-white"
      : "bg-red-600 text-white";

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-6 ${theme}`}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={detailId}
    >
      <div className="w-full max-w-2xl text-center">
        <p id={titleId} className="text-5xl font-bold tracking-tight">{title}</p>
        <p id={detailId} className="mt-4 text-2xl opacity-95">{detail}</p>
        <button
          autoFocus
          type="button"
          onClick={onDismiss}
          className="mt-10 min-h-12 min-w-12 rounded-xl bg-white px-8 py-4 text-xl font-semibold text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:ring-offset-2"
        >
          Continue
        </button>
      </div>
    </div>
  );
}