<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Writing and publishing the documentation

The documentation is one tree, `docs/`, and four things are built from it.
Nothing is written anywhere else.

| Output | Built by | Where it goes |
|---|---|---|
| The site | `mkdocs build --strict`, `.github/workflows/pages.yml` | <https://chiefgyk3d.github.io/Hammunition/> |
| The GitHub wiki | `scripts/gen_wiki.py`, `.github/workflows/wiki.yml` | the repository's wiki, replaced on every push to `main` |
| The offline bundle | `scripts/build_offline_bundle.py`, `.github/workflows/docs-bundle.yml` | a zip: [Offline documentation](../offline/index.md) |
| The package pages | `scripts/gen_package_reference.py` | `docs/packages/`, from the manifests |

**Never edit the wiki.** The next push replaces it. **Never edit a generated
page** (`docs/packages/*`, `docs/profiles/*`, `docs/projects.md`,
`docs/reference/*` where a generator is named in its header): change the
manifest and regenerate.

## Who owns what

So that two copies do not drift apart, each fact has one home.

| Fact | Owner | Everything else |
|---|---|---|
| What an application is, how it installs, launches, works offline | its manifest's `documentation:` block | the generated package page; guides link to it |
| What a companion project does, its internals | that project's own repository | the [suite page](../suite/index.md) summarises and links; it states the version the catalog pins |
| How the engine behaves | the code, then `docs/reference/cli.md` | guides link, never restate flags |
| A workflow (maps, packet, time) | its guide under `docs/guides/` | the [EMCOMM pages](../emcomm/index.md) link to the guide, and add only what the field needs |
| Why a choice was made | `docs/DECISIONS.md` | cite the decision id |

A suite page that disagrees with its project's repository is a bug in the
suite page. When the catalog pins a different version than the repository's
README describes, say so on the page.

## When you change an application or a feature

The change is not done until the documentation is. In the same pull request:

1. **A new or changed application:** fill the manifest's `documentation:`
   fields (`what_it_does`, `why_you_want_it`, `prerequisites`,
   `known_problems`, `upstream_url`, `upstream_support`) and, where the
   unit works without the internet or has a first task worth writing down,
   `offline` and `first_task`. Use the [application template](template-application.md).
   Then regenerate: `python scripts/gen_package_reference.py`,
   `gen_profile_reference.py`, `gen_projects_page.py`.
2. **A new companion project:** a page under `docs/suite/` from the
   [suite project template](template-suite-project.md), a row in
   `docs/suite/index.md`, a nav entry, and a manifest.
3. **A new page:** add it to the nav in `mkdocs.yml` in the same commit.
4. **A changelog fragment** in `changelog.d/`.

Mark what is not known: *implemented*, *experimental*, *planned* or *unverified*
(not run on hardware). Never invent a command, flag or option to fill a gap;
read it from the code or leave the gap named.

## Check it

```sh
python scripts/gen_package_reference.py --check
python scripts/gen_wiki.py --check
python scripts/check_doc_links.py
mkdocs build --strict
python scripts/build_offline_bundle.py
pytest tests/test_docs_generated.py tests/test_site.py tests/test_wiki.py tests/test_suite_docs.py tests/test_offline_bundle.py
```

The tests fail on a page that is in no nav, a link that points nowhere, a
generated page that is stale, a suite page whose repository link disagrees with
its manifest, and an offline bundle that reaches outside its own folder.

## Publication

- **The site** publishes from `main` with `pages.yml`.
- **The wiki** publishes from `main` with `wiki.yml`. It needs the wiki's
  first page created once in the GitHub UI, because the wiki's git remote does
  not exist before that. Until someone with admin access does, the publish job
  fails naming that step. This is a standing owner action, not something a pull
  request can do.
- **The bundle** is built by the `Docs bundle` workflow and attached to the run
  as an artifact. Attaching it to a release is not set up.
