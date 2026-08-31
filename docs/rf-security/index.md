<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# RF security and SIGINT

> **Maintainer review required before this is authoritative.** This page is a
> careful draft that follows the project's established principle — *disclose
> capability, never adjudicate law* (D-021) — but the legal framing on this
> subject is the kind that gets quoted back, and it should carry the
> maintainer's own review and voice before it is treated as final. It is
> published as a draft because the section is a 1.0 requirement and existing to
> be reacted to is more useful than being absent.

Hammunition carries RF-security, SIGINT and RF-research tooling alongside its
amateur-radio software. That is the whole reason the project exists: the
operator who wants amateur radio *and* SDR *and* RF security on one machine has
been carrying two laptops. This section is about using that capability
**responsibly and lawfully**, which is entirely your responsibility and not
something any software can decide for you.

## What this project does, and does not, do

**We disclose. We do not adjudicate.** Every profile whose lawful use depends on
your authorization is *consent-gated*: installing it requires an affirmative act
that `--yes` cannot supply, and it prints, before installing anything, exactly
what the tools can do. `hammunition show rf-research` is that disclosure. The
gate names risk *categories* — capabilities like unlicensed transmission,
interception of protected communications, identifier collection, spectrum
disruption — and stops there. **It does not tell you whether your specific use
is legal.** Only you, knowing your jurisdiction, your authorization, and your
intent, can answer that, and this project will not pretend to answer it for you.

This is deliberate and consistent: the same discipline governs how the catalog
handles everything with a legal dimension. Disclose the capability plainly;
point at the law; let the operator decide.

## The law you are operating under (not legal advice)

This is orientation, not counsel, and it is not exhaustive. **Consult primary
sources and, where the stakes warrant, a lawyer.** At least two bodies of law
commonly intersect for this tooling, and their intersection is not obvious:

- **Radio regulation.** In the United States, amateur operation is governed by
  **47 CFR Part 97**; transmission generally requires a licence and is confined
  to your privileges, and Part 97 has specific rules about, for example,
  obscuring the meaning of communications and causing interference. Other
  countries have their own regulators and rules (Ofcom, ISED, ACMA, and so on).
  Receiving is treated very differently from transmitting, and the line this
  project's own scoping draws — receive broadly, transmit under tight,
  consent-gated conditions — mirrors that.
- **Computer-crime and wiretap law.** Software that intercepts communications,
  collects identifiers, or interacts with systems you do not own can implicate
  statutes far outside radio law — in the US, the **Computer Fraud and Abuse
  Act**, the **Wiretap Act / ECPA**, and their state equivalents. "It was
  transmitted over the air" is not a blanket exemption; the details matter, and
  they vary by jurisdiction and by what you do with what you capture.

The **intersection** is where people go wrong: an action that is fine under
radio law can still violate computer-crime or privacy law, and vice versa. When
in doubt, the safe posture is receive-only, on spectrum and systems you are
authorized for, keeping nothing you are not entitled to keep.

## Responsible-use posture

The project's own position, which you inherit when you install this tooling:

- **Authorization first.** Use these capabilities only where you have the
  authority to — your own equipment and spectrum, a documented engagement, a
  CTF or research context with defined scope, licensed operation within your
  privileges.
- **Least capability for the task.** The gates and profiles are structured so
  you opt into exactly the capability you need, not a blanket "security mode."
- **Nothing hidden.** Every system modification is printed before it happens
  and recorded after. If a tool can transmit, the disclosure says so.
- **Receive is not a free pass.** Interception and collection have their own
  legal weight even without transmitting. Treat captured data as something you
  may not be entitled to keep.

## Where the gated tooling lives

RF-security and SIGINT tools are in the `rf-security` and `rf-research`
profiles, both consent-gated, both post-1.0 for the fuller SIGINT set. Read the
gate before you install: `hammunition show rf-research`. The gate is the
contract — it tells you what you are taking on, and asks you to accept it
deliberately.
