/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

/**
 * Rebuild of rental_management's "Statistics" screen.
 *
 * It exists here so the page is available on every database, even the ones
 * running a rental_management build that never shipped that menu.  All the
 * numbers come from property.dashboard.get_statistics_data() and every card
 * drills through to the underlying list view.
 */
export class PropertyStatistics extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = proxy({
            loading: true,
            error: false,
            sections: [],
            currency: "",
            documentsModel: "",
        });

        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const d = await this.orm.call("property.dashboard", "get_statistics_data", []);
            this.state.sections = d.sections || [];
            this.state.currency = d.currency_symbol || "";
            this.state.documentsModel = d.documents_model || "";
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || (e && e.message) || String(e);
            this.state.sections = [];
        }
        this.state.loading = false;
    }

    fmt(v) {
        if (v === undefined || v === null || isNaN(v)) return "0";
        const n = Math.abs(parseFloat(v));
        return (v < 0 ? "-" : "") + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    display(card) {
        return card.money ? `${this.state.currency} ${this.fmt(card.value)}` : this.fmt(card.value);
    }

    openCard(card) {
        if (!card.model) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: card.label,
            res_model: card.model,
            domain: card.domain || [],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }
}

PropertyStatistics.template = "property_dashboard.Statistics";

registry.category("actions").add("property_dashboard.statistics", PropertyStatistics);
