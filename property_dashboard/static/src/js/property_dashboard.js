/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle, loadCSS } from "@web/core/assets";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, proxy, signal } from "@odoo/owl";


/* =====================================================================
 * Theme palettes — ported verbatim from the Advanced Accounting Dashboard
 * so the look is identical (Purple / Ocean / Light / Dark / Comet).
 * ===================================================================== */
const THEMES = {
    purple: {
        cssClass: "ad-theme-purple", isDark: false,
        palette: ["#7C3AED", "#06B6D4", "#F59E0B", "#EF4444", "#10B981", "#EC4899", "#8B5CF6", "#14B8A6", "#F97316", "#6366F1"],
        textTick: "#8886a0", gridColor: "rgba(124,58,237,0.06)", legendColor: "#2d2b3d",
        tooltipBg: "rgba(45,43,61,0.95)", tooltipTitle: "#fff", tooltipBody: "rgba(255,255,255,0.8)",
        tooltipBorder: "rgba(124,58,237,0.3)", doughnutBorder: "rgba(255,255,255,0.85)",
        line: "#7C3AED", fill: ["rgba(124,58,237,0.22)", "rgba(124,58,237,0.0)"], pointBg: "#fff",
    },
    ocean: {
        cssClass: "ad-theme-ocean", isDark: false,
        palette: ["#0097A7", "#E91E63", "#5C6BC0", "#43A047", "#EF6C00", "#00ACC1", "#AB47BC", "#00897B", "#F4511E", "#0288D1"],
        textTick: "#6b8fa0", gridColor: "rgba(0,151,167,0.06)", legendColor: "#1a3c4d",
        tooltipBg: "rgba(26,60,77,0.95)", tooltipTitle: "#fff", tooltipBody: "rgba(255,255,255,0.8)",
        tooltipBorder: "rgba(0,151,167,0.3)", doughnutBorder: "rgba(255,255,255,0.85)",
        line: "#0097A7", fill: ["rgba(0,151,167,0.22)", "rgba(0,151,167,0.0)"], pointBg: "#fff",
    },
    light: {
        cssClass: "", isDark: false,
        palette: ["#66BB6A", "#42A5F5", "#AB47BC", "#EF5350", "#FFA726", "#26A69A", "#5C6BC0", "#EC407A", "#8D6E63", "#78909C"],
        textTick: "#8e8ea0", gridColor: "rgba(102,187,106,0.08)", legendColor: "#37374a",
        tooltipBg: "rgba(55,55,74,0.95)", tooltipTitle: "#fff", tooltipBody: "rgba(255,255,255,0.8)",
        tooltipBorder: "rgba(102,187,106,0.3)", doughnutBorder: "rgba(255,255,255,0.8)",
        line: "#66BB6A", fill: ["rgba(102,187,106,0.25)", "rgba(102,187,106,0.0)"], pointBg: "#fff",
    },
    dark: {
        cssClass: "ad-theme-dark", isDark: true,
        palette: ["#38bdf8", "#fb7185", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#22d3ee", "#a3e635", "#fb923c", "#818cf8"],
        textTick: "#525880", gridColor: "rgba(255,255,255,0.04)", legendColor: "#b0b5d0",
        tooltipBg: "rgba(5,7,12,0.96)", tooltipTitle: "#edf0f7", tooltipBody: "rgba(237,240,247,0.65)",
        tooltipBorder: "rgba(56,189,248,0.12)", doughnutBorder: "rgba(10,12,18,0.95)",
        line: "#38bdf8", fill: ["rgba(56,189,248,0.28)", "rgba(56,189,248,0.0)"], pointBg: "#11141e",
    },
    comet: {
        cssClass: "ad-theme-comet", isDark: true,
        palette: ["#D4AF37", "#FFD700", "#FFE066", "#ff6464", "#34d399", "#A0CFFF", "#c08fff", "#ffb450", "#a78bfa", "#fbbf24"],
        textTick: "rgba(255,255,255,0.5)", gridColor: "rgba(255,255,255,0.04)", legendColor: "rgba(255,255,255,0.6)",
        tooltipBg: "rgba(10,14,46,0.95)", tooltipTitle: "#D4AF37", tooltipBody: "rgba(255,255,255,0.8)",
        tooltipBorder: "rgba(212,175,55,0.3)", doughnutBorder: "rgba(10,14,46,0.95)",
        line: "#D4AF37", fill: ["rgba(212,175,55,0.25)", "rgba(212,175,55,0.0)"], pointBg: "#0a0e2e",
    },
};

export class PropertyDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.root = signal.ref();
        this.charts = {};

        let saved = "purple";
        try { saved = localStorage.getItem("property_dashboard_theme") || "purple"; } catch (e) {}

        this.state = proxy({
            loading: true,
            error: false,
            theme: saved,
            kpis: {},
            animKpis: {},
            data: {},
            filters: { types: [], sale_lease: [], regions: [], buildings: [], subtypes: [], fiscal_years: [], months: [] },
            sel: { type: false, sale_lease: false, region: false, building: false, subtype: false, fiscal_year: false, month: false },
            currency: "",
            periodLabel: "",
            // renderToken changes every time the charts must be rebuilt
            renderToken: 0,
            diagOpen: false,
            diag: [],
        });
        this._paintedToken = -1;

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib"); // Chart.js 4.x shipped with Odoo
            try { await loadCSS("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"); } catch (e) {}
            try {
                const f = await this.orm.call("property.dashboard", "get_filter_data", []);
                this.state.filters = f;
                this.state.currency = f.currency_symbol;
                // server decides the default year (latest year that actually has data)
                this.state.sel.fiscal_year = f.defaults && f.defaults.fiscal_year
                    ? String(f.defaults.fiscal_year)
                    : String(new Date().getFullYear());
            } catch (e) {
                this.state.error = (e && e.message) || String(e);
            }
            await this.load();
        });

        onMounted(() => { this.applyTheme(); this.paintCharts(); this._bindTilt(); });
        // THE important fix: charts are (re)built AFTER OWL has patched the DOM,
        // never inside a bare microtask - that is why they vanished on filter change.
        onPatched(() => { this.applyTheme(); this.paintCharts(); });
        onWillUnmount(() => {
            this.destroyCharts();
            this._unbindTilt();
            if (this._kpiRaf) cancelAnimationFrame(this._kpiRaf);
        });
    }

    // ------------------------------------------------------------------ 3D tilt
    // Cursor-tracked perspective tilt + glare sheen on KPI/chart cards, bound
    // once via delegation on the root so it survives OWL patches without rebinding.
    _bindTilt() {
        if (!this.root()) return;
        if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        this._tiltCard = null;
        this._tiltMove = (ev) => {
            const card = ev.target.closest && ev.target.closest(".ad-kpi-card, .ad-chart-card");
            if (this._tiltCard && this._tiltCard !== card) this._resetTilt(this._tiltCard);
            this._tiltCard = card || null;
            if (!card) return;
            const r = card.getBoundingClientRect();
            const px = (ev.clientX - r.left) / r.width;
            const py = (ev.clientY - r.top) / r.height;
            const rx = (0.5 - py) * 10;
            const ry = (px - 0.5) * 10;
            card.style.setProperty("--glare-x", `${(px * 100).toFixed(1)}%`);
            card.style.setProperty("--glare-y", `${(py * 100).toFixed(1)}%`);
            card.style.transform = `perspective(1000px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateY(-6px) translateZ(6px)`;
            card.classList.add("ad-tilt-active");
        };
        this._tiltLeave = () => { if (this._tiltCard) { this._resetTilt(this._tiltCard); this._tiltCard = null; } };
        this.root().addEventListener("pointermove", this._tiltMove);
        this.root().addEventListener("pointerleave", this._tiltLeave);
    }

    _resetTilt(card) {
        card.classList.remove("ad-tilt-active");
        card.style.transform = "";
        card.style.removeProperty("--glare-x");
        card.style.removeProperty("--glare-y");
    }

    _unbindTilt() {
        if (!this.root()) return;
        if (this._tiltMove) this.root().removeEventListener("pointermove", this._tiltMove);
        if (this._tiltLeave) this.root().removeEventListener("pointerleave", this._tiltLeave);
    }

    // ------------------------------------------------------------------ KPI count-up
    _animateKpis(target) {
        if (this._kpiRaf) cancelAnimationFrame(this._kpiRaf);
        const keys = ["total_properties", "available", "on_rent", "sold", "buildings",
            "active_tenancies", "tenants", "occupancy", "rent_invoiced", "outstanding"];
        const from = {};
        keys.forEach((k) => { from[k] = Number(this.state.animKpis[k]) || 0; });
        const to = {};
        keys.forEach((k) => { to[k] = Number(target[k]) || 0; });
        const duration = 700;
        const ease = (t) => 1 - Math.pow(1 - t, 3);
        let startTs = null;
        const step = (ts) => {
            if (startTs === null) startTs = ts;
            const t = Math.min(1, (ts - startTs) / duration);
            const e = ease(t);
            keys.forEach((k) => { this.state.animKpis[k] = from[k] + (to[k] - from[k]) * e; });
            if (t < 1) this._kpiRaf = requestAnimationFrame(step);
        };
        this._kpiRaf = requestAnimationFrame(step);
    }

    paintCharts() {
        if (this.state.loading) return;
        if (this._paintedToken === this.state.renderToken) return;
        this._paintedToken = this.state.renderToken;
        this.destroyCharts();
        this.renderCharts();
    }

    // ------------------------------------------------------------------ data
    async load() {
        this.state.loading = true;
        this.state.error = false;
        const s = this.state.sel;
        try {
            const d = await this.orm.call("property.dashboard", "get_dashboard_data", [], {
                prop_type: s.type, sale_lease: s.sale_lease, region_id: s.region,
                building_id: s.building, subtype_id: s.subtype,
                fiscal_year: s.fiscal_year || false, month: s.month || false,
            });
            this.state.data = d;
            this.state.kpis = d.kpis || {};
            this._animateKpis(this.state.kpis);
            this.state.currency = d.currency_symbol || "";
            this.state.periodLabel = d.period_label || "";
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || (e && e.message) || String(e);
            this.state.data = {
                by_stage: { labels: [], data: [], keys: [] }, by_type: { labels: [], data: [], keys: [] },
                by_subtype: { labels: [], data: [], keys: [] }, by_building: { labels: [], data: [], keys: [] },
                by_region: { labels: [], data: [], keys: [] },
                contracts_by_status: { labels: [], data: [], keys: [] },
                contract_status_tiles: {
                    new: { value: 0, domain: [] }, renew: { value: 0, domain: [] },
                    release: { value: 0, domain: [] }, termination: { value: 0, domain: [] },
                },
                monthly_invoiced: { labels: [], data: [] },
                recent_contracts: [], outstanding_invoices: [],
            };
            this.state.kpis = {};
        }
        this.state.renderToken++;
        this.state.loading = false;
    }

    async refresh() {
        await this.load();
    }

    async toggleDiagnostics() {
        this.state.diagOpen = !this.state.diagOpen;
        if (this.state.diagOpen && !this.state.diag.length) {
            try {
                this.state.diag = await this.orm.call("property.dashboard", "get_diagnostics", []);
            } catch (e) {
                this.state.diag = [{ label: "Diagnostics call failed", ok: false, detail: String(e) }];
            }
        }
    }

    // ------------------------------------------------------------------ filters
    onFilter(key, ev) {
        let v = ev.target.value;
        if (["region", "building", "subtype"].includes(key)) {
            v = v ? parseInt(v, 10) : false;
        } else if (key === "month") {
            v = v === "" ? false : parseInt(v, 10);
        } else if (key === "fiscal_year") {
            // keep it a STRING - the option values and state must compare with ===
            v = v === "" ? false : String(v);
        }
        this.state.sel[key] = v === 0 ? false : (v || false);
        this.refresh();
    }

    resetFilters() {
        const def = this.state.filters.defaults;
        this.state.sel = {
            type: false, sale_lease: false, region: false, building: false, subtype: false,
            fiscal_year: def && def.fiscal_year ? String(def.fiscal_year) : false,
            month: false,
        };
        this.refresh();
    }

    get subtypesForType() {
        const t = this.state.sel.type;
        if (!t) return this.state.filters.subtypes;
        return this.state.filters.subtypes.filter((s) => !s.type || s.type === t);
    }

    // ------------------------------------------------------------------ theme
    switchTheme(theme) {
        if (theme === this.state.theme) return;
        this.state.theme = theme;
        try { localStorage.setItem("property_dashboard_theme", theme); } catch (e) {}
        this.state.renderToken++;
    }

    applyTheme() {
        // root.el IS the .ad-dashboard-container div (t-ref="root" sits on it directly),
        // so querySelector(".ad-dashboard-container") would only match descendants - never itself.
        const el = this.root();
        if (!el) return;
        el.classList.remove("ad-theme-dark", "ad-theme-purple", "ad-theme-ocean", "ad-theme-comet");
        const cls = THEMES[this.state.theme].cssClass;
        if (cls) el.classList.add(cls);
    }

    C() { return THEMES[this.state.theme]; }

    // ------------------------------------------------------------------ format
    fmt(v) {
        if (v === undefined || v === null || isNaN(v)) return "0";
        const n = Math.abs(parseFloat(v));
        return (v < 0 ? "-" : "") + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    money(v) { return `${this.state.currency} ${this.fmt(v)}`; }

    // ------------------------------------------------------------------ click-through
    // Mirrors dashboard.py's _property_domain() so drill-downs match the KPI that was clicked.
    _propDomain() {
        const s = this.state.sel;
        const d = [];
        if (s.type) d.push(["type", "=", s.type]);
        if (s.sale_lease) d.push(["sale_lease", "=", s.sale_lease]);
        if (s.region) d.push(["region_id", "=", s.region]);
        if (s.building) d.push(["property_project_id", "=", s.building]);
        if (s.subtype) d.push(["property_subtype_id", "=", s.subtype]);
        return d;
    }

    // Mirrors dashboard.py's _date_range() for the currently selected year/month.
    _dateRange() {
        const s = this.state.sel;
        if (!s.fiscal_year) return [false, false];
        const year = parseInt(s.fiscal_year, 10);
        const pad = (n) => String(n).padStart(2, "0");
        if (s.month) {
            const month = parseInt(s.month, 10);
            const last = new Date(year, month, 0).getDate();
            return [`${year}-${pad(month)}-01`, `${year}-${pad(month)}-${pad(last)}`];
        }
        return [`${year}-01-01`, `${year}-12-31`];
    }

    // Mirrors dashboard.py's _project_domain() (property.project uses property_type, not type).
    _projectDomain() {
        const s = this.state.sel;
        const d = [];
        if (s.building) d.push(["id", "=", s.building]);
        if (s.type) d.push(["property_type", "=", s.type]);
        if (s.sale_lease) d.push(["sale_lease", "=", s.sale_lease]);
        if (s.region) d.push(["region_id", "=", s.region]);
        if (s.subtype) d.push(["property_subtype_id", "=", s.subtype]);
        return d;
    }

    // Mirrors dashboard.py's _tenancy_domain() (filters pushed through property_id + period overlap).
    _tenancyDomain() {
        const s = this.state.sel;
        const d = [];
        if (s.type) d.push(["property_id.type", "=", s.type]);
        if (s.sale_lease) d.push(["property_id.sale_lease", "=", s.sale_lease]);
        if (s.region) d.push(["property_id.region_id", "=", s.region]);
        if (s.building) d.push(["property_id.property_project_id", "=", s.building]);
        if (s.subtype) d.push(["property_id.property_subtype_id", "=", s.subtype]);
        const [dateFrom, dateTo] = this._dateRange();
        if (dateFrom) d.push("|", ["end_date", "=", false], ["end_date", ">=", dateFrom]);
        if (dateTo) d.push(["start_date", "<=", dateTo]);
        return d;
    }

    openProperties(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Properties",
            res_model: "property.details",
            domain: domain || [],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }
    openModel(model, domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window", name, res_model: model, domain: domain || [],
            views: [[false, "list"], [false, "form"]], target: "current",
        });
    }
    onKpi(kind) {
        const base = this._propDomain();
        const map = {
            total: [[], "All Properties"],
            available: [[["stage", "=", "available"]], "Available"],
            on_rent: [[["stage", "=", "on_lease"]], "On Rent"],
            booked: [[["stage", "=", "booked"]], "In Booking"],
            sold: [[["stage", "=", "sold"]], "Sold"],
        };
        if (map[kind]) return this.openProperties(base.concat(map[kind][0]), map[kind][1]);
        if (kind === "buildings") return this.openModel("property.project", this._projectDomain(), "Buildings");
        // tenants KPI is company-wide (unfiltered) on the server too - keep its drill-down matching.
        if (kind === "tenancies") {
            const domain = this._tenancyDomain().concat([["contract_type", "in", ["running_contract", "expiring_soon"]]]);
            return this.openModel("tenancy.details", domain, "Active Tenancies");
        }
        if (kind === "tenants") return this.openModel("res.partner", [["is_tenancy", "=", true]], "Tenants");
        const tiles = (this.state.data && this.state.data.contract_status_tiles) || {};
        if (tiles[kind]) {
            return this.openModel("tenancy.details", tiles[kind].domain || [], tiles[kind].label);
        }
    }

    // ------------------------------------------------------------------ charts
    destroyCharts() {
        Object.values(this.charts).forEach((c) => { try { c.destroy(); } catch (e) {} });
        this.charts = {};
    }

    _canvas(sel) {
        return this.root() ? this.root().querySelector(sel) : null;
    }

    _tooltip() {
        const C = this.C();
        return {
            backgroundColor: C.tooltipBg, titleColor: C.tooltipTitle, bodyColor: C.tooltipBody,
            borderColor: C.tooltipBorder, borderWidth: 1, padding: 12, cornerRadius: 10, displayColors: true,
        };
    }

    renderCharts() {
        if (this.state.loading || typeof Chart === "undefined" || !this.root()) return;
        const d = this.state.data || {};
        this._doughnut(".pd-stage-canvas", d.by_stage, "stage");
        this._bar(".pd-type-canvas", d.by_type, "type");
        this._bar(".pd-subtype-canvas", d.by_subtype, "subtype", true);
        this._line(".pd-trend-canvas", d.monthly_invoiced);
        this._doughnut(".pd-contracts-canvas", d.contracts_by_status, "contract");
        this._bar(".pd-building-canvas", d.by_building, "building", true);
        this._bar(".pd-region-canvas", d.by_region, "region", true);
    }

    hasData(block) {
        return !!(block && block.data && block.data.length);
    }

    // OWL templates cannot call JS globals, so the string coercion lives here.
    isYear(v) { return String(this.state.sel.fiscal_year) === String(v); }
    isMonth(v) { return String(this.state.sel.month) === String(v); }

    _doughnut(sel, block, kind) {
        const el = this._canvas(sel);
        if (!el || !this.hasData(block)) return;
        const C = this.C();
        this.charts[sel] = new Chart(el.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: block.labels,
                datasets: [{
                    data: block.data,
                    backgroundColor: C.palette.slice(0, block.data.length),
                    borderColor: C.doughnutBorder, borderWidth: C.isDark ? 2 : 3,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "62%",
                onClick: (e, els) => this._segmentClick(kind, block, els),
                plugins: {
                    legend: { position: "right", labels: { color: C.legendColor, font: { size: 11, weight: 500 }, padding: 12, usePointStyle: true, pointStyleWidth: 10 } },
                    tooltip: this._tooltip(),
                },
            },
        });
    }

    _bar(sel, block, kind, horizontal) {
        const el = this._canvas(sel);
        if (!el || !this.hasData(block)) return;
        const C = this.C();
        this.charts[sel] = new Chart(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: block.labels,
                datasets: [{
                    data: block.data,
                    backgroundColor: C.palette.slice(0, block.data.length),
                    borderRadius: 8, borderSkipped: false, maxBarThickness: 42,
                }],
            },
            options: {
                indexAxis: horizontal ? "y" : "x",
                responsive: true, maintainAspectRatio: false,
                onClick: (e, els) => this._segmentClick(kind, block, els),
                plugins: { legend: { display: false }, tooltip: this._tooltip() },
                scales: {
                    x: { grid: { color: C.gridColor }, ticks: { color: C.textTick, font: { size: 11 } } },
                    y: { grid: { color: C.gridColor }, ticks: { color: C.textTick, font: { size: 11 } } },
                },
            },
        });
    }

    _line(sel, block) {
        const el = this._canvas(sel);
        if (!el || !this.hasData(block)) return;
        const C = this.C();
        const ctx = el.getContext("2d");
        const grad = ctx.createLinearGradient(0, 0, 0, 300);
        grad.addColorStop(0, C.fill[0]); grad.addColorStop(1, C.fill[1]);
        this.charts[sel] = new Chart(ctx, {
            type: "line",
            data: {
                labels: block.labels,
                datasets: [{
                    data: block.data, borderColor: C.line, backgroundColor: grad,
                    fill: true, tension: 0.4, borderWidth: 3,
                    pointBackgroundColor: C.pointBg, pointBorderColor: C.line, pointBorderWidth: 2,
                    pointRadius: 4, pointHoverRadius: 6,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: Object.assign(this._tooltip(), {
                        callbacks: { label: (c) => this.money(c.raw) },
                    }),
                },
                scales: {
                    x: { grid: { color: C.gridColor }, ticks: { color: C.textTick, font: { size: 11 } } },
                    y: { grid: { color: C.gridColor }, ticks: { color: C.textTick, font: { size: 11 }, callback: (v) => this.fmt(v) } },
                },
            },
        });
    }

    _segmentClick(kind, block, els) {
        if (!els || !els.length) return;
        const key = block.keys[els[0].index];
        const base = this._propDomain();
        if (kind === "stage") return this.openProperties(base.concat([["stage", "=", key]]), "Properties");
        if (kind === "type") return this.openProperties(base.concat([["type", "=", key]]), "Properties");
        if (kind === "subtype") return this.openProperties(base.concat([["property_subtype_id", "=", key]]), "Properties");
        if (kind === "building") return this.openProperties(base.concat([["property_project_id", "=", key]]), "Properties");
        if (kind === "region") return this.openProperties(base.concat([["region_id", "=", key]]), "Properties");
        if (kind === "contract") return this.openModel("tenancy.details", this._tenancyDomain().concat([["contract_type", "=", key]]), "Contracts");
    }

    onContractRow(id) { this.openModel("tenancy.details", [["id", "=", id]], "Contract"); }
    onInvoiceRow(id) { this.openModel("account.move", [["id", "=", id]], "Invoice"); }
}

PropertyDashboard.template = "property_dashboard.Dashboard";

registry.category("actions").add("property_dashboard.dashboard", PropertyDashboard);
