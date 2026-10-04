import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const dialog = vi.hoisted(() => ({ open: vi.fn() }));
vi.mock("@tauri-apps/api/dialog", () => ({ open: dialog.open }));
vi.mock("@tauri-apps/api/tauri", () => ({ convertFileSrc: (path: string) => `asset:${path}` }));
vi.mock("../api/desktopConfig", () => ({ isDesktopApp: () => true }));
import { PdfUploader } from "./PdfUploader";

let host: HTMLDivElement;
let root: Root;
const onSelect = vi.fn();
const preparing = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
const render = async (disabled = false) => act(async () => {
  root.render(<PdfUploader disabled={disabled} onSelect={onSelect} onPreparationChange={preparing} />);
});
const picker = () => host.querySelector<HTMLButtonElement>("button.drop-card")!;

it("opens the native picker from an accessible button and reads the selected PDF", async () => {
  dialog.open.mockResolvedValue("/scores/score.pdf");
  const fetchFile = vi.fn().mockResolvedValue(new Response(new Blob(["pdf"], { type: "application/pdf" })));
  vi.stubGlobal("fetch", fetchFile);
  await render();
  expect(picker().getAttribute("aria-label")).toBe("楽譜ファイルを選択");
  expect(picker().type).toBe("button");
  await act(async () => picker().click());
  await vi.waitFor(() => expect(onSelect).toHaveBeenCalledOnce());
  expect(dialog.open).toHaveBeenCalledWith(expect.objectContaining({ multiple: true }));
  expect(fetchFile).toHaveBeenCalledWith("asset:/scores/score.pdf");
  expect(onSelect.mock.calls[0][0]).toMatchObject({ name: "score.pdf", type: "application/pdf" });
  expect(preparing.mock.calls).toEqual([[true], [false]]);
});

it("leaves the current score alone when the native picker is cancelled", async () => {
  dialog.open.mockResolvedValue(null);
  await render();
  await act(async () => picker().click());
  await vi.waitFor(() => expect(dialog.open).toHaveBeenCalledOnce());
  expect(onSelect).not.toHaveBeenCalled();
  expect(preparing).not.toHaveBeenCalled();
});

it("blocks file selection and PDF drops while disabled", async () => {
  await render(true);
  expect(picker().disabled).toBe(true);
  await act(async () => {
    picker().click();
    const event = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: { files: [new File(["pdf"], "score.pdf")] } });
    picker().dispatchEvent(event);
  });
  expect(dialog.open).not.toHaveBeenCalled();
  expect(onSelect).not.toHaveBeenCalled();
});
