# Writes or checks each source's copy of what the root holds for all of
# them. `sync_sources.py` says what and how.
{ writers }:
writers.writePython3Bin "sync-sources" {
  # ruff.toml holds the style, at width 120.
  flakeIgnore = [ "E501" ];
} ./sync_sources.py
