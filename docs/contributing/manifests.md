# Adding a package manifest

A manifest is a YAML file in `catalog/packages/` describing one piece of
software: what it is, why an operator would want it, how it installs on each
target, and what is known to go wrong with it. It is pure data. No manifest
contains logic, and no manifest may assume our engine is the one reading it.

This page is the conventions. When a field's meaning is the question, the
authority is `src/hammunition/manifest/schema.py` — every field carries a
docstring and the validators say what they refuse and why. This page is for the
decisions the schema cannot make for you.

## Measure it. Do not recall it.

The rule that catches the most mistakes, including several of ours.

Writing eleven Morse manifests in one sitting, four upstream versions were
filled in from memory and **all four were wrong** — `aldo` 0.7.7 for 0.7.8,
`morse` 2.5 for 2.6, `morse2ascii` 0.1.4 for 0.2.1, `xdemorse` 3.3 for 3.6.7.
Every one would have validated, loaded, and shipped. They were caught by
running the sweep and looking, which takes about forty seconds:

```
scripts/apt-policy-sweep.sh debian-13 debian:13 <a-file-of-package-names>
```

The same applies to whether a package exists at all. `not1mm` and `qlog` are in
the Debian Hamradio Blend, which is a Debian project, and neither is in Debian
13 — both are Kali-only among our targets. `cqrlog` is on every target except
Kali. Neither fact is guessable and both change what the manifest has to say.

## One manifest per package, not per project

`gpsd`, `gpsd-clients` and `gpsd-tools` are three manifests. So are `cw`,
`cwcp` and `xcwcp`, which Debian builds from one `unixcw` source. The unit is
the thing a person installs and looks up by name, and a manifest that installs
three packages under one of their names is not findable under the other two.

Where the packages genuinely are one thing — a library and the program that
links it — use `depends` rather than a second entry in `packages`.

## `version` on an apt manifest is the primary target's answer

An apt manifest does not choose a version; apt does, and the targets disagree.
Measured on one evening, `klog` was 2.4.1 on Debian 13 and Parrot, 2.4.2 on
Ubuntu 26.04, 2.5.2 on Kali and 2.3.3 on Mint. The field has to mean one of
them.

**It means Parrot's**, because Parrot is the primary target, falling back to
Debian 13 where Parrot does not carry the package. Record the upstream part of
the candidate — `2.5.2-5` is written `"2.5.2"`.

This was already the practice and it was already inconsistent. `ubertooth` is
recorded as `2020.12.R1`, which is Kali's and Parrot's; Debian 13 ships
2018.12.R1, two years older. Under the rule the entry is right, and its
`known_problems` already names all three — but nothing said so, and the next
person had no way to tell a considered choice from a slip.

The field is a **snapshot with a stated meaning, not a promise**. Debian will
move underneath it and that is not a defect. There is deliberately no CI check
comparing it to a live archive: a check that reddens every time Debian issues a
security update is the calendar-driven failure that teaches people to ignore
CI.

Quote it. An unquoted `2.5` is a YAML float, and a test rejects it.

## Prefer apt. Justify anything else.

`docs/SCOPE.md` puts the Debian Blend first because it is the cheapest coverage
with the best provenance. A source build is a maintenance commitment: a pinned
tarball, a checksum, a build-dependency list that rots, and a compiler that
gets stricter every release.

So the bar for not using apt is a **named, measured reason** — the archive does
not carry it, or the version it carries cannot do the thing the manifest claims.
"Upstream is newer" is not a reason by itself. AHRL builds `xlog` from source
because 2.0.25 postdates the repository's 2.0.24, and that point release is not
worth six `-Wno-*` flags and a build that a future GCC will break.

Where the reason is real, say it in the install block's `note`, with what was
measured and when.

## Categories come from the vocabulary

`catalog/categories.yaml` is the controlled list. Adding a tag means adding it
there, in the same commit as the manifest that needs it — `tests/test_categories.py`
rejects both an undeclared tag and a declared tag nothing carries.

They are flat tags (**D-003**). They overlap freely and never nest, so give a
manifest every tag that is true of it rather than choosing the most important
one.

## The documentation block is not optional

`CLAUDE.md` makes it a hard rule and the schema enforces the shape, but the
schema cannot tell whether `what_it_does` is any good. The standard is that a
licensed ham with moderate Linux experience can read the entry and know whether
they want the software, without opening a browser.

Two fields do the real work and both are commonly skimped:

* **`why_you_want_it`** is not a restatement of what it does. It is what the
  software is *for*, and what it is an alternative to. "Head copy is a
  listening skill and it improves with hours, not exercises" tells a reader why
  a text-to-Morse converter matters; "converts text to Morse" does not.
* **`known_problems`** is where the hours are saved. Prefer the failure that
  looks like something else: a USB-to-serial adapter that keys perfectly at 15
  wpm and falls apart at 30 is a hardware limit that reads as a software bug,
  and an operator who has not been told will look in the wrong place for an
  evening.

Write nothing you have not checked. An unverified known problem is worse than
none, because it sends people to inspect something that was never wrong.

## Before you open the pull request

```
python -m pytest tests/
python -m ruff check . && python -m ruff format --check .
scripts/check_doc_links.py
```

The catalog tests load every manifest and report **all** failures rather than
the first (**D-016**), so one run tells you everything that is wrong.
