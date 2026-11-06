/** @odoo-module **/

import { SearchPanel } from "@web/search/search_panel/search_panel";
import { patch } from "@web/core/utils/patch";

/**
 * Patch SearchPanel so that the sidebar starts COLLAPSED for all views that
 * have a searchpanel (Building Type / Unit Type side filter bar).
 *
 * Behavior:
 *  - First time a user opens any list view with a searchpanel → sidebar is CLOSED
 *  - User clicks the «/» toggle → sidebar opens (Odoo saves their preference)
 *  - On the next visit to the same action, their saved preference is respected
 */
patch(SearchPanel.prototype, {
    setup() {
        super.setup(...arguments);

        // Only collapse if no previously saved state was imported for this action.
        // This way, once the user manually opens the sidebar, their preference is
        // remembered by Odoo's exportState / importState mechanism.
        if (!this.hasImportedState) {
            this.state.sidebarExpanded = false;
        }
    },
});
