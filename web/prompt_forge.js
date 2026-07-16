import { app } from "../../scripts/app.js";

const EXT_NAME = "scg.prompt.forge";
const FORGE_URL = new URL("./Prompt_Forge.html", import.meta.url).href;

// Only one forge UI may live at a time. Holds { focus() } while open so a
// second "Open Forge" click just focuses the existing instance.
let activeForge = null;

function findBatchWidget(node) {
  return node.widgets?.find((w) => w.name === "prompt_batch") || null;
}

function hideBatchWidget(node) {
  const widget = findBatchWidget(node);
  if (!widget) return;
  widget.serialize = true;
  widget.type = "hidden";
  widget.hidden = true;
  widget.computeSize = () => [0, 0];
  widget.draw = () => {};
  widget.mouse = () => false;
  widget.onMouseDown = () => false;
  widget.onClick = () => false;
  widget.callback = widget.callback || (() => {});
  widget.inputEl?.remove?.();
  widget.element?.remove?.();
  widget.domElement?.remove?.();
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawStyledNodeButton(widget, ctx, node, widgetWidth, y, widgetHeight) {
  const marginX = 16;
  const buttonX = marginX;
  const buttonW = Math.max(80, widgetWidth - marginX * 2);
  const buttonH = 34;
  const buttonY = y + Math.max(2, Math.round((widgetHeight - buttonH) / 2));

  ctx.save();
  roundRect(ctx, buttonX, buttonY, buttonW, buttonH, 7);
  ctx.fillStyle = widget.name === "Open Forge" ? "#2f3238" : "#25282e";
  ctx.fill();
  ctx.lineWidth = 1.25;
  ctx.strokeStyle = widget.name === "Open Forge" ? "rgba(255,255,255,0.34)" : "rgba(255,255,255,0.24)";
  ctx.stroke();
  ctx.font = "900 14px Arial, Helvetica, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.fillText(widget.name, buttonX + buttonW / 2, buttonY + buttonH / 2 + 0.5);
  ctx.restore();
}

function styleNodeButton(widget) {
  if (!widget || widget.__forgeStyledButton) return;
  widget.__forgeStyledButton = true;
  widget.serialize = false;
  widget.computeSize = (width) => [width, 40];
  widget.draw = drawStyledNodeButton.bind(null, widget);
}

function setWidgetValue(node, value) {
  const widget = findBatchWidget(node);
  if (!widget) return false;
  widget.value = value;
  if (typeof widget.callback === "function") {
    try { widget.callback(value); } catch (e) { console.warn("[SCG Prompt Forge] widget callback failed", e); }
  }
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  return true;
}

function getWidgetValue(node) {
  const widget = findBatchWidget(node);
  return widget?.value || "";
}

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `forge-toast forge-toast-${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 220);
  }, 1900);
}

function ensureStyles() {
  if (document.getElementById("scg-prompt-forge-comfy-style")) return;
  const style = document.createElement("style");
  style.id = "scg-prompt-forge-comfy-style";
  style.textContent = `
    .forge-modal-overlay{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.74);display:flex;align-items:center;justify-content:center;padding:0;box-sizing:border-box;}
    .forge-modal{width:100vw;height:100vh;background:#10131b;border:0;display:flex;flex-direction:column;overflow:hidden;}
    .forge-frame{width:100%;height:100%;border:0;background:#0f1117;flex:1 1 auto;}
    .forge-toast{position:fixed;right:18px;bottom:18px;z-index:100000;background:#171a22;color:#e7eaf0;border:1px solid rgba(255,255,255,.16);border-radius:10px;padding:10px 12px;font:700 12px/1.3 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.35);opacity:0;transform:translateY(8px);transition:.18s ease;}
    .forge-toast.show{opacity:1;transform:translateY(0);}
    .forge-toast-ok{border-color:rgba(114,209,143,.45);}
    .forge-toast-warn{border-color:rgba(255,209,102,.55);}
    .forge-toast-err{border-color:rgba(255,107,107,.55);}
  `;
  document.head.appendChild(style);
}

function batchToPlainText(raw) {
  try {
    const data = JSON.parse(raw || "");
    if (data && Array.isArray(data.prompts) && data.prompts.length) {
      const prompts = data.prompts.map(String);
      // Blank-line joins are ambiguous once prompts contain blank lines
      // themselves (multi-paragraph shapes), so switch to explicit separators.
      if (prompts.some((p) => /\n\s*\n/.test(p))) {
        return prompts.map((p, i) => `=== PROMPT ${i + 1}/${prompts.length} ===\n${p}`).join("\n\n");
      }
      return prompts.join("\n\n");
    }
  } catch (_) {}
  return raw || "";
}

// navigator.clipboard needs a secure context (HTTPS/localhost); ComfyUI is
// often served over plain LAN HTTP, so fall back to execCommand there.
function legacyCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
  ta.remove();
  return ok;
}

async function copyText(text, label) {
  if (!String(text || "").trim()) { toast("Batch is empty", "warn"); return; }
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      toast(label || "Copied", "ok");
      return;
    } catch (_) { /* fall through to the legacy path */ }
  }
  if (legacyCopy(text)) toast(label || "Copied", "ok");
  else toast("Clipboard blocked by the browser", "warn");
}

function openForgeModal(node) {
  if (activeForge) { activeForge.focus(); return; }

  ensureStyles();

  const overlay = document.createElement("div");
  overlay.className = "forge-modal-overlay";

  const modal = document.createElement("div");
  modal.className = "forge-modal";

  const iframe = document.createElement("iframe");
  iframe.className = "forge-frame";
  // Cache-bust the forge HTML: ComfyUI serves .html with no Cache-Control,
  // so browsers heuristically cache the iframe document and show a stale UI.
  iframe.src = FORGE_URL + (FORGE_URL.includes("?") ? "&" : "?") + "v=" + Date.now();
  iframe.allow = "clipboard-read; clipboard-write";

  modal.append(iframe);
  overlay.append(modal);
  document.body.appendChild(overlay);
  activeForge = { focus: () => iframe.contentWindow?.focus?.() };

  function readBatchFromFrame() {
    try {
      const fapi = iframe.contentWindow?.promptForgeAPI;
      if (fapi) return fapi.getBatch();
    } catch (e) {
      console.error("[SCG Prompt Forge] Unable to read batch from iframe", e);
      toast("Could not read forge batch", "err");
    }
    return "";
  }

  function saveBatch() {
    const batch = readBatchFromFrame();
    if (!batch.trim()) { toast("Forge batch is empty", "warn"); return false; }
    setWidgetValue(node, batch);
    return true;
  }

  function close() {
    window.removeEventListener("message", onMessage);
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    activeForge = null;
  }

  // The forge lives in a same-origin iframe and signals us via postMessage.
  function onMessage(e) {
    if (e.source !== iframe.contentWindow) return;
    const type = e.data && e.data.type;
    if (type === "forgeSendClose") { if (saveBatch()) toast("Batch saved to ComfyUI node", "ok"); close(); }
    else if (type === "forgeSave") { if (saveBatch()) toast("Batch saved to ComfyUI node", "ok"); }
    else if (type === "forgeClose") { close(); }
  }
  function onKey(e) { if (e.key === "Escape") close(); }

  window.addEventListener("message", onMessage);
  document.addEventListener("keydown", onKey);

  iframe.addEventListener("load", () => {
    const current = getWidgetValue(node);
    try {
      const fapi = iframe.contentWindow?.promptForgeAPI;
      if (fapi && current && current.trim()) fapi.setBatch(current);
    } catch (e) {
      console.warn("[SCG Prompt Forge] Unable to preload batch into iframe", e);
    }
  });
}

app.registerExtension({
  name: EXT_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "SCG_Prompt_Forge") return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);
      hideBatchWidget(this);

      // Stepping through the batch is the whole point, so freshly created
      // nodes default the index control to increment (a loaded workflow's
      // saved value overrides this in configure()).
      const ctrl = this.widgets?.find((w) => w.name === "control_after_generate");
      if (ctrl) ctrl.value = "increment";

      const openWidget = this.addWidget("button", "Open Forge", null, () => openForgeModal(this));
      const copyWidget = this.addWidget("button", "Copy Batch", null, () =>
        copyText(batchToPlainText(getWidgetValue(this)), "Batch copied"));
      styleNodeButton(openWidget);
      styleNodeButton(copyWidget);

      try {
        this.size = [310, 170];
        this.setDirtyCanvas?.(true, true);
      } catch (_) {}

      requestAnimationFrame(() => {
        hideBatchWidget(this);
        this.setDirtyCanvas?.(true, true);
      });
      setTimeout(() => {
        hideBatchWidget(this);
        this.setDirtyCanvas?.(true, true);
      }, 120);
      setTimeout(() => {
        hideBatchWidget(this);
        this.setDirtyCanvas?.(true, true);
      }, 500);
    };
  },
});
