# Warp 10 integration for Home Assistant

Streams entity state changes from Home Assistant into a
[Warp 10](https://www.warp10.io/) time series platform, in raw form
(one Geo Time Series point per state change, no aggregation). Numeric,
boolean, and free-text states are all forwarded, each as Warp10's matching
native GTS value type.

## Installation

### Via HACS

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add this repository URL, category "Integration".
3. Search for "Warp 10", install, restart Home Assistant.

### Manual

Copy `custom_components/warp10` into your Home Assistant `config/custom_components/`
directory and restart Home Assistant.

## Configuration

Settings → Devices & Services → Add Integration → "Warp 10".

You will be asked for:

- **Warp 10 URL** — e.g. `http://localhost:8080` or the address of the
  [warp10-ha-addon](https://github.com/YOUR_GITHUB_USERNAME/warp10-ha-addon)
  if you're running Warp 10 as a Home Assistant add-on.
- **Write token** — a Warp 10 WRITE token for the application/producer
  you want the data attributed to.

Options (gear icon on the integration card) let you set:

- entity include/exclude lists (comma-separated `entity_id`s)
- the GTS class name prefix (default `homeassistant`)
- the batch flush interval in seconds (default 5)
- whether to ingest numeric, boolean, and/or free-text states — each is its
  own on/off toggle, all enabled by default

## How data is stored

Each forwarded state change becomes one Warp10 GTS point:

```
<timestamp_micros>// homeassistant.<entity_id>{entity_id=<entity_id>} <value>
```

`<value>` depends on the state's type:

- **Numeric** states (e.g. sensor readings) → a Warp10 LONG/DOUBLE, e.g. `21.5`.
- **Boolean** states — `on`/`off` (binary_sensor, switch, input_boolean, ...)
  and `true`/`false`, case-insensitive — → Warp10's native BOOLEAN literal,
  `T` or `F`.
- Everything else (free text) → a Warp10 STRING, percent-encoded and
  single-quoted, e.g. `'hello%20world'`.

`unknown`, `unavailable`, and empty states are always skipped, regardless of
the toggles above. Points are buffered and flushed in a single batched HTTP
call every `batch_interval` seconds, using each state's own `last_updated`
timestamp — not the time of the flush.

## Diagnostics

The integration exposes two diagnostic sensors:

- `sensor.warp_10_points_sent` — cumulative points sent since HA started
- `sensor.warp_10_last_error` — the last transport/HTTP error, if any

## License

Apache-2.0
