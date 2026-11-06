/** @odoo-module **/

import { x2ManyCommands } from "@web/core/orm_plugin";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Set first: they drive onchanges (product -> label, price, account, taxes).
const BASE_FIELDS = ["display_type", "product_id", "product_uom_id", "currency_id", "partner_id"];
// Then the line's own values, re-applied after those onchanges.
const VALUE_FIELDS = [
    "account_id", "name", "quantity", "price_unit", "discount",
    "date_maturity", "deferred_start_date", "deferred_end_date", "analytic_distribution",
];
// Journal Items only: on invoice lines the amounts follow from price/qty.
const AMOUNT_FIELDS = ["debit", "credit", "amount_currency"];

/**
 * Copy icon next to the delete icon on every invoice / bill line and, on
 * journal entries, every journal item - same as the copy icon on the
 * analytic distribution popup rows. Inserts an exact copy of the line
 * right below it. Draft entries only; on invoices the Journal Items are
 * generated from the invoice lines, so they get no copy icon there.
 */
patch(ListRenderer.prototype, {
    canCopyMoveLine(record) {
        const list = this.props.list;
        const parent = record._parentRecord;
        if (list.resModel !== "account.move.line" || !parent || parent.resModel !== "account.move") {
            return false;
        }
        if (parent.data.state !== "draft" || this.props.readonly) {
            return false;
        }
        if (["line_section", "line_note"].includes(record.data.display_type)) {
            return false;
        }
        return list === parent.data.invoice_line_ids
            || (list === parent.data.line_ids && parent.data.move_type === "entry");
    },

    _pickMoveLineValues(record, names) {
        const values = {};
        for (const name of names) {
            if (name in this.props.list.activeFields && name in record.data) {
                values[name] = record.data[name];
            }
        }
        return values;
    },

    async onCopyMoveLine(record) {
        const list = this.props.list;
        const isInvoiceLine = "price_unit" in list.activeFields;
        const baseValues = this._pickMoveLineValues(record, BASE_FIELDS);
        const lineValues = this._pickMoveLineValues(
            record, isInvoiceLine ? VALUE_FIELDS : [...VALUE_FIELDS, ...AMOUNT_FIELDS]
        );
        const taxIds = "tax_ids" in list.activeFields && record.data.tax_ids
            ? record.data.tax_ids.records.map((tax) => tax.resId)
            : null;

        const copy = await list.addNewRecord({ position: "bottom", mode: "readonly" });
        if (Object.keys(baseValues).length) {
            await copy.update(baseValues);
        }
        // fresh object per call: update() replaces the tax command in the
        // object it is given with its own list
        const values = () => (
            taxIds ? { ...lineValues, tax_ids: [x2ManyCommands.set(taxIds)] } : { ...lineValues }
        );
        await copy.update(values());
        // onchanges of the step above (account -> taxes, taxes -> amounts)
        // may have changed the line's own values: put them back
        await copy.update(values());
        if (list.canResequence()) {
            await list.resequence(copy.id, record.id);
        }
    },
});
