# RepeaterBook API fixture

`repeaterbook-api-de.json` is **written by hand from RepeaterBook's documented
format and the unofficial client's models, not recorded from the live API.**
Nothing here was fetched: the maintainer had no token on 2026-10-04, and the
suite blocks the network anyway.

- Format sources, read 2026-10-04: RepeaterBook's wiki
  <https://www.repeaterbook.com/wiki/doku.php?id=api>, which lists the data
  fields but prints neither the JSON key names nor the response envelope, and
  the source of the `repeaterbook` 0.13.0 client (PyPI, MIT,
  `github.com/MicaelJarniac/repeaterbook`, `models.py` `RepeaterJSON` and
  `ExportJSON`), which gives the keys (`Frequency`, `Input Freq`, `PL`, `TSQ`,
  `Nearest City`, `Landmark`, `County`, `State`, `Lat`, `Long`, `Callsign`,
  `Use`, `Operational Status`, `Notes`, `Last Update`, a `Yes`/`No` key per
  mode) and the envelope `{"count": N, "results": [...]}`.
  The fixture omits keys the parser does not read.
- The runner wraps it as `{"ok": true, ...}`; the verb's tests serve it from a
  fake runner script.
- Every row is synthetic: N0CALL, N0TST and invented places and positions.
  Two rows are there to be skipped (off the air, no position), one has no
  callsign, one has a frequency that is not one.
- State ids are the standard FIPS codes (Delaware 10); the client's
  `na_states.py` confirms RepeaterBook's US `state_id` is the two-digit FIPS code.
