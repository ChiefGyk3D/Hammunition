- **HydraSDR RFOne and RigExpert Fobos SDR: host software and device entries,
  from upstream's own files, for hardware nobody here owns** (**D-024**,
  **D-027**, **D-028**, **D-029**, **D-032**). Five units: `hydrasdr-host` (the
  library and its seventeen tools) and `soapysdr-module-hydrasdr`, and
  `libfobos`, `libfobos-sdr-agile` and `soapysdr-module-fobos`, the last
  needing both libraries to build. Kali and Ubuntu 26.04 take the HydraSDR
  units from apt; every other target builds the tags Debian packages
  (v1.1.1, v1.0.1). Nothing Fobos is packaged anywhere, so `libfobos` (head
  1e0fab3) and `soapysdr-module-fobos` (aa8d486) are commit pins with a
  `pin_review`, `libfobos-sdr-agile` is upstream's tag. Two entries under
  `catalog/hardware/devices/`: `hydrasdr-rfone` (38af:0001, `status:
  supported` in D-027's shape, with 1d50:60a1 recorded in `rejected_ids`
  because the Airspy R2 and Mini use it and no rule can tell them apart, and
  the NXP DFU recovery id marked shared with the HackRF) and `fobos-sdr`
  (16d0:132e, `untested`; both firmware families present it and differ only
  in bcdDevice). Identifiers are cited as commit-pinned URLs into the vendors'
  repositories; `scripts/check_rule_citations.py` now ignores a rules file
  named inside a URL, since the sweep covers distribution packages only.
  Built in rootless containers on Debian 13, Ubuntu 24.04, Ubuntu 26.04 and
  Kali (x86_64): all five units build and install, `hydrasdr_info` and
  `fobos_devinfo` run without a board, `SoapySDRUtil --info` lists both
  modules. Three defects of upstream's builds are handled in the manifests,
  each measured: libfobos-sdr-agile wrote `/etc/udev/rules.d` as root (a
  CRLF-preserving patch removes it), SoapyHydraSDR also wrote into dpkg's
  module directory (a define), and nothing a build into `/usr/local` links
  was found without `ldconfig` (an embedded run path). Not owned, not run
  against a board; the units stay out of the `sdr` profile (D-020). The
  HydraSDR tree states two licences (per-directory LICENSE.md files, and a
  debian/copyright reading "licensed exclusively for HydraSDR products"); the
  unit's page says so and the catalog follows the LICENSE.md files (D-033).
