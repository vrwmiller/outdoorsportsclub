"use client";

import { useId } from "react";

type KioskStatusOverlayProps =
  | {
      variant: "success";
      title: string;
      detail: string;
      onDismiss: () => void;
    }
  | {
      variant: "denied";
      title: string;
      detail: string;
    };

export default function KioskStatusOverlay(props: KioskStatusOverlayProps) {
  const { variant, title, detail } = props;
  const isModal = variant === "success";
  const titleId = useId();
  const detailId = useId();
  const theme =
    variant === "success"
      ? "bg-green-700 text-white"
      : "bg-red-600 text-white";

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-6 ${theme}`}
      role={isModal ? "alertdialog" : "alert"}
      aria-modal={isModal ? "true" : undefined}
      aria-labelledby={titleId}
      aria-describedby={detailId}
      aria-live={isModal ? undefined : "assertive"}
    >
      <div className="w-full max-w-2xl text-center">
        <p id={titleId} className="text-5xl font-bold tracking-tight">{title}</p>
        <p id={detailId} className="mt-4 text-2xl opacity-95">{detail}</p>
        {props.variant === "success" ? (
          <button
            autoFocus
            type="button"
            onClick={props.onDismiss}
            className="mt-10 min-h-12 min-w-12 rounded-xl bg-white px-8 py-4 text-xl font-semibold text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:ring-offset-2"
          >
            Continue
          </button>
        ) : (
          <p className="mt-10 text-xl opacity-80">Awaiting RSO authentication</p>
        )}
      </div>
    </div>
  );
}