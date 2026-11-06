/** @odoo-module **/
// ============================================================
// Click-through for the 7 "Expiring Soon Contracts" day-range tiles added
// by rental_dashboard_expiring_soon_days.xml. Same viewPropertyTenancies
// (type) method every tile on this dashboard already calls; type is one
// of the non-overlapping bucket keys below (matching
// tenancy.details._EXPIRING_SOON_DAY_BUCKETS / the counts computed in
// al_shafar_extended/models/property_details.py) - each contract falls
// into exactly one bucket, so the 7 tiles' domains are mutually
// exclusive and sum to the full "Expiring Soon" total.
//
// Stacks on top of the other viewPropertyTenancies patches
// (rental_dashboard_contract_statics.js in this module,
// rental_dashboard_contract_types.js in ribs_real_estate) via the same
// super() fallback chain - order-independent, each patch only claims the
// type strings it recognises.
// ============================================================

import { RentalDashboard } from "@rental_management/js/rental";
import { patch } from "@web/core/utils/patch";

const EXPIRING_SOON_BUCKET_DOMAINS = {
    expiring_0_60: { label: '0-60 Days', domain: [['days_left', '<=', 60]] },
    expiring_60_90: { label: '60-90 Days', domain: [['days_left', '>', 60], ['days_left', '<=', 90]] },
    expiring_90_100: { label: '90-100 Days', domain: [['days_left', '>', 90], ['days_left', '<=', 100]] },
    expiring_100_120: { label: '100-120 Days', domain: [['days_left', '>', 100], ['days_left', '<=', 120]] },
    expiring_120_140: { label: '120-140 Days', domain: [['days_left', '>', 120], ['days_left', '<=', 140]] },
    expiring_140_160: { label: '140-160 Days', domain: [['days_left', '>', 140], ['days_left', '<=', 160]] },
    expiring_160_plus: { label: '160+ Days', domain: [['days_left', '>', 160]] },
};

patch(RentalDashboard.prototype, {
    viewPropertyTenancies(type) {
        const bucket = EXPIRING_SOON_BUCKET_DOMAINS[type];
        if (bucket) {
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: `Expiring Soon (${bucket.label})`,
                res_model: 'tenancy.details',
                view_mode: 'list',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
                context: { create: false },
                domain: [['contract_type', '=', 'expiring_soon'], ...bucket.domain],
            });
            return;
        }
        super.viewPropertyTenancies(type);
    },
});
