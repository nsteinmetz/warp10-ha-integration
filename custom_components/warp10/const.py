"""Constants for the Warp10 integration."""

DOMAIN = "warp10"

CONF_URL = "url"
CONF_WRITE_TOKEN = "write_token"
CONF_INCLUDE = "include_entities"
CONF_EXCLUDE = "exclude_entities"
CONF_BATCH_INTERVAL = "batch_interval"
CONF_CLASS_PREFIX = "class_prefix"
CONF_INGEST_NUMERIC = "ingest_numeric"
CONF_INGEST_BOOLEAN = "ingest_boolean"
CONF_INGEST_STRING = "ingest_string"

DEFAULT_CLASS_PREFIX = "homeassistant"
DEFAULT_BATCH_INTERVAL = 5  # seconds between flushes to Warp10
DEFAULT_TIMEOUT = 10  # seconds, aiohttp request timeout
DEFAULT_INGEST_NUMERIC = True
DEFAULT_INGEST_BOOLEAN = True
DEFAULT_INGEST_STRING = True
