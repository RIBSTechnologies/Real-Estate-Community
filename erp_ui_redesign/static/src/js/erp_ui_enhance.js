/** @odoo-module **/
// ============================================================
// ERP UI/UX Professional Redesign - Enhanced JS v2
// ============================================================

import { FormRenderer } from "@web/views/form/form_renderer";
import { patch } from "@web/core/utils/patch";

// Current visual theme ("vibrant" | "minimal" | "classic"), set by
// loadConfiguredAppearance() near the bottom of this file once the saved
// choice is fetched. Read by enhanceOneStatusbar() to decide whether the
// statusbar pill gets the gradient/pulse "3D" treatment or a flat one.
let currentTheme = "vibrant";

// ----- Stage Color Map -----
const STAGE_COLORS = {
    done:           { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    posted:         { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    paid:           { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    validated:      { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    received:       { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    locked:         { bg: "#059669", border: "#34D399", light: "#ECFDF5", text: "#065F46" },
    purchase:       { bg: "#4F46E5", border: "#818CF8", light: "#EEF2FF", text: "#3730A3" },
    "purchase order":{ bg: "#4F46E5", border: "#818CF8", light: "#EEF2FF", text: "#3730A3" },
    confirmed:      { bg: "#4F46E5", border: "#818CF8", light: "#EEF2FF", text: "#3730A3" },
    assigned:       { bg: "#2563EB", border: "#60A5FA", light: "#EFF6FF", text: "#1E40AF" },
    ready:          { bg: "#2563EB", border: "#60A5FA", light: "#EFF6FF", text: "#1E40AF" },
    "in progress":  { bg: "#2563EB", border: "#60A5FA", light: "#EFF6FF", text: "#1E40AF" },
    open:           { bg: "#2563EB", border: "#60A5FA", light: "#EFF6FF", text: "#1E40AF" },
    "to approve":   { bg: "#2563EB", border: "#60A5FA", light: "#EFF6FF", text: "#1E40AF" },
    draft:          { bg: "#D97706", border: "#FCD34D", light: "#FFFBEB", text: "#92400E" },
    "rfq sent":     { bg: "#D97706", border: "#FCD34D", light: "#FFFBEB", text: "#92400E" },
    rfq:            { bg: "#D97706", border: "#FCD34D", light: "#FFFBEB", text: "#92400E" },
    sent:           { bg: "#D97706", border: "#FCD34D", light: "#FFFBEB", text: "#92400E" },
    waiting:        { bg: "#EA580C", border: "#FB923C", light: "#FFF7ED", text: "#9A3412" },
    "waiting another operation": { bg: "#EA580C", border: "#FB923C", light: "#FFF7ED", text: "#9A3412" },
    cancel:         { bg: "#DC2626", border: "#F87171", light: "#FEF2F2", text: "#991B1B" },
    cancelled:      { bg: "#DC2626", border: "#F87171", light: "#FEF2F2", text: "#991B1B" },
    rejected:       { bg: "#DC2626", border: "#F87171", light: "#FEF2F2", text: "#991B1B" },
};

const DEFAULT_COLOR = { bg: "#6B7280", border: "#9CA3AF", light: "#F3F4F6", text: "#374151" };

function getStageColor(text) {
    const n = (text || "").toLowerCase().trim();
    if (STAGE_COLORS[n]) return STAGE_COLORS[n];
    for (const [key, color] of Object.entries(STAGE_COLORS)) {
        if (n.includes(key) || key.includes(n)) return color;
    }
    return DEFAULT_COLOR;
}

// ============================================================
// STAGE PILLS - 3D Effect
// ============================================================
function enhanceStatusbarStages(root) {
    if (!root) return;
    root.querySelectorAll(".o_statusbar_status").forEach(enhanceOneStatusbar);
}

function enhanceOneStatusbar(statusbar) {
    const buttons = statusbar.querySelectorAll(".o_arrow_button");
    if (!buttons.length) return;

    let currentIndex = -1;
    buttons.forEach((btn, idx) => {
        if (btn.classList.contains("o_arrow_button_current")) currentIndex = idx;
    });

    const flat = currentTheme === "minimal" || currentTheme === "classic";

    buttons.forEach((btn, idx) => {
        const text = btn.textContent || "";
        const isCurrent = btn.classList.contains("o_arrow_button_current");
        const isPast = currentIndex >= 0 && idx < currentIndex;
        const c = getStageColor(text);

        btn.classList.remove("erp-stage-3d", "erp-stage-current", "erp-stage-past", "erp-stage-future");

        if (isCurrent) {
            btn.classList.add(flat ? "erp-stage-current" : "erp-stage-3d", "erp-stage-current");
            if (flat) {
                // Minimal/Classic: solid colour, no gradient, no scale, no pulse.
                btn.style.cssText = `
                    background: ${c.bg} !important;
                    color: #FFFFFF !important;
                    font-weight: 700 !important;
                    border-radius: 20px !important;
                    padding: 5px 18px !important;
                    border: none !important;
                    font-size: 0.8rem !important;
                    box-shadow: none !important;
                    transform: none !important;
                `;
                btn.style.removeProperty("--erp-stage-shadow");
                btn.style.removeProperty("--erp-stage-shadow-pulse");
            } else {
                const shadow = `0 6px 20px rgba(0,0,0,0.14), 0 0 0 3px ${c.light}, inset 0 1px 0 rgba(255,255,255,0.25)`;
                const shadowPulse = `0 8px 28px rgba(0,0,0,0.2), 0 0 0 5px ${c.light}, inset 0 1px 0 rgba(255,255,255,0.3)`;
                btn.style.cssText = `
                    background: linear-gradient(145deg, ${c.bg}, ${c.border}) !important;
                    color: #FFFFFF !important;
                    font-weight: 800 !important;
                    border-radius: 26px !important;
                    padding: 7px 24px !important;
                    border: none !important;
                    font-size: 0.84rem !important;
                    letter-spacing: 0.03em !important;
                    transform: scale(1.08) translateY(-2px) !important;
                    box-shadow: ${shadow} !important;
                    text-shadow: 0 1px 3px rgba(0,0,0,0.2) !important;
                    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1) !important;
                    position: relative !important;
                    z-index: 2 !important;
                `;
                btn.style.setProperty("--erp-stage-shadow", shadow);
                btn.style.setProperty("--erp-stage-shadow-pulse", shadowPulse);
            }
        } else if (isPast) {
            btn.classList.add(flat ? "erp-stage-past" : "erp-stage-3d", "erp-stage-past");
            btn.style.cssText = `
                background: ${c.light} !important;
                color: ${c.text} !important;
                font-weight: 600 !important;
                border-radius: ${flat ? "20px" : "26px"} !important;
                padding: 5px 20px !important;
                border: 1.5px solid ${c.border}55 !important;
                font-size: 0.8rem !important;
                opacity: 0.9 !important;
                box-shadow: ${flat ? "none" : "inset 0 1px 2px rgba(0,0,0,0.04)"} !important;
                transition: all 0.3s ease !important;
            `;
        } else {
            btn.classList.add(flat ? "erp-stage-future" : "erp-stage-3d", "erp-stage-future");
            btn.style.cssText = `
                background: #F1F5F9 !important;
                color: #94A3B8 !important;
                font-weight: 500 !important;
                border-radius: ${flat ? "20px" : "26px"} !important;
                padding: 5px 20px !important;
                border: 1px dashed #CBD5E1 !important;
                font-size: 0.8rem !important;
                opacity: 0.6 !important;
                box-shadow: none !important;
                transition: all 0.3s ease !important;
            `;
        }
    });
}

// ============================================================
// FIELD LABELS - Bold & dark
// ============================================================
function enhanceFieldLabels(formEl) {
    if (!formEl) return;
    const labels = formEl.querySelectorAll(
        ".o_inner_group .o_form_label, .o_group .o_form_label, label.o_form_label"
    );
    labels.forEach((label) => {
        if (label.dataset.erpLabeled === "2") return;
        if (label.closest(".oe_title")) return;
        label.dataset.erpLabeled = "2";
        label.style.cssText = `
            color: #1E293B !important;
            font-weight: 700 !important;
            font-size: 0.82rem !important;
            letter-spacing: 0.015em !important;
        `;
    });
}

// ============================================================
// FIELD GROUPS - Colorful left accent
// ============================================================
function enhanceFieldGroups(formEl) {
    if (!formEl) return;
    const groups = formEl.querySelectorAll(".o_inner_group");
    const accents = [
        ["rgba(79,70,229,0.22)",  "#4F46E5"],
        ["rgba(5,150,105,0.22)",  "#059669"],
        ["rgba(217,119,6,0.22)",  "#D97706"],
        ["rgba(2,132,199,0.22)",  "#0284C7"],
        ["rgba(124,58,237,0.22)", "#7C3AED"],
        ["rgba(236,72,153,0.22)", "#EC4899"],
    ];

    groups.forEach((group, i) => {
        if (group.dataset.erpGrouped === "2") return;
        group.dataset.erpGrouped = "2";
        group.classList.add("erp-group-enhanced");
        const [light, full] = accents[i % accents.length];
        group.style.borderLeftColor = light;

        group.addEventListener("mouseenter", () => {
            group.style.borderLeftColor = full;
            group.style.background = light.replace("0.22", "0.03");
        });
        group.addEventListener("mouseleave", () => {
            group.style.borderLeftColor = light;
            group.style.background = "transparent";
        });
    });
}

// ============================================================
// STATUSBAR HEADER
// ============================================================
function enhanceStatusbarHeader(formEl) {
    if (!formEl) return;
    formEl.querySelectorAll(".o_form_statusbar").forEach((sb) => {
        if (sb.dataset.erpHeader === "2") return;
        sb.dataset.erpHeader = "2";
        sb.style.cssText = `
            background: linear-gradient(120deg, #F7F9FF 0%, #EEF2FF 50%, #FDF4FF 100%) !important;
            border-bottom: 2px solid transparent !important;
            border-image: linear-gradient(to right, #DDE1EA, #4F46E5, #7C3AED, #DDE1EA) 1 !important;
            padding: 12px 22px !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 10 !important;
            box-shadow: 0 2px 10px rgba(79,70,229,0.06) !important;
        `;
    });
}

// ============================================================
// RUNTIME FIXES (bulletproof against any other stylesheet)
// ------------------------------------------------------------
// Everything up to this version tried to win the fix with a CSS
// selector - matching Odoo's real DOM, then out-specificity-ing
// whatever else was also targeting it. That's a losing game if another
// installed module's CSS loads after this one in the bundle with equal
// or higher specificity: no selector in a .scss file can guarantee a
// win there, `!important` included, because CSS specificity - not
// declaration order alone - is still what breaks the tie.
//
// An inline `style` property set via JS with `setProperty(prop, val,
// "important")` sits above *any* external stylesheet rule in the
// cascade, important or not (only another inline !important, or a
// later JS call, can beat it). Since this runs against the real,
// already-rendered element - not a guessed selector - it doesn't matter
// what class names or wrapper markup another module's widget uses
// underneath `.o_field_monetary`; only that outer class needs to be
// right, and it's Odoo's own standard MonetaryField wrapper class since
// v11.
// ============================================================

function fixMonetaryFields(root) {
    const fields = root.querySelectorAll(".o_field_monetary");
    fields.forEach((wrapper) => {
        if (wrapper.dataset.erpMonetaryFixed === "1") return;
        wrapper.dataset.erpMonetaryFixed = "1";

        const set = (el, prop, val) => el.style.setProperty(prop, val, "important");

        set(wrapper, "display", "inline-flex");
        set(wrapper, "align-items", "center");
        set(wrapper, "flex-wrap", "nowrap");
        set(wrapper, "gap", "4px");
        set(wrapper, "width", "100%");

        const input = wrapper.querySelector("input");
        Array.from(wrapper.children).forEach((child) => {
            if (child === input) {
                set(child, "flex", "1 1 auto");
                set(child, "min-width", "0");
                set(child, "text-align", "right");
            } else {
                // Whatever this element is (span, small, whatever the
                // widget renders) - it's the currency-code token.
                set(child, "position", "static");
                set(child, "top", "auto");
                set(child, "transform", "none");
                set(child, "vertical-align", "baseline");
                set(child, "line-height", "1");
                set(child, "margin", "0");
                set(child, "flex", "0 0 auto");
                set(child, "font-size", "0.75rem");
                set(child, "font-weight", "600");
                set(child, "color", "#8a93a2");
                set(child, "white-space", "nowrap");
            }
        });
    });
}

function fixTaxTotalsLinks(root) {
    const containers = root.querySelectorAll(".o_tax_totals, .oe_subtotal_footer");
    containers.forEach((container) => {
        container.querySelectorAll("a").forEach((a) => {
            if (a.dataset.erpLinkFixed === "1") return;
            a.dataset.erpLinkFixed = "1";
            a.style.setProperty("text-decoration", "none", "important");
            a.style.setProperty("border-bottom", "none", "important");
            a.style.setProperty("color", "inherit", "important");
        });
    });
}

// ============================================================
// MASTER FUNCTION
// ============================================================
function applyAllEnhancements(formEl) {
    if (!formEl) return;
    requestAnimationFrame(() => {
        enhanceFieldLabels(formEl);
        enhanceStatusbarStages(formEl);
        enhanceFieldGroups(formEl);
        enhanceStatusbarHeader(formEl);
        fixMonetaryFields(formEl);
        fixTaxTotalsLinks(formEl);
    });
}

// ============================================================
// SHARED OBSERVER (fix: was created fresh on every form mount, one per
// instance, and only ever disconnected by that same instance's own
// unmount — so opening/closing records, or scrolling through one2many
// rows that each embed a sub-form, left a growing pile of observers all
// watching the same `.o_action_manager` subtree forever. One shared,
// module-scope observer, created once, does the same job with a single
// listener regardless of how many forms come and go.
// ============================================================
let _erpObserverStarted = false;

function startSharedObserver() {
    if (_erpObserverStarted) return;
    const container = document.querySelector(".o_action_manager") || document.body;
    if (!container) return;
    _erpObserverStarted = true;

    const observer = new MutationObserver(() => applyAllEnhancements(document));
    observer.observe(container, { childList: true, subtree: true });
}

// ============================================================
// PATCH FormRenderer
// ============================================================
patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
    },

    onMounted() {
        if (super.onMounted) super.onMounted(...arguments);
        // Scoped to the whole document, not just this instance's own
        // element: querySelector(".o_form_view") would only ever return
        // the FIRST match in document order, silently missing a wizard's
        // form if it happens to render after the background view in the
        // DOM. querySelectorAll (inside applyAllEnhancements) reaches
        // every open form - background view and any dialog on top of it
        // - in one pass.
        applyAllEnhancements(document);
        startSharedObserver();
    },

    onPatched() {
        if (super.onPatched) super.onPatched(...arguments);
        setTimeout(() => applyAllEnhancements(document), 80);
    },
});

// ============================================================
// CONFIGURABLE APPEARANCE (font + theme)
// ------------------------------------------------------------
// Reads the admin's choices from the "ERP UI Redesign" settings popup
// (stored as ir.config_parameter "erp_ui_redesign.font_family" and
// "erp_ui_redesign.theme") and applies them:
//   - font -> a CSS variable that erp_redesign.scss (section 24) reads.
//   - theme -> a `data-erp-theme` attribute on <html> that the theme
//     override section of the SCSS is keyed off, plus `currentTheme`
//     above, read by enhanceOneStatusbar() for the JS-driven parts of
//     the "3D" statusbar effect that live outside plain CSS.
//
// Uses a plain fetch() to the standard /web/dataset/call_kw JSON-RPC
// endpoint rather than importing an ORM/RPC service module: those import
// paths (`@web/core/network/rpc` vs `@web/core/network/rpc_service`, etc.)
// have moved between Odoo versions, and this module is meant to drop into
// anything from 15 to 19 - the HTTP endpoint itself has stayed stable.
//
// Fonts are limited to ones already installed on the OS (system-ui,
// Segoe UI, Georgia, Roboto/Inter fall back gracefully if absent) rather
// than pulling from Google Fonts, since production Odoo servers - like
// the ones this module targets - often run without outbound internet
// access, and a missing @import would silently fail anyway.
// ============================================================
const FONT_STACKS = {
    inter: "'Inter', -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
    roboto: "'Roboto', -apple-system, 'Segoe UI', Arial, sans-serif",
    system: "-apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
    georgia: "Georgia, 'Times New Roman', serif",
    // 'default' intentionally has no entry — see applyFontChoice().
};

function applyFontChoice(value) {
    const root = document.documentElement;
    const stack = FONT_STACKS[value];
    if (stack) {
        // --erp-ui-font          : read by this module's own SCSS selectors.
        // --bs-body-font-family  : Bootstrap 5 custom property that Odoo 18
        //   uses for `body { font-family: var(--bs-body-font-family) }`.
        //   Overriding it on :root is the only way to change the font site-
        //   wide without an exhaustive selector list — and it also reaches
        //   the navbar, portalled dropdown menus, and modal dialogs that a
        //   plain SCSS rule can miss. An inline style on :root wins the
        //   cascade before specificity is evaluated, so it cannot be beaten
        //   by any external stylesheet regardless of load order.
        root.style.setProperty("--erp-ui-font", stack);
        root.style.setProperty("--bs-body-font-family", stack);
    } else {
        // "default": remove both overrides so Odoo's bundled values apply.
        root.style.removeProperty("--erp-ui-font");
        root.style.removeProperty("--bs-body-font-family");
    }
}

function applyThemeChoice(value) {
    const theme = ["vibrant", "minimal", "classic"].includes(value) ? value : "vibrant";
    currentTheme = theme;
    document.documentElement.setAttribute("data-erp-theme", theme);
    // Re-run the statusbar pass immediately so an already-rendered pill
    // picks up the flat vs. gradient/pulse styling without waiting for
    // the next DOM mutation. enhanceOneStatusbar() always recomputes
    // (it has no its-own-run-once guard), so this is safe to call again.
    enhanceStatusbarStages(document);
}

async function getConfigParam(key, fallback) {
    const response = await fetch("/web/dataset/call_kw", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "ir.config_parameter",
                method: "get_str",
                args: [key, fallback],
                kwargs: {},
            },
        }),
    });
    const data = await response.json();
    return data && data.result ? data.result : fallback;
}

async function loadConfiguredAppearance() {
    try {
        const [font, theme] = await Promise.all([
            getConfigParam("erp_ui_redesign.font_family", "default"),
            getConfigParam("erp_ui_redesign.theme", "vibrant"),
        ]);
        applyFontChoice(font);
        applyThemeChoice(theme);
    } catch (e) {
        // Non-fatal: if this fails for any reason (offline, session not
        // ready yet, etc.) the page just keeps the default appearance.
    }
}


loadConfiguredAppearance();
