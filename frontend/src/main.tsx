import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

// Browser extensions sometimes inject async message listeners that reject with:
// "A listener indicated an asynchronous response by returning true, but the
// message channel closed before a response was received".
// This is external to the app, but Vite/React can surface it as an uncaught
// runtime error overlay that looks like our fault. Ignore only this known
// extension-originated noise so genuine app rejections still surface.
window.addEventListener("unhandledrejection", (event) => {
  const reason =
    typeof event.reason === "string"
      ? event.reason
      : event.reason instanceof Error
        ? event.reason.message
        : "";
  if (
    reason.includes(
      "A listener indicated an asynchronous response by returning true",
    )
  ) {
    event.preventDefault();
  }
});

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
