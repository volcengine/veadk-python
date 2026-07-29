import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "motion/react";
import { PhotoProvider } from "react-photo-view";
import App from "./App";
import "react-photo-view/dist/react-photo-view.css";
import "./styles.css";

const PRELOAD_RECOVERY_KEY = "veadk.preloadRecoveryAt";

// An open tab can still reference hashed lazy chunks from the previous release.
// Reload once so the browser picks up the current HTML and asset manifest.
window.addEventListener("vite:preloadError", (event) => {
  const now = Date.now();
  let lastRecoveryAt = 0;
  try {
    lastRecoveryAt = Number(sessionStorage.getItem(PRELOAD_RECOVERY_KEY) || "0");
  } catch {
    /* storage unavailable */
  }
  if (now - lastRecoveryAt < 10_000) return;

  event.preventDefault();
  try {
    sessionStorage.setItem(PRELOAD_RECOVERY_KEY, String(now));
  } catch {
    /* storage unavailable */
  }
  window.location.reload();
});

// OAuth popup callback landing. When an OAuth authorize flow (see runOAuthPopup
// in App.tsx) redirects back to our own origin, this same SPA is loaded inside
// the popup. Detect that case *before* the app boots, hand the full callback
// URL (with ?code=&state=) back to the opener, and close — so the user never
// has to paste anything and the app never mounts in a throwaway window.
(() => {
  const isCallback =
    window.opener &&
    window.opener !== window &&
    /[?&](code|state|error)=/.test(window.location.search);
  if (!isCallback) return false;
  try {
    window.opener.postMessage(
      { veadkOAuth: true, url: window.location.href },
      window.location.origin,
    );
  } catch {
    /* ignore */
  }
  window.close();
  return true;
})() ||
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* reducedMotion="user" makes all motion components honor the OS
        prefers-reduced-motion setting (transforms/opacity are stilled). */}
    <MotionConfig reducedMotion="user">
      <PhotoProvider maskOpacity={0.9}>
        <App />
      </PhotoProvider>
    </MotionConfig>
  </React.StrictMode>,
);
