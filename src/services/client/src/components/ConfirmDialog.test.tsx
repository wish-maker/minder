import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useConfirm } from "./ConfirmDialog";

function Harness({
  danger,
  confirmLabel,
}: {
  danger?: boolean;
  confirmLabel?: string;
}) {
  const { confirm, dialog } = useConfirm();
  return (
    <>
      {dialog}
      <button
        onClick={async () => {
          const result = await confirm({
            title: "Delete thing?",
            message: "This cannot be undone.",
            danger,
            confirmLabel,
          });
          document.title = `result:${result}`;
        }}
      >
        Trigger
      </button>
    </>
  );
}

afterEach(() => {
  cleanup();
  document.title = "";
});

describe("useConfirm", () => {
  it("renders no dialog until confirm() is called", () => {
    render(<Harness />);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("shows the dialog with the given title/message on confirm()", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));

    expect(await screen.findByRole("alertdialog")).toBeTruthy();
    expect(screen.getByText("Delete thing?")).toBeTruthy();
    expect(screen.getByText("This cannot be undone.")).toBeTruthy();
  });

  it("resolves true and closes the dialog when the confirm button is clicked", async () => {
    render(<Harness danger />);
    fireEvent.click(screen.getByText("Trigger"));
    await screen.findByRole("alertdialog");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(document.title).toBe("result:true"));
  });

  it("resolves false when Cancel is clicked", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    await screen.findByRole("alertdialog");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(document.title).toBe("result:false"));
  });

  it("resolves false when the backdrop is clicked", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    const backdrop = await screen.findByRole("presentation");

    fireEvent.click(backdrop);

    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(document.title).toBe("result:false"));
  });

  it("does not dismiss when the panel itself is clicked (stopPropagation)", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    const panel = await screen.findByRole("alertdialog");

    fireEvent.click(panel);

    expect(screen.queryByRole("alertdialog")).toBeTruthy();
    expect(document.title).toBe("");
  });

  it("resolves false on Escape", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    const backdrop = await screen.findByRole("presentation");

    fireEvent.keyDown(backdrop, { key: "Escape" });

    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(document.title).toBe("result:false"));
  });

  it("defaults to a 'Confirm' button for non-danger confirmations", async () => {
    render(<Harness danger={false} />);
    fireEvent.click(screen.getByText("Trigger"));
    expect(await screen.findByRole("button", { name: "Confirm" })).toBeTruthy();
  });

  it("uses a custom confirmLabel when provided, overriding the danger default", async () => {
    render(<Harness danger confirmLabel="Reconcile now" />);
    fireEvent.click(screen.getByText("Trigger"));
    expect(
      await screen.findByRole("button", { name: "Reconcile now" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("traps Tab from the last button back to the first", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    const backdrop = await screen.findByRole("presentation");
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    const cancelButton = screen.getByRole("button", { name: "Cancel" });

    confirmButton.focus();
    expect(document.activeElement).toBe(confirmButton);
    fireEvent.keyDown(backdrop, { key: "Tab" });

    expect(document.activeElement).toBe(cancelButton);
  });

  it("traps Shift+Tab from the first button back to the last", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Trigger"));
    const backdrop = await screen.findByRole("presentation");
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    const cancelButton = screen.getByRole("button", { name: "Cancel" });

    cancelButton.focus();
    expect(document.activeElement).toBe(cancelButton);
    fireEvent.keyDown(backdrop, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(confirmButton);
  });
});
