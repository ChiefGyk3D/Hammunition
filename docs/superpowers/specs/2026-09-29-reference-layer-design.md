# The offline reference layer: Kiwix books, dictionaries, ICS forms, one loopback page

**Status:** design approved by the maintainer (2026-09-29, relayed with the
task); this document is written for the record and for the implementation
plan. **Decision record:** D-065, written with the implementation. It is the
fourth case D-049 named ("then the ZIM with `kiwix`") and ETC sub-project 5's
offline-data layer (D-042 rule 5).

Everything below rests on the spike of 2026-09-29 (Parrot 7.3, Debian 13
archive plus echo-backports; packages run from `dpkg-deb -x`, nothing
installed): nine ZIMs downloaded and checked against the publisher's sha256,
33 books pinned from their `.meta4` alone, `kiwix-serve` measured binding
every address by default, dictd measured binding loopback by default.

## 1. What it delivers

| Need | Answer |
|---|---|
| An encyclopaedia, medicine, how-to and ham Q&A with no network | Kiwix ZIM files the operator chooses by name, pinned and verified, read by `kiwix-serve` or the Kiwix desktop reader |
| A dictionary, a thesaurus, acronyms | `dictd` with GCIDE, WordNet, FOLDOC and VERA, on 127.0.0.1, and `goldendict-ng` as the desktop lookup |
| The ICS forms a served agency hands a radio operator | FEMA's 39 ICS PDFs, 205 (radio communications plan), 213 and 214 among them, each pinned by our own sha256 |
| One place to open all of it | `hammunition reference serve`: a landing page on 127.0.0.1 listing the books, the forms and the dictionaries, with kiwix-serve beside it on loopback |

## 2. Units

| Unit | Method | What |
|---|---|---|
| `kiwix-tools` | apt `kiwix-tools` | `kiwix-serve`, `kiwix-manage`, `kiwix-search`. 3.7.0 on Debian 13, 3.5.0 on Ubuntu 24.04. 11.4 MB closure, 6.2 MB of it aria2 that libkiwix depends on and we never call |
| `kiwix` | apt `kiwix` | The Kiwix desktop reader (Qt5 WebEngine). Optional: not in the profile's core argument, in the profile because it is the easy way in |
| `dictionaries` | apt `dictd dict dict-gcide dict-wn dict-foldoc dict-vera` | About 32 MB. The package's `/etc/dictd/dictd.conf` already says `listen_to 127.0.0.1` and `allow localhost`: nothing is reconfigured, and the docs say so |
| `goldendict-ng` | apt `goldendict-ng` | Qt6 desktop lookup; reads DICT servers and ZIM files |
| `kiwix-library` | new method `kiwix-books` | The books the operator chose in station config; none by default; deferred by name when none are chosen |
| `ics-forms` | `data` (D-049) | 39 PDFs, 8,046,865 bytes measured (the spike's 4.9 MB was the page's own size column, which undercounts), public domain as US federal works (17 USC 105) |

Profile `reference`: all six. A reader installs whether or not books are
chosen (D-049 rule 3); `kiwix-library` is deferred alone.

## 3. Books: an allow-list, a generated pin file, station selection

**`catalog/data/kiwix-books.yaml`, hand-written.** The curation step. Each
entry: `id` (Kiwix's file stem without the date: `<name>_<flavour>`, or the
bare name for a book with no flavour, e.g. `ham.stackexchange.com_en_all`,
`wikipedia_en_medicine_nopic`), `name`, `flavour` (or null), `category`
(Kiwix's directory under `zim/`), `title`, `licence`, `licence_url`, and an
optional `note`. The licence line is the publisher's, because 8 of the 9
ZIMs read carry no `License` metadata:

- Wikimedia projects: "CC BY-SA 4.0 (text; media individually licensed)"
- Stack Exchange: "CC BY-SA"
- Appropedia, WikEM: "CC BY-SA 4.0"
- iFixit: "CC BY-NC-SA 3.0 — non-commercial"
- US federal works: "US federal work, public domain (17 USC 105)"

Carried: the 26 books of the spike's table that have a licence stated by
their publisher. Not carried, each with its reason in D-065 and the guide:
wikiHow, the `zimgit-*` prepper collections, energypedia (licence not
verified), whole Gutenberg, video-channel ZIMs, MedlinePlus, nhs.uk.

**`catalog/data/kiwix-pins.yaml`, generated** by
`scripts/gen_kiwix_pins.py` from `library_zim.xml` (for each allowed book,
the current entry's `.meta4` URL) and each book's `.meta4` (file name, exact
size, sha256). One row per allowed book: `id`, `file`, `url`, `size`,
`sha256`, `published` (the book's date), `measured`. The generator refuses a
book the library does not list, a `.meta4` with no sha-256, and an allow-list
entry with no pin, by name. `--check` refetches each pinned `.meta4` and goes
red when one is gone (404) or its size or sha256 moved; `--check --offline`
checks the shape only (every allowed book pinned once, every pin allowed,
hashes and URLs well formed) and runs in the test suite. The weekly
pin-review CI job runs `--check`.

Nothing Kiwix publishes is signed. Trust is TLS to `download.kiwix.org` at
the moment the pin is generated, frozen by the sha256. Kiwix keeps only the
two newest dated files per book, so **a pin dies about two publications after
it is made**; a 404 on a pin is an error naming the regeneration, never a
move to the newer file.

**Station.** `hammunition station set --reference-books ID[,ID…]` replaces
the list; an id not in the allow-list is refused at set time, naming
`hammunition reference books`. Book names are not location data, so
`station show` prints them. With none set, `kiwix-library` is deferred from
a profile (named, with the command) and refused when typed.

## 4. Install

A new install method, `kiwix-books` (`provider: kiwix`). Like `dem-tiles`,
the manifest pins nothing and states no licence: each book's licence comes
from the allow-list. At plan time the CLI resolves the selection against the
allow-list and pins; an unknown id or an allowed book with no pin refuses
the plan (exit 2). Each book not already installed is `HEAD`-checked before
the plan prints, so an expired pin refuses before anything runs, naming
`scripts/gen_kiwix_pins.py`.

The backend, per selected book: a `fetch` step whose description is the
disclosure D-049 asks for — *Fetch reference book ID (DATE, SIZE, LICENCE)*
— verified by sha256 and size, and an `install-data` step copying it to
`<prefix>/share/hammunition/data/kiwix-library/<file>.zim`, re-hashed on the
way in (`PrefixWriter`). A book whose pinned file is already there at its
pinned size is not fetched again. A `.zim` in that directory that no chosen
book names is removed as its own `remove-data` step. Disk: each download
counts twice (cache and prefix); a short file system refuses the plan with
both numbers. `uninstall kiwix-library` removes the directory whole, like
every data unit.

No `library.xml` is written at install time: building one runs
`kiwix-manage`, a parser of downloaded data, which belongs to the reader and
runs as the operator (D-057's line), not as root inside a data unit.

## 5. `hammunition reference`

- `reference books` lists the allow-list: id, title, size, licence, and
  whether it is chosen and installed. `--json` gives a `books` document.
- `reference serve [--port N]` (default 8480; kiwix on N+1; 1024–65534):
  1. refuses under root;
  2. finds the installed books, ICS forms and `dict`;
  3. with at least one book, builds `library.xml` in the operator's state
     directory with `kiwix-manage LIB add <zim>…` (refused, naming
     `hammunition install kiwix-tools`, when `kiwix-manage` is absent);
  4. starts `kiwix-serve -i 127.0.0.1 -p N+1 -r /wiki -b -a <pid> --library
     -M <library>` as a child — the argv always carries `-i 127.0.0.1`,
     because without it kiwix-serve listens on every address, and a test
     holds it;
  5. serves the landing page on 127.0.0.1:N from the standard library:
     books with links into kiwix, the forms under `/forms/`, and how to use
     the dictionaries (`dict WORD`, goldendict-ng);
  6. on Ctrl-C, or when the child exits, stops the other and returns.
  No `--json` form: a server, not a document (as `gps-tether`, D-059).

## 6. update

Offline (D-053): `kiwix-library` is *up to date* when every chosen book's
pinned file is installed, *behind the pin* when a chosen book is installed
at another date, *not installed* otherwise. `--upstream`: a new probe
method, `kiwix`, asks Kiwix's OPDS catalogue (`opds.library.kiwix.org`, one
~3 KB answer per book) for each chosen book's current file: the same file is
*current*; a newer one is *newer upstream*, with the warning that the pin
goes when Kiwix publishes again; and when the pinned `.meta4` itself answers
404 the row is *pin expired*, naming the regeneration.

## 7. Corrections carried into the docs

- `zim-tools` 3.5.0 in Debian 13 ships `/usr/bin/zimwriterfs`; "no
  zimwriterfs in Debian 13" is true of the package name only.
- libzim 9.2.3 (Debian 13) reads the format-6.3 ZIMs published today.
- `hamradio-maintguide` is the Debian Hamradio team's packaging guide, not
  operator documentation.

`docs/reference/etc-inventory.md` is generated; the correction goes into
`scripts/gen_etc_inventory.py`'s source note.

## 8. Testing

No network in tests: the generator, the plan-time `HEAD`, the fetch and the
OPDS probe each take an injected function. The serve verb is tested with a
fake child and a real loopback landing server. `make check` is the gate.
What the bench owes: a real `install reference` on the field laptop, one
small book fetched and served, and the pages opened in a browser.
