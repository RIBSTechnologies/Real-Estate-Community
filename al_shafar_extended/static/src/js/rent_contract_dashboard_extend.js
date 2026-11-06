/** @odoo-module **/
// ============================================================
// Extends the "Contracts | Status | Payment Terms" bar embedded above the
// All Contracts list view (rental_management's RentalContractDashboard,
// static/src/components/rent_contract_dashboard.js) with two new click
// handlers used by the template extension in
// rent_contract_dashboard_extend.xml:
//   - viewAllContracts(): the new "Total" tile in the Status section.
//   - viewExpiringSoonBucket(): each tile in the "Expiring Soon
//     Contracts" section that replaces Payment Terms, filtered by
//     contract_type='expiring_soon' plus a days_left range.
// The existing viewContract(field, type) handler only supports an exact-
// match domain [[field, '=', type]], which can't express "no filter" or
// a range - hence these two additions, following the exact same
// this.action.doAction(...) pattern it already uses. Both data keys
// (total_contract_count, expiring_*_count) come from the backend
// override in al_shafar_extended/models/tenancy_details.py
// (retrieve_contract_list_dashboard_data) - no new business logic here,
// only navigation wiring identical in shape to every other tile.
// ============================================================

import { RentalContractDashboard } from "@rental_management/components/rent_contract_dashboard";
import { patch } from "@web/core/utils/patch";

patch(RentalContractDashboard.prototype, {
    /** "Total" tile: every contract, no filter. */
    viewAllContracts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'All Contracts',
            res_model: 'tenancy.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: { create: false },
            domain: [],
        });
    },

    /**
     * One "Expiring Soon Contracts" bucket tile. minDays/maxDays are the
     * bucket's (exclusive lower, inclusive upper) days_left bounds -
     * pass null for whichever side is open-ended (the two boundary
     * buckets: "<= 60" and "> 160").
     */
    viewExpiringSoonBucket(minDays, maxDays, label) {
        const domain = [['contract_type', '=', 'expiring_soon']];
        if (minDays !== null) {
            domain.push(['days_left', '>', minDays]);
        }
        if (maxDays !== null) {
            domain.push(['days_left', '<=', maxDays]);
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: label,
            res_model: 'tenancy.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: { create: false },
            domain: domain,
        });
    },
});
