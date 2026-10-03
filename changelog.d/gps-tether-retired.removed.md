- **The engine's own GPS tether copy retired; the ACMA Bunker ruling recorded**
  (**D-071** note, **D-074**, 2026-10-02). `gps_tether.py` and its tests are
  deleted: the tether is hammunition-gps-tether, installed by the `gps-tether`
  unit. `hammunition maps gps-tether` runs the installed program and, absent,
  refuses naming `hammunition install gps-tether`. `tether_contract.py` holds
  the ports and the four GeoClue constants shared with the tether, asserted
  equal to its source by `tests/test_tether_contract.py` (skipped where that
  source is absent). `reference serve` checks `--position-port` itself. The
  maintainer's ruling that a Bunker may hold the ACMA register zip (it contains
  `client.csv`, never opened by the engine) is recorded, with Bunker's
  `hold_unverified = false` as the opt-out.
