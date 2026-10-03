- **US Topo is bounded: a radius around your grid square by default,
  `--topo-regions`, `--topo-all`, and a typed `yes` to a size above 10 GB**
  (**D-068** amendment, 2026-10-02, #232). Every sheet of three whole-state
  regions was 7,284 sheets, 55 GB of download and 111 GB of disk, and the
  `navigation` profile could not leave them out. `station set
  --topo-radius-km N` (100 when unset, 0 for none), `--topo-regions a,b` (a
  subset of `--map-regions`) and `--topo-all` / `--no-topo-all` choose; FSTopo
  and 3DEP follow, Copernicus terrain does not. The install prints a `note:`
  line before the plan saying what was chosen and how to change it. With
  `--topo-all`, or more than 10 GB, the plan prints the count, download and
  disk in one sentence and asks you to type `yes`, which `--yes` does not
  answer. With no grid square the unit defers by name and keeps what is
  installed.
