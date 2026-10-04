<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Template: an application's documentation

An application's page is generated from its manifest, so this template is the
shape of the `documentation:` block, not of a markdown file. Copy it, fill every
field, and say *not measured* where that is true.

```yaml
documentation:
  # What it does, in plain language for someone who has not used it.
  what_it_does: >
    ...
  # Why an operator wants it, and what it is an alternative to.
  why_you_want_it: >
    ...
  # What must be configured first: rig control, audio, GPS, station values.
  prerequisites:
    - ...
  # Known problems and workarounds, including display-server issues.
  known_problems:
    - ...
  upstream_url: https://...
  upstream_support: https://...
  # What works with no internet, and what has to be fetched or configured
  # ahead of time. Separate internet, a LAN service and the radio.
  offline: >
    ...
  # One useful first task and the result to expect. Only commands and menu
  # entries that exist. Mark unrun steps "not tested on hardware".
  first_task: >
    ...
```

The generated page also states, from the rest of the manifest, how it installs
(`hammunition install NAME`), which profiles include it, its launcher, and
whether install touches the network. Do not repeat those by hand.

## Checklist

- [ ] Plain-language purpose; the alternative it replaces
- [ ] Profile or "optional, by name only" (generated)
- [ ] How to launch (menu entry or command; generated from `launchers`)
- [ ] `first_task` with the expected result, or the gap said honestly
- [ ] `offline`: what works, what needs the internet, what to fetch first
- [ ] Radios, interfaces, permissions, accounts needed
- [ ] `known_problems` and where to ask for help (`upstream_support`)
- [ ] Regenerated the package pages; `gen_package_reference.py --check` clean
