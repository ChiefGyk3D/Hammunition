<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Offline reference: an encyclopaedia, a dictionary and the ICS forms on the laptop

When the network is down the questions keep coming: what an acronym in a
passed message means, how to treat an injury, how a part works, what the
agency's communications plan form wants. The `reference` profile puts the
answers on the laptop first: Kiwix books you choose (Wikipedia, WikiMed,
WikEM, Amateur Radio Stack Exchange and others), a dictionary server with an
English dictionary, a thesaurus, computing terms and acronyms, and FEMA's
ICS forms. `hammunition reference serve` shows all of it on one page in a
browser, on this machine only.

The decision behind this is **D-065** in `docs/DECISIONS.md`; the method
the books use is **D-049**'s offline-data layer.

---

## What you need first

- **A choice of books.** Nothing is chosen for you. `hammunition reference
  books` lists the 27 the catalog offers, with each one's size and licence.
- **Disk space** for the books you choose. A book is counted twice while it
  installs: the checked download, then the installed copy (the download is
  deleted once the copy is in place). See [Sizes](#sizes).
- **A network connection at install time**, and only then.

## 1. Choose your books

```
hammunition reference books
```

Each book has an id: Kiwix's own file name without its date. A book in
several flavours has one id per flavour: `maxi` has pictures, `nopic` has
none, `mini` keeps each article's introduction only. Choose by id,
comma-separated:

```
hammunition station set --reference-books ham.stackexchange.com_en_all,wikipedia_en_medicine_nopic,wikem_en_all_nopic
```

That replaces the whole list. An id the catalog does not list is refused as
you type it, with the command that lists them. The ids are saved in
`~/.config/hammunition/station.yml` with your other station values, and
`hammunition station show` prints them: which books you read is not where
you are, so unlike map regions they are named.

Why only the catalog's list: the ZIM files do not say what licence they are
under (of nine read, one did), and the plan has to print each book's
licence before you confirm. The list carries the publisher's own licence
line for each book. A book not on it can be added to
`catalog/data/kiwix-books.yaml` with its licence, and the pins regenerated
(`scripts/gen_kiwix_pins.py`); or you can open any ZIM you have with the
readers directly.

## 2. Look at the plan, then install

```
hammunition install reference --dry-run
hammunition install reference
```

The plan names each book with its date, size and licence before anything
downloads, for example:

```
Fetch reference book ham.stackexchange.com_en_all (2026-08, 75.9 MB, CC BY-SA)
```

Each book is checked twice: against the size and sha256 the catalog pinned
when it was downloaded, and again when it is copied into
`/usr/local/share/hammunition/data/kiwix-library/`. With no books chosen,
`kiwix-library` is deferred by name and the readers, dictionaries and forms
install anyway.

## 3. Open it: `hammunition reference serve`

```
hammunition reference serve
```

Then open <http://127.0.0.1:8480/> in a browser. The page lists every
installed book (click one to read it; *Search every book* searches them
all), every ICS form, and how to use the dictionaries. Ctrl-C in the
terminal stops it.

It listens on 127.0.0.1 only. The books are served by Kiwix's own
`kiwix-serve` on the next port (8481), which the engine always starts with
`-i 127.0.0.1`: left to itself kiwix-serve listens on every network address
of the machine and announces its LAN address. If you run kiwix-serve by
hand, give it `-i 127.0.0.1` yourself. `--port N` moves the page (Kiwix
takes N+1); it never widens the address. To read the books from another
machine, forward the ports over SSH (`ssh -L 8480:127.0.0.1:8480 -L
8481:127.0.0.1:8481 <laptop>`) rather than opening a listener.

The desktop reader, `kiwix`, opens the same files by name from
`/usr/local/share/hammunition/data/kiwix-library/`, if you prefer a window
to a browser tab.

## 4. Dictionaries

`dictionaries` installs dictd with four databases: GCIDE (English), WordNet
(definitions and synonyms), FOLDOC (computing) and VERA (acronyms). In a
terminal:

```
dict dipole
dict -d vera ICS
dict -D
```

dictd listens on 127.0.0.1 port 2628 only, because Debian's own
configuration says so; nothing is changed. goldendict-ng is the desktop
look-up: add the local dictd (127.0.0.1) as a DICT server among its
dictionary sources once. Where that setting sits in its current menus has
not been checked on a desktop here yet.

Translation dictionaries are not installed: Debian has 253
`dict-freedict-*` packages, 32 from English. Choose the ones for the
languages you serve (`apt search dict-freedict-eng`).

## 5. The ICS forms

`ics-forms` installs the 39 PDFs FEMA publishes as the ICS forms, under
`/usr/local/share/hammunition/data/ics-forms/`: the 205 incident radio
communications plan and 205A communications list, the 213 general message,
the 214 activity log, the 201 briefing and the rest, with FEMA's
instructions and the NIMS forms booklet. They are fillable in a PDF reader
that fills forms, and on the reference page under *ICS forms*. FEMA
publishes no checksum for them; each is checked against a sha256
Hammunition measured on 2026-09-29.

Winlink users have ICS-213 and its siblings in pat's forms already. The ICS
309 communications log is not among the 39 FEMA lists, so it is not here.

## 6. Keeping the books current

```
hammunition update
hammunition update --upstream
```

Offline, `update` says whether each chosen book's pinned file is installed.
`--upstream` asks Kiwix (about 3 KB per book) whether the pinned file is
still its newest. Kiwix keeps only the **two newest dated files of each
book**, so a pin dies about two publications after it was made:

- *newer upstream*: Kiwix has published a newer file. Yours still works and
  can still be installed, but the pinned file goes at the next publication.
- *pin expired*: the pinned file is gone. An install refuses that book,
  naming `scripts/gen_kiwix_pins.py`, and never quietly takes the newer
  file: nobody has measured its sha256.

Either way the fix is in the catalog: regenerate the pins (the weekly pin
review does it on a calendar), pull the catalog, and install again. An
installed book keeps working whatever happens upstream.

## Sizes

Measured 2026-09-29 from Kiwix's own metadata. `hammunition reference
books` prints the current pin for every book.

| Book | Size |
|---|---:|
| Simple English Wiktionary | 26.5 MB |
| Amateur Radio Stack Exchange | 75.9 MB |
| WikiMed, introductions only (`mini`) | 163 MB |
| WikEM, no pictures | 347 MB |
| Wikivoyage, no pictures | 272 MB |
| Appropedia | 582 MB |
| WikiMed, no pictures | 862 MB |
| Simple English Wikipedia, no pictures | 1.09 GB |
| WikiMed, with pictures | 2.22 GB |
| iFixit | 3.57 GB |
| Army Publishing Directorate | 8.23 GB |
| English Wikipedia, introductions only | 14.4 GB |
| English Wikipedia, no pictures | 52.7 GB |
| English Wikipedia, with pictures | 127 GB |

The readers and dictionaries are small (kiwix-tools about 11.4 MB with its
dependencies, the dictionaries about 32 MB); kiwix and goldendict-ng are
mostly their web engine, not yet measured. The ICS forms are 8 MB.

## Licences

The plan prints each book's licence line, and `hammunition reference books`
lists them. Hammunition states them and does not judge what you do with
the content:

- Wikipedia, Wiktionary, Wikivoyage, WikiMed: CC BY-SA 4.0 for text; media
  are licensed individually.
- Stack Exchange sites: CC BY-SA.
- Appropedia, WikEM: CC BY-SA 4.0. MDWiki: CC BY-SA. OpenStreetMap wiki:
  CC BY-SA 2.0.
- iFixit: CC BY-NC-SA 3.0, **non-commercial**.
- Ready.gov, the Army Publishing Directorate, the FAS military-medicine
  mirror, and the ICS forms: US federal works, public domain (17 USC 105).
  For the three scraped sites this is the class of the publisher, not
  checked page by page.
- Project Gutenberg's military-science class: public domain in the USA,
  with Project Gutenberg's licence on the ebook files.

## What is not carried, and why

- **wikiHow**: Kiwix has no current wikiHow file (the archive holds frozen
  2023 copies), and its content is CC BY-NC-SA.
- **The `zimgit-*` prepper collections** (post-disaster, medicine, water,
  knots, food preparation): no licence is stated anywhere, in the files or
  by their publisher. They are a documented gap until one is.
- **energypedia**: its licence could not be verified on the day.
- **The whole of Project Gutenberg**: 221 GB. One class of it, military
  science, is offered; others can be added to the list the same way.
- **Video-channel ZIMs** (prepper channels) and **MedlinePlus**: mixed
  licences (MedlinePlus includes A.D.A.M. content that is not public
  domain).
- **ARRL and ARES material**, including ETC's ARRL band chart: ARRL
  copyright.
- **A sigidwiki ZIM**: none exists. `artemis` carries the signal database
  offline already.
- **Direwolf's user guide**: Debian's `direwolf` package strips upstream's
  PDFs. Upstream publishes them in the `wb2osz/direwolf-doc` repository,
  which is the route, and has not been measured here.

## Removing it

```
hammunition uninstall kiwix-library ics-forms
```

removes the books and the forms (their data directories, whole). The
readers and dictionaries are apt packages and come out with `hammunition
uninstall kiwix-tools kiwix dictionaries goldendict-ng`. The library file
`reference serve` builds is in `~/.cache/hammunition/reference/` and can be
deleted at any time.

## Troubleshooting

- **"not in the catalog's book list"** when setting books: the id is not
  one the catalog offers. Ids use Kiwix's spelling:
  `wikipedia_en-simple_all_nopic` has a hyphen in `en-simple`. `hammunition
  reference books` lists them.
- **"answered HTTP 404"** at install: the pin has expired upstream (see
  [Keeping the books current](#6-keeping-the-books-current)). Nothing was
  changed.
- **`reference serve` says kiwix-serve or kiwix-manage is not on the
  PATH**: `hammunition install kiwix-tools`.
- **"cannot listen on 127.0.0.1 port 8480"**: something else has the port,
  or another `reference serve` is running. `--port 8490` uses 8490 and 8491.
- **A book opens with no pictures**: you chose a `nopic` or `mini`
  flavour. Choose the `maxi` id too, if the disk has room.

## What has not been measured yet

- A real `hammunition install reference` on a target: the fetch, check and
  install of one book (76 MB) and of the 39 forms ran through the engine's
  own code on the development host on 2026-09-29, and `reference serve` ran
  there against the archive's kiwix-tools 3.7.0 unpacked from its `.deb`,
  with both listeners on 127.0.0.1 only and Ctrl-C stopping kiwix-serve. It
  has not run on the field laptop, and no page has been opened in a
  desktop browser there.
- goldendict-ng's DICT-server setting and the Kiwix desktop reader on a
  desktop session.
- The installed sizes of `kiwix` and `goldendict-ng` on a desktop that
  lacks their web engines.
