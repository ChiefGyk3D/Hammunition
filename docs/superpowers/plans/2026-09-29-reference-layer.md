# The offline reference layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry Kiwix books, dictionaries and the ICS forms as catalog units, pinned and disclosed, and serve them on one loopback page (D-066).

**Architecture:** Readers are apt units; the payloads are a new `kiwix-books` method (station-selected, pins generated into `catalog/data/`) and a `data` unit; serving is an engine verb that starts `kiwix-serve` as a loopback child beside a stdlib landing server.

**Tech Stack:** Python 3.11+, pydantic schema, stdlib `http.server`/`urllib`/`xml.etree`, pytest with the suite's loopback-only network block.

**Spec:** `docs/superpowers/specs/2026-09-29-reference-layer-design.md`

## Global Constraints

- Nothing in tests touches the network; every fetch is an injected function (tests/conftest.py blocks non-loopback sockets).
- `kiwix-serve` argv always carries `-i 127.0.0.1`; the landing server binds `127.0.0.1` only; ports 1024–65534, default 8480 (kiwix on N+1).
- A 404 on a pinned book is an error naming `scripts/gen_kiwix_pins.py`, never a switch to the newer file.
- Size and licence of every book print before the confirmation (D-049), in the fetch step's description.
- Licence lines exactly: "CC BY-SA 4.0 (text; media individually licensed)", "CC BY-SA", "CC BY-SA 4.0", "CC BY-NC-SA 3.0 — non-commercial", "US federal work, public domain (17 USC 105)".
- No sudo, no real install, no GUI; `nice -n 19 ionice -c 3` for every run on this machine.
- Commits as `19499446+ChiefGyk3D@users.noreply.github.com`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- `mypy --strict`, `ruff check`, `ruff format --check` clean.

## Review Focus

1. An operator types a book id with the wrong separator (`wikipedia_en_simple_all_nopic` for `wikipedia_en-simple_all_nopic`): refused at `station set`, naming `hammunition reference books` — test in Task 3.
2. The port N+1 is out of range when N is 65535: refused before anything starts — test in Task 8.
3. A book file on disk with the pinned name but a truncated size: fetched again, not trusted — test in Task 5.
4. `reference serve` with no books installed: the page still serves forms and dictionaries, and no kiwix child is started — test in Task 8.
5. A form name requested under `/forms/` with `..` or a slash: 404, nothing outside the forms directory is read — test in Task 8.

---

### Task 1: Book model, allow-list and pin parsing (`src/hammunition/kiwix.py`)

**Files:** Create `src/hammunition/kiwix.py`, `tests/test_kiwix.py`.

**Produces:**
- `BOOK_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")`
- `@dataclass(frozen=True) class Book: id, name, flavour: str|None, category, title, licence, licence_url, note: str|None`
- `@dataclass(frozen=True) class BookPin: id, file, url, size: int, sha256, published, measured`
- `@dataclass(frozen=True) class BookFile: book: Book; pin: BookPin` with `.dest_name` (= pin.file)
- `class KiwixError(ValueError)`
- `load_books(text) -> dict[str, Book]`, `load_pins(text) -> dict[str, BookPin]` (refuse malformed rows by name)
- `resolve_books(selection, books, pins) -> list[BookFile]` (unknown id / unpinned id → KiwixError naming both remedies)
- `parse_meta4(text) -> tuple[str, int, str]` (file name, size, sha256); `parse_library(xml) -> dict[(name, flavour), str]` (meta4 url); `current_file(opds_xml, name, flavour) -> str|None`
- `file_date(file) -> str` (the `YYYY-MM` at the end of a pinned file name)

- [ ] Tests: allow-list loads; a duplicate id, a bad licence_url (not https), an id not matching `<name>_<flavour>` are refused; pins load; an unknown selected id raises naming `hammunition reference books`; an allowed id with no pin raises naming `scripts/gen_kiwix_pins.py`; `parse_meta4` on the spike's ham.stackexchange `.meta4` returns `("ham.stackexchange.com_en_all_2026-08.zim", 75931239, "71480bd2…")`; a `.meta4` with no sha-256 raises; `current_file` picks the right flavour out of a three-entry OPDS answer.
- [ ] Run, see them fail; implement; run, pass; commit.

### Task 2: The allow-list, the generator and the pin file

**Files:** Create `catalog/data/kiwix-books.yaml`, `scripts/gen_kiwix_pins.py`, `catalog/data/kiwix-pins.yaml` (generated), `tests/test_gen_kiwix_pins.py`; modify `tests/test_docs_generated.py`, `.github/workflows/ci.yml` (weekly pin-review job), `REUSE.toml` if it lists data files.

**Consumes:** Task 1's parsers. **Produces:** `main(argv, *, text=None, today=None, books_path=..., pins_path=...) -> int` with `--check [--offline]`.

- [ ] Tests (fakes only): generation from a two-book fake library writes both rows sorted by allow-list order with the generated mark; a book absent from the library refuses naming it; `--check --offline` passes on a good file and fails naming an unpinned allowed id; `--check` online reports a 404 `.meta4` as "gone upstream … regenerate"; `--check` writes nothing.
- [ ] Implement; generate the real file once (network: `library_zim.xml` 20 MB and 26 `.meta4`s); wire the offline check into `tests/test_docs_generated.py` and the online one into the weekly CI job; commit.

### Task 3: Station `reference_books`

**Files:** Modify `src/hammunition/station.py`, `src/hammunition/cli/main.py` (`station set --reference-books`, station show), `src/hammunition/interface/station.py`, JSON goldens; tests in `tests/test_reference_station.py`.

- [ ] Tests: a `reference_books` list round-trips through save/load; an id with a space or upper case is refused by the dataclass; `station set --reference-books a,b` saves and prints both; an id outside the allow-list is refused naming `hammunition reference books` and nothing is saved; `--reference-books ","` is refused; `prompt_for` keeps the books; `station show` lists them; the station JSON document carries `reference_books`.
- [ ] Implement; regenerate `docs/reference/json-interface.md`; commit.

### Task 4: Schema method `kiwix-books`, plan deferral

**Files:** Modify `src/hammunition/manifest/schema.py` (`KiwixBooksInstall`, `UpdateProbe.method` gains `kiwix`), `src/hammunition/backends/__init__.py` (`IMPLEMENTED_METHODS`), `src/hammunition/plan.py` (deferral/blocker), `src/hammunition/state/uninstall.py`, `scripts/gen_package_reference.py`, `scripts/gen_capability_matrix.py`; tests in `tests/test_plan.py`-style `tests/test_plan.py` and `tests/test_uninstall.py`.

- [ ] Tests: a profile holding a `kiwix-books` unit with no books set defers it with `why == "no reference books chosen"` and a remedy naming `station set --reference-books`, the apt members still planned; the same unit typed by name is refused; with books set nothing is deferred; uninstall plans removal of `data/kiwix-library/` whole.
- [ ] Implement; commit.

### Task 5: The backend (`src/hammunition/backends/kiwix.py`)

**Produces:** `KiwixBooksBackend(fetcher, prefix, files: Sequence[BookFile], runner=None)` with `data_dir(manifest)`, `pending() -> list[BookFile]`, `steps(manifest, block)`; `disk_needs(pending, cache, prefix) -> dict[Path, int]`.

- [ ] Tests: a pending book gives a `fetch` step whose description holds id, date, size and licence and an `install-data` step whose detail is the destination; a book present at its pinned size gives no step; one present at the wrong size is fetched again; a `.zim` no chosen book names gets a `remove-data` step; running the steps against a loopback-served fake file installs it and re-verifies it; a size mismatch fails naming the manifest-vs-download sizes.
- [ ] Implement; wire into `execute.commands_for` (`books=` keyword); commit.

### Task 6: CLI install integration

**Files:** `src/hammunition/cli/main.py` (`resolve_reference_books`, HEAD check, disk check, backend construction), `src/hammunition/interface/plan.py` (status "already installed" when nothing to fetch).

- [ ] Tests: with a fake catalog and injected HEAD, a pinned book answering 404 refuses the plan (exit 2) naming `scripts/gen_kiwix_pins.py`; the dry-run text shows the book's size and licence line; an installed-current book's line reads "already installed".
- [ ] Implement; commit.

### Task 7: update, offline and `--upstream`

**Files:** `src/hammunition/update.py`, `src/hammunition/upstream.py`, `src/hammunition/cli/main.py`, `src/hammunition/interface/update.py` if its state list is closed.

- [ ] Tests: offline row up to date / behind the pin / not installed from files on disk; `probe_kiwix` returns *current* for a matching OPDS answer, *newer upstream* with "goes when Kiwix publishes again" for a newer file, *pin expired* when the pinned `.meta4` raises 404, *unanswered* on a timeout.
- [ ] Implement; commit.

### Task 8: `hammunition reference books` and `reference serve`

**Files:** Create `src/hammunition/reference.py`, `src/hammunition/interface/books.py`; modify `src/hammunition/cli/main.py`; tests `tests/test_reference_serve.py`, JSON golden for `books`.

**Produces:** `serve_port(text) -> int`, `kiwix_serve_argv(port, library, pid) -> list[str]`, `landing_page(books, forms, dictionaries) -> str`, `make_server(port, page, forms_dir) -> ThreadingHTTPServer`, `run(port, *, spawn, manage, ...) -> int`.

- [ ] Tests: argv always contains `-i`, `127.0.0.1` adjacent, `-p` N+1, `--library`, `-M`, `-b`, `-r /wiki`, `-a pid`; `serve_port("65535")` refused, `"1023"` refused; the landing server answers `/` with every book title, form and `dict` line; `/forms/<name>` returns the PDF bytes and `/forms/../x` 404s; with no books no child is spawned; the child's exit stops the server; KeyboardInterrupt terminates the child; root is refused; `reference books --json` validates.
- [ ] Implement; regenerate the JSON reference; commit.

### Task 9: Manifests and profile

**Files:** `catalog/packages/{kiwix-tools,kiwix,dictionaries,goldendict-ng,kiwix-library,ics-forms}.yaml`, `catalog/profiles/reference.yaml`, `catalog/categories.yaml` (references summary).

- [ ] Every manifest carries the five documentation fields; `ics-forms` has 39 artifacts with our sha256 and sizes measured 2026-09-29; the full suite's catalog tests pass; regenerate `docs/packages/`, profile pages, capability matrix and any page whose `--check` goes red; commit.

### Task 10: Docs and records

- [ ] `docs/guides/offline-reference.md` (install, choose books, serve, dictionaries, forms, what is not carried and why, bench status); `docs/reference/cli.md`; `CHANGELOG.md` Unreleased; `CLAUDE.md` table row; `## D-066` appended at the end of `docs/DECISIONS.md`; the three corrections (etc-inventory generator note, and any page saying otherwise); `make check` exit 0 captured to a log; commit.

### Task 11: Whole-branch review (one opus subagent), fix, re-check, report.
