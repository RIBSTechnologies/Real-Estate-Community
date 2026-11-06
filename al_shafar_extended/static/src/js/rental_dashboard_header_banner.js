/** @odoo-module **/
// ============================================================
// Backs the banner added to the top of the Dashboard
// (rental_management.rental_dashboard) by
// rental_dashboard_header_banner.xml: company logo/name (dynamic - the
// currently active company, not hardcoded), a static title/tagline, and
// a cosmetic "As of <today>" date label (no filtering - just a display,
// same as the reference design).
// ============================================================

import { RentalDashboard } from "@rental_management/js/rental";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";

const { DateTime } = luxon;

patch(RentalDashboard.prototype, {
    get dashboardCompanyName() {
        return user.activeCompany?.name || "";
    },

    get dashboardCompanyLogoUrl() {
        const companyId = user.activeCompany?.id;
        return companyId ? `/web/image/res.company/${companyId}/logo` : "";
    },

    get dashboardAsOfDate() {
        return DateTime.local().toFormat("dd MMM yyyy");
    },
});
