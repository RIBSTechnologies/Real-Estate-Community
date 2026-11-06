/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AnalyticDistribution } from "@analytic/components/analytic_distribution/analytic_distribution";

patch(AnalyticDistribution.prototype, {
    recordProps(line) {
        const props = super.recordProps(line);

        const buildingPlan = this.allPlans.find(
            (p) => p.customized_type === "building" || p.name?.toLowerCase() === "building"
        );
        const unitPlan = this.allPlans.find(
            (p) => p.customized_type === "units" || p.name?.toLowerCase() === "units"
        );

        if (buildingPlan && unitPlan) {
            const buildingCol = this.planIdToColumn[buildingPlan.id];
            const unitCol = this.planIdToColumn[unitPlan.id];

            if (props.fields && props.fields[unitCol]) {
                // Return dynamic domain function evaluated on every dropdown open, search, and search-more
                props.fields[unitCol].domain = () => {
                    const baseDomain = [["root_plan_id", "=", unitPlan.id]];

                    // Determine building account id on this line
                    const buildingAcc = line.analyticAccounts?.find(
                        (a) => a.planId === buildingPlan.id
                    );
                    let buildingId = buildingAcc?.accountId;

                    if (!buildingId && props.values && props.values[buildingCol]) {
                        buildingId = props.values[buildingCol];
                    }

                    if (Array.isArray(buildingId)) {
                        buildingId = buildingId[0];
                    } else if (typeof buildingId === "object" && buildingId !== null) {
                        buildingId = buildingId.id || false;
                    }

                    if (buildingId) {
                        return [...baseDomain, ["building_account_id", "=", buildingId]];
                    }
                    return baseDomain;
                };
            }
        }

        const costCenterPlan = this.allPlans.find((p) => p.name?.toLowerCase() === "cost center");
        const subCostCenterPlan = this.allPlans.find(
            (p) => p.name?.toLowerCase() === "sub cost center"
        );

        if (costCenterPlan && subCostCenterPlan) {
            const costCenterCol = this.planIdToColumn[costCenterPlan.id];
            const subCostCenterCol = this.planIdToColumn[subCostCenterPlan.id];

            if (props.fields && props.fields[subCostCenterCol]) {
                // Same pattern as Building/Unit above: restrict Sub Cost
                // Center choices to the department linked (via
                // cost_center_account_id) to whichever Cost Center is
                // picked on this line.
                props.fields[subCostCenterCol].domain = () => {
                    const baseDomain = [["root_plan_id", "=", subCostCenterPlan.id]];

                    const costCenterAcc = line.analyticAccounts?.find(
                        (a) => a.planId === costCenterPlan.id
                    );
                    let costCenterId = costCenterAcc?.accountId;

                    if (!costCenterId && props.values && props.values[costCenterCol]) {
                        costCenterId = props.values[costCenterCol];
                    }

                    if (Array.isArray(costCenterId)) {
                        costCenterId = costCenterId[0];
                    } else if (typeof costCenterId === "object" && costCenterId !== null) {
                        costCenterId = costCenterId.id || false;
                    }

                    if (costCenterId) {
                        return [...baseDomain, ["cost_center_account_id", "=", costCenterId]];
                    }
                    return baseDomain;
                };
            }
        }

        return props;
    },

    async lineChanged(record, changes, line) {
        const res = await super.lineChanged(record, changes, line);

        const buildingPlan = this.allPlans.find(
            (p) => p.customized_type === "building" || p.name?.toLowerCase() === "building"
        );
        const unitPlan = this.allPlans.find(
            (p) => p.customized_type === "units" || p.name?.toLowerCase() === "units"
        );

        if (buildingPlan && unitPlan) {
            const buildingCol = this.planIdToColumn[buildingPlan.id];
            const unitCol = this.planIdToColumn[unitPlan.id];

            // If building changed on this row, reset the unit selection -
            // but not when the unit is ALSO part of this same batch of
            // changes (e.g. picking Building then Unit on a freshly added
            // line can land in one lineChanged call): that's the user
            // setting both at once, not switching building out from under
            // an already-picked unit, so it must not be wiped out here.
            if (changes && buildingCol in changes && !(unitCol in changes)) {
                const unitAcc = line.analyticAccounts?.find(
                    (a) => a.planId === unitPlan.id
                );
                if (unitAcc && unitAcc.accountId) {
                    unitAcc.accountId = false;
                    unitAcc.accountDisplayName = "";
                    if (record && record.update) {
                        await record.update({ [unitCol]: false });
                    }
                }
            }
        }

        const costCenterPlan = this.allPlans.find((p) => p.name?.toLowerCase() === "cost center");
        const subCostCenterPlan = this.allPlans.find(
            (p) => p.name?.toLowerCase() === "sub cost center"
        );

        if (costCenterPlan && subCostCenterPlan) {
            const costCenterCol = this.planIdToColumn[costCenterPlan.id];
            const subCostCenterCol = this.planIdToColumn[subCostCenterPlan.id];

            // Same reset rule as Building/Unit: only when Cost Center
            // changed alone, not when Sub Cost Center is being set in the
            // same batch of changes.
            if (changes && costCenterCol in changes && !(subCostCenterCol in changes)) {
                const subCostCenterAcc = line.analyticAccounts?.find(
                    (a) => a.planId === subCostCenterPlan.id
                );
                if (subCostCenterAcc && subCostCenterAcc.accountId) {
                    subCostCenterAcc.accountId = false;
                    subCostCenterAcc.accountDisplayName = "";
                    if (record && record.update) {
                        await record.update({ [subCostCenterCol]: false });
                    }
                }
            }
        }

        return res;
    },

    /**
     * Copy button on each popup row: inserts an exact copy of the row (same
     * accounts in every plan column, same percentage) right below it.
     */
    copyLine(index) {
        const line = this.state.formattedData[index];
        if (!line) {
            return;
        }
        const copy = {
            ...line,
            id: this.nextId++,
            analyticAccounts: line.analyticAccounts.map((account) => ({ ...account })),
        };
        this.state.formattedData.splice(index + 1, 0, copy);
        this.setFocusSelector(`[name=line_${index + 1}] td:first-of-type`);
    },
});
