/** @odoo-module **/

import { Component, proxy } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

/**
 * Liquid Glass appearance: dark (original), light, or same as device.
 * The choice is stored per user (res.users.lg_color_scheme), delivered in
 * session_info, and cached in localStorage so the next load starts right.
 */
const STORAGE_KEY = "lg_color_scheme";
const SCHEMES = ["dark", "light", "system"];
const deviceLight = window.matchMedia("(prefers-color-scheme: light)");

function readCache() {
    try {
        return localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

function writeCache(mode) {
    try {
        localStorage.setItem(STORAGE_KEY, mode);
    } catch {
        // private window / blocked storage: the server value is enough
    }
}

function isLight(mode) {
    return mode === "light" || (mode === "system" && deviceLight.matches);
}

function applyScheme(mode) {
    document.documentElement.classList.toggle("o_lg_light", isLight(mode));
}

// Apply as early as possible (module load), before the web client mounts.
const initial = SCHEMES.includes(session.lg_color_scheme)
    ? session.lg_color_scheme
    : SCHEMES.includes(readCache())
      ? readCache()
      : "dark";
applyScheme(initial);

export const lgColorSchemeService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        const state = proxy({ mode: initial });
        writeCache(initial);

        deviceLight.addEventListener("change", () => {
            if (state.mode === "system") {
                applyScheme(state.mode);
            }
        });

        return {
            state,
            async setMode(mode) {
                if (!SCHEMES.includes(mode) || mode === state.mode) {
                    return;
                }
                state.mode = mode;
                applyScheme(mode);
                writeCache(mode);
                await orm.call("res.users", "lg_set_color_scheme", [mode]);
            },
        };
    },
};

registry.category("services").add("lg_color_scheme", lgColorSchemeService);

export class LgColorSchemeToggle extends Component {
    static template = "theme_liquid_glass.ColorSchemeToggle";
    static components = { Dropdown, DropdownItem };

    setup() {
        this.scheme = useService("lg_color_scheme");
        this.options = [
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
            { value: "system", label: "Same as device" },
        ];
    }

    get mode() {
        return this.scheme.state.mode;
    }

    get shownIcon() {
        return this.mode === "system" ? "system" : isLight(this.mode) ? "light" : "dark";
    }
}

registry
    .category("systray")
    .add("theme_liquid_glass.color_scheme", { Component: LgColorSchemeToggle }, { sequence: 1 });
