- **Reticulum, NomadNet and LXMF** (Track C, PR 2, issue #105, **D-080**). Three
  hash-pinned per-user venvs, `rns`, `lxmf` and `nomadnet`, because no archive
  carries any of them: `rns` exposes every console script Reticulum declares
  (`rnsd`, `rnstatus`, `rnpath`, `rnprobe`, `rnid`, `rncp`, `rnx`, `rnsh`, the
  RNode flasher `rnodeconf` and the rest) and installs a user service,
  `hammunition-rnsd`, that keeps one shared instance per operator (enabled at
  install, started at next login; an abstract local socket, not a TCP port,
  measured in a Debian 13 container); `lxmf` gives `lxmd` and starts nothing;
  `nomadnet` gives the terminal messenger and a menu entry. The Reticulum
  License (MIT plus two use restrictions, not OSI-approved) is printed on the
  plan line that installs the venv and never gated; NomadNet is `GPL-3.0-only`
  by its shipped text. The engine writes no Reticulum configuration and
  uninstall leaves `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd` and `~/.rnsh`.
  New post-1.0 `mesh` profile (the three plus `python3-meshtastic` and
  `gtk-meshtastic-client`), a `rnode` hardware entry (`untested`: no identifier
  of its own), and `docs/guides/mesh-and-reticulum.md` with four
  troubleshooting entries. Engine: a user service's `exec` may start
  `{venv}/...`, and a venv block may state its `licence` and `licence_url` on
  its plan line. Two containers on one bridge found each other, exchanged an
  LXMF message and ran `rnsh`; no LoRa link has been run.
