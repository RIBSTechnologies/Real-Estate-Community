/** @odoo-module **/
// ============================================================
// ERP UI Redesign - Document Dashboard (client action)
// ------------------------------------------------------------
// Same architecture as the reference "dynamic process menu"
// component (registry action + OWL Component + separate XML
// template + plain CSS), with the left sidebar dropped.
//
// The sidebar's job - picking which set of records the right-hand
// table shows - is done by the pill row in the content header
// instead, so the table gets the full page width. Nothing else
// about the flow changed: pick a type -> searchRead that type ->
// render the styled table -> row click opens the form.
//
// The reference component read its types out of a real table
// (`manufacturing.process.type`). This module has no such table
// and adding one would mean a new model + ACL row + menus just to
// store five constants, so the types live in DOC_TYPES below.
// Add an entry there to add a tab - no Python side needed.
// ============================================================

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";
import { formatMonetary } from "@web/views/fields/formatters";

// ============================================================
// DOCUMENT TYPES
// ------------------------------------------------------------
// These mirror exactly the forms this module already restyles
// (see __manifest__ description): PO, vendor bill, customer
// invoice, GRN, journal entry.
//
// `canCreate: false` on GRN is deliberate. stock.picking needs a
// picking_type_id to be usable and there is no correct value to
// hard-code here - it differs per warehouse - so the New button
// is hidden for that tab rather than opening a form that errors
// on save. "Open List" still works and creating from there picks
// up the operation type from the list's own context.
// ============================================================
const DOC_TYPES = [
    {
        key: "purchase_order",
        label: "Purchase Orders",
        icon: "shopping_cart",
        model: "purchase.order",
        domain: [],
        order: "date_order desc",
        canCreate: true,
        createContext: {},
        columns: [
            { field: "name", label: "Reference", type: "char", bold: true },
            { field: "partner_id", label: "Vendor", type: "many2one" },
            { field: "date_order", label: "Order Date", type: "date" },
            { field: "amount_total", label: "Total", type: "monetary", currency: "currency_id" },
            { field: "state", label: "Status", type: "state" },
        ],
    },
    {
        key: "vendor_bill",
        label: "Vendor Bills",
        icon: "article",
        model: "account.move",
        domain: [["move_type", "in", ["in_invoice", "in_refund"]]],
        order: "invoice_date desc, id desc",
        canCreate: true,
        createContext: { default_move_type: "in_invoice" },
        columns: [
            { field: "name", label: "Number", type: "char", bold: true },
            { field: "partner_id", label: "Vendor", type: "many2one" },
            { field: "invoice_date", label: "Bill Date", type: "date" },
            { field: "amount_total", label: "Total", type: "monetary", currency: "currency_id" },
            { field: "state", label: "Status", type: "state" },
        ],
    },
    {
        key: "customer_invoice",
        label: "Customer Invoices",
        icon: "article",
        model: "account.move",
        domain: [["move_type", "in", ["out_invoice", "out_refund"]]],
        order: "invoice_date desc, id desc",
        canCreate: true,
        createContext: { default_move_type: "out_invoice" },
        columns: [
            { field: "name", label: "Number", type: "char", bold: true },
            { field: "partner_id", label: "Customer", type: "many2one" },
            { field: "invoice_date", label: "Invoice Date", type: "date" },
            { field: "amount_total", label: "Total", type: "monetary", currency: "currency_id" },
            { field: "state", label: "Status", type: "state" },
        ],
    },
    {
        key: "grn",
        label: "Goods Receipts",
        icon: "local_shipping",
        model: "stock.picking",
        domain: [["picking_type_code", "=", "incoming"]],
        order: "scheduled_date desc",
        canCreate: false,
        createContext: {},
        columns: [
            { field: "name", label: "Reference", type: "char", bold: true },
            { field: "partner_id", label: "Partner", type: "many2one" },
            { field: "origin", label: "Source", type: "char" },
            { field: "scheduled_date", label: "Scheduled", type: "date" },
            { field: "state", label: "Status", type: "state" },
        ],
    },
    {
        key: "journal_entry",
        label: "Journal Entries",
        icon: "book",
        model: "account.move",
        domain: [["move_type", "=", "entry"]],
        order: "date desc, id desc",
        canCreate: true,
        createContext: { default_move_type: "entry" },
        columns: [
            { field: "name", label: "Number", type: "char", bold: true },
            { field: "ref", label: "Reference", type: "char" },
            { field: "date", label: "Date", type: "date" },
            { field: "amount_total", label: "Total", type: "monetary", currency: "currency_id" },
            { field: "state", label: "Status", type: "state" },
        ],
    },
];

const RECORD_LIMIT = 80;

// ============================================================
// STATE -> BADGE TONE
// ------------------------------------------------------------
// The reference component returned Bootstrap 4 class names
// (`badge-success`, `badge-warning`, ...). Those are dead classes
// in Odoo 17+, which ships Bootstrap 5 - `badge-success` renders
// as an uncoloured grey pill because BS5 renamed them to
// `text-bg-success`. Rather than depend on either naming, the
// tones below map to this module's own classes in
// erp_ui_dashboard.css, so the colours stay correct regardless of
// which Bootstrap the host version carries.
// ============================================================
const STATE_TONES = {
    draft: "muted",
    sent: "warn",
    "to approve": "warn",
    to_approve: "warn",
    waiting: "warn",
    confirmed: "info",
    assigned: "info",
    purchase: "ok",
    posted: "ok",
    done: "ok",
    paid: "ok",
    cancel: "bad",
    cancelled: "bad",
    rejected: "bad",
};

export class ErpUiDashboard extends Component {
    static template = "erp_ui_redesign.ErpUiDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.docTypes = DOC_TYPES;

        // Cache of `state` selection labels, keyed by model name, so the
        // table shows "Purchase Order" rather than the raw "purchase".
        // fields_get is fetched once per model, not once per record.
        this._selectionCache = {};

        this.state = proxy({
            activeKey: null,
            // Kept as two flat maps rather than one map of mixed
            // number-or-sentinel values, because the template would then
            // need `typeof x === 'number'` to tell them apart - and OWL's
            // expression compiler prefixes bare identifiers with the
            // render context, so an unrecognised keyword like `typeof`
            // compiles to `ctx['typeof']` and blows up at render time.
            counts: {},
            denied: {},
            records: [],
            loading: true,
            recordsLoading: false,
            error: null,
        });

        onWillStart(async () => {
            await this._loadCounts();
            const first = this.docTypes.find((t) => !this.state.denied[t.key]);
            if (first) {
                await this._selectType(first.key);
            }
            this.state.loading = false;
        });
    }

    // --------------------------------------------------------
    // Helpers
    // --------------------------------------------------------
    get activeType() {
        return this.docTypes.find((t) => t.key === this.state.activeKey) || null;
    }

    get recordLimit() {
        return RECORD_LIMIT;
    }

    get activeColumns() {
        return this.activeType ? this.activeType.columns : [];
    }

    _readFields(type) {
        const fields = new Set(["id"]);
        for (const col of type.columns) {
            fields.add(col.field);
            if (col.currency) {
                fields.add(col.currency);
            }
        }
        return Array.from(fields);
    }

    // --------------------------------------------------------
    // Data loading
    // --------------------------------------------------------
    async _loadCounts() {
        // Each count is isolated: a user without access to, say,
        // purchase.order should still get a working Bills tab rather
        // than an empty dashboard, so one AccessError marks only that
        // one tab "denied" instead of aborting the whole load.
        await Promise.all(
            this.docTypes.map(async (type) => {
                try {
                    this.state.counts[type.key] = await this.orm.searchCount(
                        type.model,
                        type.domain
                    );
                    this.state.denied[type.key] = false;
                } catch (e) {
                    this.state.counts[type.key] = 0;
                    this.state.denied[type.key] = true;
                }
            })
        );
    }

    async _loadSelection(model) {
        if (this._selectionCache[model]) {
            return this._selectionCache[model];
        }
        try {
            const info = await this.orm.call(model, "fields_get", [["state"], ["selection"]]);
            const map = {};
            for (const [value, label] of (info.state && info.state.selection) || []) {
                map[value] = label;
            }
            this._selectionCache[model] = map;
        } catch (e) {
            this._selectionCache[model] = {};
        }
        return this._selectionCache[model];
    }

    async _selectType(key) {
        const type = this.docTypes.find((t) => t.key === key);
        if (!type) {
            return;
        }
        this.state.activeKey = key;
        this.state.recordsLoading = true;
        this.state.error = null;

        try {
            const [records] = await Promise.all([
                this.orm.searchRead(type.model, type.domain, this._readFields(type), {
                    order: type.order,
                    limit: RECORD_LIMIT,
                }),
                this._loadSelection(type.model),
            ]);
            this.state.records = records;
        } catch (e) {
            this.state.records = [];
            this.state.error =
                "You do not have access to these documents, or they could not be loaded.";
        } finally {
            this.state.recordsLoading = false;
        }
    }

    async _refresh() {
        await this._loadCounts();
        if (this.state.activeKey) {
            await this._selectType(this.state.activeKey);
        }
    }

    // --------------------------------------------------------
    // Cell rendering
    // --------------------------------------------------------
    formatCell(record, col) {
        const raw = record[col.field];
        if (raw === false || raw === undefined || raw === null || raw === "") {
            return "-";
        }
        switch (col.type) {
            case "many2one":
                return Array.isArray(raw) ? raw[1] : raw;
            case "date":
                // searchRead returns "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS";
                // the date half is all this table shows either way.
                return String(raw).split(" ")[0];
            case "monetary": {
                const currency = col.currency ? record[col.currency] : false;
                const currencyId = Array.isArray(currency) ? currency[0] : false;
                try {
                    return formatMonetary(raw, { currencyId });
                } catch (e) {
                    // Guard only against the formatter's import surface
                    // shifting between versions - the number still shows.
                    return Number(raw).toFixed(2);
                }
            }
            case "state":
                return this.stateLabel(record);
            default:
                return raw;
        }
    }

    stateLabel(record) {
        const type = this.activeType;
        if (!type) {
            return record.state;
        }
        const map = this._selectionCache[type.model] || {};
        return map[record.state] || record.state;
    }

    stateBadgeClass(record) {
        const value = String(record.state || "").toLowerCase().trim();
        const tone = STATE_TONES[value] || "muted";
        return `o_erp_dash_badge o_erp_dash_badge_${tone}`;
    }

    isNumeric(col) {
        return col.type === "monetary";
    }

    // --------------------------------------------------------
    // Actions
    // --------------------------------------------------------
    async _openRecord(recordId) {
        const type = this.activeType;
        if (!type) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: type.label,
            res_model: type.model,
            view_mode: "form",
            views: [[false, "form"]],
            res_id: recordId,
            target: "current",
        });
    }

    async _openFullList() {
        const type = this.activeType;
        if (!type) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: type.label,
            res_model: type.model,
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: type.domain,
            context: type.createContext,
            target: "current",
        });
    }

    async _createNew() {
        const type = this.activeType;
        if (!type || !type.canCreate) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: `New ${type.label}`,
            res_model: type.model,
            view_mode: "form",
            views: [[false, "form"]],
            context: type.createContext,
            target: "current",
        });
    }
}

registry.category("actions").add("erp_ui_redesign_dashboard", ErpUiDashboard);
