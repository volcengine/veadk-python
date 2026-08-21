(function () {
  var script = document.currentScript;
  if (!(script instanceof HTMLScriptElement) || !script.getAttribute("data-token")) return;
  window.__VEADK_WEBSITE_INTEGRATION_SCRIPT__ = script;
  import("/src/website-integration/main.tsx");
})();
