import os


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "digispace")
SITE_ID = os.getenv("SITE_ID", "building-1")

# The wildcard the backend subscribes to: digispace/building-1/+/state
TELEMETRY_WILDCARD = f"{MQTT_TOPIC_PREFIX}/{SITE_ID}/+/state"

CORS_ORIGINS = _csv("CORS_ORIGINS", "http://localhost:5173")

# How many days of history the rolling window keeps, including today.
HISTORY_DAYS = 7
