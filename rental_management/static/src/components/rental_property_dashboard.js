/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class RentalPropertyDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = proxy({
            'property_data': {},
            isDashboardVisible: localStorage.getItem("rental_dashboard_visible") === "true",
        })
        onWillStart(async ()=>{
            const data = await this.orm.call('property.details', 'retrieve_list_dashboard_data', []);
            this.state.property_data = data
        })
    }

    toggleDashboard() {
        this.state.isDashboardVisible = !this.state.isDashboardVisible;
        localStorage.setItem("rental_dashboard_visible", this.state.isDashboardVisible);
    }
    viewAllProperties(status){
        let domain, context;
        if (status === 'all') {
           domain = [['stage', '!=', 'draft']]
        } else {
            domain = [['stage', '=', status]]
        }
        context = { 'create': true }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Properties',
            res_model: 'property.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: context,
            domain: domain,
        });
    }
    viewForRentProperties(type){
        let domain, context;
        if (type === 'all') {
           domain = [['stage','=','available'],['sale_lease','=','for_tenancy']]
        } else {
            domain = [['stage','=','available'],['sale_lease','=','for_tenancy'],['type','=', type]]
        }
        context = { 'create': true }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Properties',
            res_model: 'property.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: context,
            domain: domain,
        });
    }
    viewProperties(status, type){
        let domain, context;
        if (status === 'all') {
           domain = [['stage', '!=', 'draft'],['type','=',type]]
        } else {
            domain = [['stage', '=', status],['type','=', type]]
        }
        context = { 'create': true }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Properties',
            res_model: 'property.details',
            view_mode: 'list',
            views: [[false, 'list'], [false, 'kanban'], [false, 'form']],
            target: 'current',
            context: context,
            domain: domain,
        });
    }
}

RentalPropertyDashboard.template = 'rental_management.RentalPropertyDashboard';
