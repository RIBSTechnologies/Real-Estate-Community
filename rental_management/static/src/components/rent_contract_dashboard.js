/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class RentalContractDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = proxy({
            'tenancy_data': {},
            isDashboardVisible: localStorage.getItem("rental_contract_dashboard_visible") === "true",
        })
        onWillStart(async ()=>{
            const data = await this.orm.call('tenancy.details', 'retrieve_contract_list_dashboard_data', []);
            this.state.tenancy_data = data
        })
    }

    toggleDashboard() {
        this.state.isDashboardVisible = !this.state.isDashboardVisible;
        localStorage.setItem("rental_contract_dashboard_visible", this.state.isDashboardVisible);
    }
    async viewContract(field, type) {
        let domain, context;
        domain = [[field, '=', type]]
        context = { 'create': false }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Contracts',
            res_model: 'tenancy.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: context,
            domain: domain,
        });
    }
}

RentalContractDashboard.template = 'rental_management.RentalContractDashboard';
