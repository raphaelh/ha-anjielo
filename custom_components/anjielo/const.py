"""Constants for the Anjielo integration."""

DOMAIN = "anjielo"

CONF_RTSP_PORT = "rtsp_port"

DEFAULT_PORT = 8565
DEFAULT_RTSP_PORT = 8564

# Version of the bridge API this integration speaks (GET /api/info "api_version").
# The bridge and the integration are released together with the same version.
API_VERSION = 1

# Bridge discovery components -> HA platforms (plus the camera).
PLATFORMS = ["button", "camera", "event", "image", "select", "sensor", "switch"]

# Discovery keys with a name in translations/en.json (entity.<platform>.<key>).
# Unknown keys (a newer bridge) fall back to the name the bridge sends.
TRANSLATED_KEYS = {
    "doorbell", "motion", "alert", "lock_opened", "gate_opened",
    "doorbell_photo", "motion_photo", "alert_photo",
    "open_lock", "open_gate",
    "motion_detection", "motion_zone",
    "motion_sensitivity", "alarm_interval",
    "sd_card", "doors", "detection_zone",
}


def signal_uplink(device_id: str) -> str:
    """Dispatcher signal of an upload test result: (mbit_per_s, quality)."""
    return f"anjielo_uplink_{device_id}"
