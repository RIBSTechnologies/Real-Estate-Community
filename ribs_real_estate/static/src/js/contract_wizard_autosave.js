/** @odoo-module **/
/**
 * Auto-save the Contract Wizard.
 *
 * `contract.wizard` is a TransientModel shown in a dialog, so nothing reaches
 * the database until a button is pressed.  This patch snapshots the form every
 * few seconds (and once more when the dialog is destroyed) into `contract.draft`,
 * from where `default_get` restores it on the next open.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";
import { serializeDate, serializeDateTime } from "@web/core/l10n/dates";
import { onWillDestroy } from "@odoo/owl";

const DRAFT_MODEL = "contract.wizard";
const AUTOSAVE_INTERVAL = 3000; // ms
const RESUME_AFTER_BUTTON = 15000; // ms

const SKIP_FIELDS = new Set([
    "id",
    "display_name",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "company_id",
    "currency_id",
    "ribs_draft_id",
    "ribs_draft_restored",
]);

function serializeRecord(record) {
    const values = {};
    const fieldDefs = record.fields || {};
    for (const name in fieldDefs) {
        if (SKIP_FIELDS.has(name)) {
            continue;
        }
        const def = fieldDefs[name];
        const value = record.data[name];
        if (value === undefined) {
            continue;
        }
        try {
            switch (def.type) {
                case "many2one": {
                    if (!value) {
                        values[name] = false;
                    } else if (Array.isArray(value)) {
                        values[name] = value[0] || false;
                    } else if (typeof value === "object") {
                        values[name] = value.id || value.resId || false;
                    } else {
                        values[name] = value;
                    }
                    break;
                }
                case "many2many": {
                    const ids = (value && value.currentIds) || [];
                    values[name] = [...ids].filter((id) => Number.isInteger(id) && id > 0);
                    break;
                }
                case "one2many": {
                    const lines = (value && value.records) || [];
                    values[name] = lines.map((line) => serializeRecord(line));
                    break;
                }
                case "date": {
                    values[name] = value ? serializeDate(value) : false;
                    break;
                }
                case "datetime": {
                    values[name] = value ? serializeDateTime(value) : false;
                    break;
                }
                case "binary":
                case "reference":
                    break;
                default: {
                    values[name] = value === undefined ? false : value;
                }
            }
        } catch (error) {
            console.warn(`[ribs_real_estate] cannot serialize field ${name}`, error);
        }
    }
    return values;
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.resModel !== DRAFT_MODEL) {
            return;
        }
        this.ribsDraftOrm = useService("orm");
        this.ribsDraftSkip = false;

        const context = this.props.context || {};
        this.ribsDraftKeys = {
            propertyId:
                context.ribs_property_id ||
                (context.active_model === "property.details" ? context.active_id : false) ||
                false,
            contractId:
                context.active_contract_id ||
                (context.active_model === "tenancy.details" ? context.active_id : false) ||
                false,
        };

        this.ribsDraftTimer = setInterval(() => this.ribsSaveDraft(), AUTOSAVE_INTERVAL);

        onWillDestroy(() => {
            clearInterval(this.ribsDraftTimer);
            // fire and forget - the page is not unloading when a dialog closes
            this.ribsSaveDraft();
        });
    },

    async ribsSaveDraft() {
        if (this.props.resModel !== DRAFT_MODEL || this.ribsDraftSkip) {
            return;
        }
        const record = this.model && this.model.root;
        if (!record) {
            return;
        }
        try {
            const payload = serializeRecord(record);
            const propertyId = this.ribsDraftKeys.propertyId || payload.property_id || false;
            await this.ribsDraftOrm.call("contract.draft", "store_draft", [
                payload,
                propertyId,
                this.ribsDraftKeys.contractId,
            ]);
        } catch (error) {
            // autosave must never disturb the user
            console.warn("[ribs_real_estate] contract draft autosave failed", error);
        }
    },

    /**
     * When the user actually submits (or explicitly discards) the wizard the
     * draft is handled server-side, so stop autosaving - otherwise the dialog
     * being destroyed would immediately write the draft back.
     */
    async beforeExecuteActionButton(clickParams) {
        if (
            this.props.resModel === DRAFT_MODEL &&
            ["contract_action", "action_clear_draft"].includes(clickParams.name)
        ) {
            this.ribsDraftSkip = true;
            // if the server raised an error the dialog stays open: resume later
            setTimeout(() => {
                this.ribsDraftSkip = false;
            }, RESUME_AFTER_BUTTON);
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});
