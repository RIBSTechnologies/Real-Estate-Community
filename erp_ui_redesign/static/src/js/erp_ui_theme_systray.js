/** @odoo-module **/
// ============================================================
// ERP UI Redesign - "Choose Theme" systray icon
// ------------------------------------------------------------
// A single icon button in the navbar, open to every internal user (not
// gated behind base.group_system like the full Settings screen). Clicking
// it opens erp.ui.theme.quickswitch as a normal target="new" dialog - the
// same window-action machinery every other Odoo popup uses - rather than a
// hand-built dropdown/popover, so it renders exactly like any other Odoo
// dialog (title bar, X to close, footer buttons) with no extra CSS to
// maintain here.
// ============================================================

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ErpUiThemeSystray extends Component {
    static template = "erp_ui_redesign.ThemeSystray";

    setup() {
        this.actionService = useService("action");
    }

    async onClickChooseTheme() {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Choose Theme",
            res_model: "erp.ui.theme.quickswitch",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
    }
}

registry.category("systray").add(
    "erp_ui_redesign.ThemeSystray",
    { Component: ErpUiThemeSystray },
    { sequence: 1 }
);
