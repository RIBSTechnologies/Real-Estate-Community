/** @odoo-module **/
// ============================================================
// Click-through for the 6 new "Portfolio Overview" tiles added to the
// Dashboard (rental_management.rental_dashboard) by
// rental_dashboard_portfolio_overview.xml. Same
// this.action.doAction({...}) shape RentalDashboard's own
// viewPropertyTenancies/viewDocs/etc. already use - just a new handler
// for the new tiles, since none of the existing ones cover
// property.project or the "parking" property.details subtype.
//
// A parking unit is a property.details record whose Sub Type is
// "Parking" - matches the domain used server-side in
// al_shafar_extended/models/property_details.py (get_property_stats).
// ============================================================

import { RentalDashboard } from "@rental_management/js/rental";
import { patch } from "@web/core/utils/patch";

const PARKING_SUBTYPE_DOMAIN = [['property_subtype_id.name', 'ilike', 'parking']];
const NOT_PARKING_SUBTYPE_DOMAIN = [['property_subtype_id.name', 'not ilike', 'parking']];

// Single/Multi Unit CONTRACTS breakdown (Normal Units / Parking Units
// cards) - mirrors al_shafar_extended/models/property_details.py
// (get_property_stats) exactly, so the count shown on the tile always
// matches the number of records this click-through opens:
// - Single: classified by its one unit's (property_id's) subtype.
// - Multi: classified as Parking only if ALL of its units are
//   parking-subtype (a multi-contract can genuinely mix a few apartments
//   with a few parking slots in one lease - one non-parking unit is
//   enough to make the whole contract count as Normal). Keep this in
//   sync with the server-side rule if it ever changes.
// Returns the *contract* ids for the requested bucket, so the resulting
// list is tenancy.details (contracts), not property.details (units).
async function classifyContractsByType(orm, isMulti) {
    const contracts = await orm.searchRead(
        'tenancy.details',
        isMulti
            ? [['is_multi_contract', '=', true]]
            : [['is_multi_contract', '=', false], ['property_id', '!=', false]],
        isMulti ? ['unit_ids'] : ['property_id']
    );
    // unit_ids (Many2many) comes back as a plain array of ids;
    // property_id (Many2one) comes back as [id, display_name] or false -
    // normalise both to "the unit ids this contract needs classified".
    const unitIdsByContract = new Map();
    const allUnitIds = new Set();
    for (const rec of contracts) {
        const ids = isMulti
            ? (rec.unit_ids || [])
            : (rec.property_id ? [rec.property_id[0]] : []);
        unitIdsByContract.set(rec.id, ids);
        ids.forEach((id) => allUnitIds.add(id));
    }

    const units = allUnitIds.size
        ? await orm.searchRead('property.details', [['id', 'in', [...allUnitIds]]], ['property_subtype_id'])
        : [];
    const isParkingUnit = new Map(units.map((u) => [
        u.id,
        Boolean(u.property_subtype_id && u.property_subtype_id[1] && u.property_subtype_id[1].toLowerCase().includes('parking')),
    ]));

    const normalIds = [];
    const parkingIds = [];
    for (const [contractId, unitIds] of unitIdsByContract.entries()) {
        const isParkingContract = unitIds.length > 0 && unitIds.every((id) => isParkingUnit.get(id));
        (isParkingContract ? parkingIds : normalIds).push(contractId);
    }
    return { normalIds, parkingIds };
}

patch(RentalDashboard.prototype, {
    async viewPortfolioOverview(type) {
        let model = 'property.details';
        let domain = [];
        switch (type) {
            case 'total_properties':
                model = 'property.project';
                break;
            case 'total_units':
                break;
            case 'total_parking':
                domain = PARKING_SUBTYPE_DOMAIN;
                break;
            case 'available_units':
                domain = [['stage', '=', 'available']];
                break;
            case 'occupied_units':
                domain = [['stage', '=', 'on_lease']];
                break;
            case 'occupied_parking':
                domain = [...PARKING_SUBTYPE_DOMAIN, ['stage', '=', 'on_lease']];
                break;
            case 'normal_units':
                domain = NOT_PARKING_SUBTYPE_DOMAIN;
                break;
            case 'normal_on_rent':
                domain = [...NOT_PARKING_SUBTYPE_DOMAIN, ['stage', '=', 'on_lease']];
                break;
            case 'normal_available':
                domain = [...NOT_PARKING_SUBTYPE_DOMAIN, ['stage', '=', 'available']];
                break;
            case 'parking_on_rent':
                domain = [...PARKING_SUBTYPE_DOMAIN, ['stage', '=', 'on_lease']];
                break;
            case 'parking_available':
                domain = [...PARKING_SUBTYPE_DOMAIN, ['stage', '=', 'available']];
                break;
            case 'normal_single_contracts':
            case 'normal_multi_contracts':
            case 'parking_single_contracts':
            case 'parking_multi_contracts': {
                const isMulti = type.includes('multi');
                const isParking = type.startsWith('parking');
                const { normalIds, parkingIds } = await classifyContractsByType(this.env.services.orm, isMulti);
                model = 'tenancy.details';
                domain = [['id', 'in', isParking ? parkingIds : normalIds]];
                break;
            }
            default:
                return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            view_mode: 'list',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
            context: { create: false },
            domain: domain,
        });
    },
});
