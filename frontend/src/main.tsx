import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "motion/react";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* reducedMotion="user" makes all motion components honor the OS
        prefers-reduced-motion setting (transforms/opacity are stilled). */}
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </React.StrictMode>,
);
