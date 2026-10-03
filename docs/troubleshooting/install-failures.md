<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# When an install fails

Every failure the engine reports names what it was doing and stops there —
resolution finishes before installation, so a failure is a report, not a
half-installed machine. What you do next depends on which of these it is.

## <a name="slow-plan"></a>The dry run seems to hang

`hammunition install navigation --dry-run` can take minutes before it prints a
line. It has not hung: the plan checks every terrain tile, map sheet, book and
map it would download against the publisher, one request each, because each
answer (size, checksum) is part of what the plan tells you. On a terminal it
says so on stderr (`checking 412 terrain tiles … (needs the network)…`) with a
count. If you see nothing at all, stderr is not a terminal; run it with
`HAMMUNITION_PROGRESS=1` in front, or in a terminal rather than through a pipe
or a log. A repeat dry run is fast now: an item already installed that the transaction
log attributes to the engine is not asked about again for seven days (the plan
says `N installed data item(s) were not re-checked`, and `--json` lists each in
`publisher_checks`), and only a first install or an older attribution costs the
requests. `hammunition install … --recheck` asks every publisher regardless, for
when you suspect one re-issued a file. With the network down
a request that cannot connect is retried, then the host is given up on after
three such failures in a row and each remaining request is asked once (a
publisher answering 503 for everything is treated the same); a blackholed
connection still waits out its own 30 s timeout, four at a time, so a few
hundred tiles can take a long while to refuse. Interrupt with Ctrl-C, fix the
connection and run again.

## <a name="publisher-not-answering"></a>The plan said a publisher is not answering

```text
Will NOT happen (the rest of the transaction still will):
  usgs-ustopo: will not fetch 3 item(s) this run: <sheet>, <sheet>, <region> (its outline)
      why: the publisher is not answering right now (prd-tnm.s3.amazonaws.com answered
      HTTP 503); 3 attempts each, then given up
```

Nothing is wrong with your station or the catalog. A publisher (a Geofabrik
outline, the USGS bucket, Kiwix, a CDN) answered a 5xx, dropped the connection
or timed out three times running for those items, and the plan left them out
rather than refuse everything else. Run the same command again in a few
minutes: the items are asked again and, once the publisher is back, planned as
usual. Anything of theirs already on disk was kept; when the deferred item is a
Kiwix book or a CoMaps map, the unit removes no unlisted file in that run, so a
book you deselected goes at the next complete one. A certificate that does not
verify is never treated as an outage: it refuses by name.

- `hammunition install <unit>` (the unit named in the line) asks again for just
  that unit and, if the publisher still does not answer, refuses with its last
  answer instead of deferring.
- `hammunition status` keeps listing the deferral for as long as that was your
  latest transaction.
- An **HTTP 404** on a sheet is a different message and a different fix: the
  carried index is stale, and the line names `scripts/gen_ustopo_index.py
  --fetch`. That is not an outage and is never deferred.
- Retry lines on stderr (`retrying (attempt 2 of 3)`) show only on a terminal,
  or with `HAMMUNITION_PROGRESS=1` in front.

## <a name="dead-url"></a>A source build fails to fetch — HTTP 404

```
Failed: [fetch] https://…/foo-1.2.3.tar.gz … returned HTTP 404 (Not Found)
```

A pinned upstream URL moved or the project stopped publishing that artifact.
This is a catalog bug, not your machine — the manifest's URL needs updating.
[Open an issue](https://github.com/ChiefGyk3D/Hammunition/issues) with the package name, or if you
maintain a checkout, run the sweep that catches these:

```sh
scripts/check_artifact_urls.py
```

It knocks on every pinned URL in the catalog and reports the dead ones,
keeping them apart from hosts that merely flaked today.

## <a name="git-editor"></a>A git build stops in a text editor

```
  $ git -C …/build/comaps-…/src tag -f v2026.08.31-14 FETCH_HEAD
  GNU nano …   .git/TAG_EDITMSG
## Write a message for tag:
```

Your own git configuration turned a plain tag into a signed one. With
`tag.gpgsign true` (or `tag.forceSignAnnotated true`) in `~/.gitconfig`,
`git tag NAME` creates an annotated tag, which needs a message, so git opens
your editor and the install waits in it. Nothing is wrong with the build.

Engines from v0.20.0 on run every git step with the operator's signing
settings turned off for that one command and with no editor and no terminal
prompt, so this cannot recur. On an older engine, type any word, save and
leave the editor (`Ctrl+O`, `Enter`, `Ctrl+X` in nano); if signing then fails
for want of a key, the step fails and a rerun of the same command resumes
from the cache once the engine is updated. Your git configuration is never
changed.

## <a name="parrot-backports"></a>apt refuses with "held broken packages" on Parrot

```
E: Unable to correct problems, you have held broken packages.
   … libcurl4t64 … is selected as a downgrade …
```

Seen on **Parrot Security** with backports enabled: its backports stream ships
updated runtime libraries (libcurl, GTK, SDL2, some Qt6), but the *base*
`-dev` packages a source build needs conflict with them. The remedy is to take
the development packages from backports too:

```sh
sudo apt-get install -t echo-backports <the -dev packages the plan named>
```

The engine's failure text lists exactly which packages apt could not reconcile
— those are the ones to pull from backports. This is a distribution-state
issue, not a catalog one; Debian and Kali do not show it.

## <a name="venv"></a>`python3 -m venv` fails with ensurepip

```
The virtual environment was not created successfully because ensurepip is
not available.
```

A **Debian netinst** ships no `python3-venv`, which the engine's source and
hybrid backends need. One command:

```sh
sudo apt install python3-venv
```

Parrot and Kali ship it. A future `.deb` install of Hammunition will carry its
own virtualenv and remove this step entirely.

## <a name="deb-conflict"></a>A vendor .deb is refused for a file collision

```
wsjtx-improved: its vendor .deb collides with installed distribution
package(s): wsjtx-data
   → remove them first (sudo apt-get remove wsjtx-data) …
```

This is **the engine protecting you**, not failing. `wsjtx-improved`'s vendor
`.deb` ships a file that the distribution's `wsjtx-data` (a `jtdx` dependency)
also owns, with no `Replaces` header, so installing it would leave dpkg's
database inconsistent. The engine refuses at plan time and names the remedy —
remove the conflicting package first if you want the improved build, or keep
what you have. It never removes a distribution package silently (D-022).

## <a name="refused"></a>A package is "refused by name" for a backend or repo

```
code: requires third-party apt repositories (microsoft-vscode) that this
engine cannot add yet
```

Also not a failure. The engine will not pretend to support something it cannot
actually do — adding a third-party apt repository with a pinned signing key is
a disclosed modification it does not yet implement, so it refuses by name and
tells you to install that one package by hand. A capability matrix that
reported coverage the engine does not have would be the lie this rule exists to
prevent. The rest of your transaction is unaffected; install the named package
yourself, or choose one that needs no third-party repo.
