/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";

function getCurrentPosition() {
    return new Promise((resolve, reject) => {
        if (!browser.navigator.geolocation) {
            reject(new Error(_t("Geolocation is not supported by this browser.")));
            return;
        }
        browser.navigator.geolocation.getCurrentPosition(
            (position) => resolve(position.coords),
            (error) => reject(error),
            { enableHighAccuracy: true, timeout: 10000 }
        );
    });
}

export class MissionGeoActionButton extends Component {
    static template = "ibs_hr_permission.MissionGeoActionButton";
    static props = { ...standardWidgetProps, method: String, label: String };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async onClick() {
        if (!this.props.record.resId) {
            const saved = await this.props.record.save();
            if (!saved) {
                return;
            }
        }
        let coords;
        try {
            coords = await getCurrentPosition();
        } catch (error) {
            this.notification.add(
                _t("Could not get your location: %(reason)s", { reason: error.message }),
                { type: "danger" }
            );
            return;
        }
        await this.orm.call(
            this.props.record.resModel,
            this.props.method,
            [[this.props.record.resId]],
            { latitude: coords.latitude, longitude: coords.longitude }
        );
        await this.props.record.load();
        this.render();
    }
}

registry.category("view_widgets").add("ibs_mission_geo_button", {
    component: MissionGeoActionButton,
    extractProps: ({ attrs }) => ({
        method: attrs.method,
        label: attrs.label,
    }),
});
