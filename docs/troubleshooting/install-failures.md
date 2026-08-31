<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# When an install fails

Every failure the engine reports names what it was doing and stops there —
resolution finishes before installation, so a failure is a report, not a
half-installed machine. What you do next depends on which of these it is.

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
