import { fireEvent, render, screen } from "@testing-library/react";
import KioskStatusOverlay from "@/components/kiosk/KioskStatusOverlay";

describe("KioskStatusOverlay", () => {
  it("renders success state content and dismisses", () => {
    const onDismiss = jest.fn();

    render(
      <KioskStatusOverlay
        variant="success"
        title="Check-In Confirmed"
        detail="Training level validated"
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText("Check-In Confirmed")).toBeInTheDocument();
    expect(screen.getByText("Training level validated")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders denied state content", () => {
    render(
      <KioskStatusOverlay
        variant="denied"
        title="Check-In Denied"
        detail="Level 3 Required"
        onDismiss={() => {}}
      />,
    );

    expect(screen.getByText("Check-In Denied")).toBeInTheDocument();
    expect(screen.getByText("Level 3 Required")).toBeInTheDocument();
  });
});
