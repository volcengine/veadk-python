import { createRoot } from "react-dom/client";

import "../i18n";

import highlightStyles from "highlight.js/styles/github.css?inline";
import builtinToolStyles from "../ui/builtin-tools/builtin-tools.css?inline";
import codeBrowserStyles from "../ui/CodeBrowserDialog.css?inline";
import textShimmerStyles from "../ui/text-shimmer/text-shimmer.css?inline";
import studioStyles from "../styles.css?inline";
import widgetStyles from "./website-integration.css?inline";
import { WebsiteChatWidget } from "./WebsiteChatWidget";

declare global {
  interface Window {
    __VEADK_WEBSITE_INTEGRATION_SCRIPT__?: HTMLScriptElement;
  }
}

function currentLoader(): HTMLScriptElement | null {
  return (
    window.__VEADK_WEBSITE_INTEGRATION_SCRIPT__ ??
    (document.currentScript instanceof HTMLScriptElement
      ? document.currentScript
      : null)
  );
}

const loader = currentLoader();
const token = loader?.dataset.token?.trim() ?? "";

if (loader && token && !document.querySelector("[data-veadk-website-integration]")) {
  const studioOrigin = new URL(loader.src, window.location.href).origin;
  const host = document.createElement("div");
  host.dataset.veadkWebsiteIntegration = "";
  document.body.appendChild(host);

  const shadowRoot = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = [
    studioStyles,
    highlightStyles,
    textShimmerStyles,
    builtinToolStyles,
    codeBrowserStyles,
    widgetStyles,
  ].join("\n");
  const mount = document.createElement("div");
  shadowRoot.append(style, mount);

  createRoot(mount).render(
    <WebsiteChatWidget studioOrigin={studioOrigin} token={token} />,
  );
}
