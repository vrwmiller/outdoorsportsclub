"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import type { KioskRangeLanesResponse } from "@/types/api";
import { KioskApiError, getKioskRangeLanes } from "@/lib/kioskApi";
import KioskStatusOverlay from "@/components/kiosk/KioskStatusOverlay";

type OverlayState =
  | {
      variant: "success" | "denied";
      title: string;
      detail: string;
    }
  | null;

function laneStatusClass(status: string): string {
  if (status === "Available") {
    return "bg-green-100 text-green-900";
  }
  return "bg-amber-100 text-amber-900";
}

export default function KioskShell() {
  const [lanesData, setLanesData] = useState<KioskRangeLanesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [overlay, setOverlay] = useState<OverlayState>(null);

  const loadLanes = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getKioskRangeLanes();
      setLanesData(data);
    } catch (err) {
      if (err instanceof KioskApiError) {
        setError(err.message);
      } else {
        setError("Could not load kiosk range lanes. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const laneSummary = useMemo(() => {
    if (!lanesData) {
      return { available: 0, occupied: 0 };
    }

    const available = lanesData.lanes.filter((lane) => lane.status === "Available").length;
    return { available, occupied: lanesData.lanes.length - available };
  }, [lanesData]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 bg-gray-50 p-4 text-gray-800">
      <header className="rounded-2xl bg-white p-6 shadow-md">
        <p className="text-sm font-semibold uppercase tracking-wider text-gray-500">Kiosk Surface</p>
        <h1 className="mt-2 text-4xl font-bold">Range Operations</h1>
        <p className="mt-2 text-lg text-gray-600">
          Device-token mode is active. No Cognito login is required on kiosk routes.
        </p>
      </header>

      <section className="grid grid-cols-1 gap-3 rounded-2xl bg-white p-4 shadow-md sm:grid-cols-2">
        <button
          type="button"
          onClick={loadLanes}
          className="min-h-12 min-w-12 rounded-xl bg-green-700 px-4 py-3 text-xl font-semibold text-white hover:bg-green-800 focus:outline-none focus:ring-2 focus:ring-green-600"
        >
          {isLoading ? "Loading..." : "Refresh Range Lanes"}
        </button>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() =>
              setOverlay({
                variant: "success",
                title: "Check-In Confirmed",
                detail: "Training level validated. Lane assignment complete.",
              })
            }
            className="min-h-12 min-w-12 rounded-xl bg-gray-100 px-3 py-3 text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
          >
            Preview Success
          </button>
          <button
            type="button"
            onClick={() =>
              setOverlay({
                variant: "denied",
                title: "Check-In Denied",
                detail: "Level 3 Required",
              })
            }
            className="min-h-12 min-w-12 rounded-xl bg-gray-100 px-3 py-3 text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
          >
            Preview Denied
          </button>
        </div>
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 p-4" role="alert">
          <p className="text-base font-semibold text-red-700">{error}</p>
        </section>
      ) : null}

      <section className="rounded-2xl bg-white p-6 shadow-md">
        <h2 className="text-2xl font-semibold">Lane Occupancy</h2>
        {lanesData ? (
          <>
            <p className="mt-2 text-lg text-gray-600">
              {lanesData.name} · {lanesData.is_open ? "Open" : "Closed"}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {laneSummary.available} available · {laneSummary.occupied} occupied
            </p>

            <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {lanesData.lanes.map((lane) => (
                <li key={lane.lane_id} className="rounded-xl border border-gray-200 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xl font-semibold">Lane {lane.lane_number}</p>
                    <span className={`rounded-full px-3 py-1 text-sm font-semibold ${laneStatusClass(lane.status)}`}>
                      {lane.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-gray-600">
                    Member: {lane.member_num ?? "-"} · Guests: {lane.guest_count ?? 0}
                  </p>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="mt-2 text-lg text-gray-600">
            Refresh to load kiosk lane status from `/v1/kiosk/range/lanes`.
          </p>
        )}
      </section>

      <nav className="grid grid-cols-2 gap-3 pb-6 sm:grid-cols-4">
        <Link
          href="/kiosk"
          className="flex min-h-12 min-w-12 items-center justify-center rounded-xl bg-gray-100 px-4 py-3 text-center text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
        >
          Home
        </Link>
        <button
          type="button"
          className="min-h-12 min-w-12 rounded-xl bg-gray-100 px-4 py-3 text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
        >
          Check In
        </button>
        <button
          type="button"
          className="min-h-12 min-w-12 rounded-xl bg-gray-100 px-4 py-3 text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
        >
          Check Out
        </button>
        <button
          type="button"
          className="min-h-12 min-w-12 rounded-xl bg-gray-100 px-4 py-3 text-base font-semibold text-gray-900 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-green-600"
        >
          Waiver
        </button>
      </nav>

      {overlay ? (
        <KioskStatusOverlay
          variant={overlay.variant}
          title={overlay.title}
          detail={overlay.detail}
          onDismiss={() => setOverlay(null)}
        />
      ) : null}
    </main>
  );
}