- **gps-tether 0.1.1: refusals exit 3, the unit retries crashes only** (**D-073**
  amendment, the maintainer's ruling). hammunition-gps-tether v0.1.1 exits 3 on
  a refusal (a taken port or socket, root, an unusable option) and 1 on an
  uncaught crash; the `gps-tether` unit is re-pinned to it and carries
  `RestartPreventExitStatus=3`, so systemd stops retrying refusals and keeps
  retrying crashes. `hammunition maps gps-tether` passes the tether's exit code
  through.
