/** @odoo-module **/
// ============================================================
// Adds a 'total_contracts' case to RentalDashboard's existing
// viewPropertyTenancies(type) - the same click-through method every tile
// in "Rent Contract Statics" already calls - for the new "Total
// Contracts" tile added by rental_dashboard_contract_statics.xml.
// "Active Contracts" needs no JS change: its type ('running_contract')
// already falls through to the base method's generic
// domain = [['contract_type', '=', type]] branch.
//
// Also adds 'single_unit_contracts'/'multi_unit_contracts' (the new
// "Contract Portfolio" tiles - per-contract is_multi_contract counts) and
// an 'expired' case to viewDocs(type) (the new "Documents Expired" tile -
// the base method only ever implemented 'pending').
//
// Same patch shape ribs_real_estate/static/src/js/
// rental_dashboard_contract_types.js already uses on this exact method
// (extra `if` branch + super.viewPropertyTenancies(type) fallback), so
// both patches compose regardless of load order.
// ============================================================

import { RentalDashboard } from "@rental_management/js/rental";
import { patch } from "@web/core/utils/patch";

patch(RentalDashboard.prototype, {
    viewPropertyTenancies(type) {
        if (type === 'total_contracts') {
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'Contracts',
                res_model: 'tenancy.details',
                view_mode: 'list',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
                context: { create: false },
                domain: [],
            });
            return;
        }
        if (type === 'single_unit_contracts' || type === 'multi_unit_contracts') {
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: type === 'single_unit_contracts' ? 'Single Unit Contracts' : 'Multi-Unit Contracts',
                res_model: 'tenancy.details',
                view_mode: 'list',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
                context: { create: false },
                domain: [['is_multi_contract', '=', type === 'multi_unit_contracts']],
            });
            return;
        }
        super.viewPropertyTenancies(type);
    },

    viewDocs(type) {
        if (type === 'expired') {
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'Documents Expired',
                res_model: 'partner.documents',
                view_mode: 'list',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
                context: { create: false },
                domain: [['verified_status', '=', 'expired']],
            });
            return;
        }
        super.viewDocs(type);
    },
});
