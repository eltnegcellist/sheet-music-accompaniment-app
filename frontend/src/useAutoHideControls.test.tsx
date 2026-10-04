import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAutoHideControls } from "./useAutoHideControls";

let host: HTMLDivElement;
let root: Root;

function Harness() {
  const controls = useAutoHideControls();
  return <>
    <header className="topbar" data-visible={controls.headerVisible}>
      <button id="settings">OMR</button>
    </header>
    <div className="transport" data-visible={controls.footerVisible}>
      <button id="export">MusicXML</button>
    </div>
    <button id="pin" aria-pressed={controls.controlsPinned}
      onClick={controls.toggleControlsPinned}>Controls</button>
    <button id="outside">Score</button>
  </>;
}

beforeEach(async () => {
  vi.useFakeTimers();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root.render(<Harness />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const visible = (selector: string) => host.querySelector(selector)!
  .getAttribute("data-visible") === "true";
const move = async (clientY: number) => act(async () => {
  window.dispatchEvent(new MouseEvent("mousemove", { clientY }));
});
const waitForHide = async () => act(async () => vi.advanceTimersByTime(1600));
const focus = async (id: string) => act(async () => {
  (host.querySelector(id) as HTMLButtonElement).focus();
});

it("keeps the original mouse reveal and hide behavior when unpinned", async () => {
  await move(10);
  expect(visible(".topbar")).toBe(true);
  await move(window.innerHeight - 10);
  expect(visible(".transport")).toBe(true);
  await move(window.innerHeight / 2);
  await waitForHide();
  expect(visible(".topbar")).toBe(false);
  expect(visible(".transport")).toBe(false);
});

it("reveals both controls and keeps them visible after pending hide timers", async () => {
  await move(window.innerHeight / 2);
  await act(async () => (host.querySelector("#pin") as HTMLButtonElement).click());
  await waitForHide();
  expect(host.querySelector("#pin")!.getAttribute("aria-pressed")).toBe("true");
  expect(visible(".topbar")).toBe(true);
  expect(visible(".transport")).toBe(true);
  await act(async () => (host.querySelector("#pin") as HTMLButtonElement).click());
  expect(visible(".topbar")).toBe(false);
  expect(visible(".transport")).toBe(false);
});

it("reveals keyboard-focused header controls and never hides them during focus", async () => {
  await move(window.innerHeight / 2);
  await waitForHide();
  expect(visible(".topbar")).toBe(false);
  await focus("#settings");
  expect(visible(".topbar")).toBe(true);
  await move(window.innerHeight / 2);
  await waitForHide();
  expect(visible(".topbar")).toBe(true);
  await focus("#outside");
  await move(window.innerHeight / 2);
  await waitForHide();
  expect(visible(".topbar")).toBe(false);
});

it("keeps MusicXML export reachable when keyboard focus enters the player", async () => {
  await move(window.innerHeight / 2);
  await focus("#export");
  await waitForHide();
  expect(visible(".transport")).toBe(true);
  await move(window.innerHeight / 2);
  await waitForHide();
  expect(visible(".transport")).toBe(true);
});
