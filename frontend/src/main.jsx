import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./styles.css";
import "./mission-theme.css";
import "./expedition.css";
import "./explorer.css";
import "./workflows.css";
import "./ux.css";
import "./mission-overlay.css";
import "./sim-compact.css";
import "./sim-layout.css";
import "./sim-alerts.css";
import "./trip-profile.css";
import "./motion.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
