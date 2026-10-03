- **Unverified repeater snapshots can sit on a Bunker; the bring-your-own-data
  principle is recorded; Canada's sources measured and not carried**
  (**D-078**, **D-074** amendment of 2026-10-03). `hammunition artifacts
  --json` lists the three on-request lists (ETCC, Brandmeister, hearham) as
  unit `repeater-snapshots`, check `unverified-fetch` (no digest, the
  publisher's URL, the size from a `HEAD`, the licence position), so a Bunker
  can hold them under `hold_unverified`; `maps repeaters fetch-etcc`,
  `fetch-brandmeister` and `fetch-hearham` read the station's mirror first at
  `<mirror>/repeater-snapshots/<name>` (`--no-mirror` skips it) and the
  publisher on any failure, still marked unverified. Operators bring their own
  export or key for questionable or personal data, the project never hosts it,
  and no licence letters are sent on its behalf. Canada's TAFL (no amateur
  rows, licensee names and addresses) and ISED's call-sign file (names and
  addresses) are not carried.
