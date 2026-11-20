"""Constants for the Anjielo integration."""

DOMAIN = "anjielo"

CONF_RTSP_PORT = "rtsp_port"

DEFAULT_PORT = 8565
DEFAULT_RTSP_PORT = 8564

# Bridge discovery components -> HA platforms (plus the camera).
PLATFORMS = ["button", "camera", "event", "image", "select", "sensor", "switch"]

# Discovery keys with an English name in translations/en.json (entity.<platform>.<key>).
TRANSLATED_KEYS = {
    "sonnette", "mouvement", "alerte", "serrure", "portail",
    "photo_sonnette", "photo_mouvement", "photo_alerte",
    "porte_1", "porte_2",
    "detection_mouvement", "zone_mouvement",
    "sensibilite", "intervalle_alarme",
    "carte_sd", "portes", "zone_surveillance",
}

# The bridge API speaks French: attribute names and values shown in English.
ATTR_NAMES = {
    "portes": "doors",
    "n_sommets": "vertex_count",
    "sous_type": "subtype",
}
ATTR_VALUES = {
    "serrure": "lock",
    "portail": "gate",
    "mouvement": "motion",
    "humain": "human",
    "sonnette": "doorbell",
    "son": "sound",
    "sabotage": "tamper",
    "appel": "call",
    "inconnu": "unknown",
}
