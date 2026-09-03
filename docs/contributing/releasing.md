# Releasing

A release is an annotated, **signed** git tag on `main`. The README has
promised signed tags since the first commit, because a tag anyone can verify
is the difference between "git, tagged releases" and a tarball on a download
site. `v0.7.0` (2026-09-02) is annotated but not signed: no key existed on
the maintainer's machine when it was cut. The first signed release is the
one after it, and this page is the procedure so it is not rediscovered each
time.

The identity behind a release is not one key. It is the **set** of keys in
`.github/allowed_signers`, each with the dates between which it was trusted.
That is what lets a key be added, moved to hardware, or retired after a loss
without touching a tag that was already cut. The first key is described
first because it is the one that exists soonest; the rest of the page is
what to do once there is more than one.

## Signing with an SSH key

Git signs with SSH keys since 2.34 and honours a key's validity window since
2.35 (below). It needs no GPG keyring and GitHub shows "Verified" for it
exactly as for GPG. The key is the maintainer's identity; **only the
maintainer generates it**, and it is a key used for nothing else — not the
one that opens the dev VMs, not the one that pushes.

One-time setup, on the release machine:

```sh
# 1. A dedicated key. Set a passphrase; the agent caches it per session.
ssh-keygen -t ed25519 -C "hammunition release signing" \
    -f ~/.ssh/hammunition_release_ed25519

# 2. Tell git to sign tags with it. --global is fine on a single-user
#    machine; --local keeps it to this clone.
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/hammunition_release_ed25519.pub
git config --global tag.gpgSign true

# 3. Register the PUBLIC half with GitHub as a *signing* key:
#    Settings -> SSH and GPG keys -> New SSH key -> Key type: "Signing Key".
#    The same key added as an authentication key does not count, and a key
#    can hold both roles -- the roles are separate lists.
cat ~/.ssh/hammunition_release_ed25519.pub
```

Local verification needs an allowed-signers file, because SSH signatures
carry no identity of their own. This repository carries one,
`.github/allowed_signers`, and it is the record; the line for a new key is
its principal, an optional validity window, and the public key:

```sh
printf '%s valid-after="%s" %s\n' 19499446+ChiefGyk3D@users.noreply.github.com \
    "$(date +%Y%m%d)" "$(cut -d' ' -f1,2 ~/.ssh/hammunition_release_ed25519.pub)" \
    >> .github/allowed_signers
git config --global gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
```

Back up the private key and its passphrase somewhere that is not this
machine. What a lost key costs is in [When a key is lost or
compromised](#when-a-key-is-lost-or-compromised); the short version is that
it costs a new key and a dated line in the file, never a re-signed tag.

## More than one key

GitHub accepts any number of signing keys on one account, and
`allowed_signers` is one line per key, all carrying the same principal. Every
key the maintainer has ever signed a release with stays in the file with the
window it was valid for; verification of an old tag then still succeeds after
that key is gone, because the check is made against the tag's own date:

```
# .github/allowed_signers
19499446+ChiefGyk3D@users.noreply.github.com valid-after="20260910" valid-before="20270301" ssh-ed25519 AAAA…   # file key, retired
19499446+ChiefGyk3D@users.noreply.github.com valid-after="20270201" sk-ssh-ed25519@openssh.com AAAA…            # YubiKey
```

The window is honoured by **git 2.35 and later** with **OpenSSH 8.8 or
later** — git passes the tag's timestamp to `ssh-keygen -Y verify` as
`-Overify-time`. Measured here (2026-09-03) on the two ends of that:
OpenSSH 8.9's `ssh-keygen` verifies a signature dated inside the window and
rejects the same signature dated after `valid-before` with `key has expired`;
git 2.34.1, which predates the option, verifies against the *current* time,
so on that git a retired key fails **every** tag it ever signed, however old.
Ubuntu 24.04 ships git 2.43 and OpenSSH 9.6; 22.04 ships 2.34.1 and is the
one place an operator will see the old behaviour.

Two keys at once is normal, not a transition state. A file key on the
release machine and a hardware key in a drawer can both be valid; a tag is
signed by whichever is at hand, and both verify. Sign the tag with one key —
git does not produce multi-signature tags, and the second key's value is
that it exists, not that it co-signs.

Trusting the file for the first time is the one step this repository cannot
do for an operator, because a file in the repository is only as trustworthy
as the checkout it came in. GitHub publishes an account's signing keys
separately from its authentication keys, without a login:

```sh
curl -s https://api.github.com/users/ChiefGyk3D/ssh_signing_keys
```

(`[]` as of 2026-09-03 — no key exists yet.) Compare that against
`.github/allowed_signers` and against the README's release section. If any
two of the three disagree, trust none of them and ask.

## Hardware keys

A private key that cannot be copied is the property both of these offer, and
the cost is the same: it cannot be backed up either. **Enrol two**, or keep a
file key alongside, before retiring anything.

### YubiKey, or any FIDO2 token

OpenSSH 8.2 and later generate keys whose private half lives on a FIDO2
token; git signs with them exactly as with a file key, with a touch per
signature. A **resident** key can be loaded onto another machine from the
token alone, which is the backup story for the key file itself (not for the
token):

```sh
# Needs libfido2 (Debian/Ubuntu: libfido2-1, pulled in by openssh-client).
# ed25519-sk needs YubiKey firmware 5.2.3+; ecdsa-sk works on older ones.
ssh-keygen -t ed25519-sk -O resident -O verify-required \
    -O application=ssh:hammunition-release \
    -C "hammunition release signing (yubikey)" \
    -f ~/.ssh/hammunition_release_sk

# On another machine, with the token plugged in: recover the key files.
ssh-keygen -K
```

`verify-required` means the token's PIN is asked before it will sign, which is
the difference between "someone has my key" and "someone has my key and my
PIN". Registering the public key with GitHub is the same *Signing Key* step as
above. **Whether GitHub accepts `sk-ssh-ed25519@openssh.com` in that role is
to be verified on the day it is added** — add it, sign a throwaway tag on a
branch, and look for "Verified" before writing its line into
`allowed_signers`. This page will say which way it went.

### Immurok

[Immurok](https://github.com/immurok) is a Bluetooth fingerprint
authenticator whose SSH feature is an **SSH agent with on-device ECDSA P-256
keys**: the key is generated on the device, the app sends a hash, the device
signs it after a fingerprint match, and the private half never leaves
([its security notes](https://github.com/immurok/immurok/blob/main/docs/security.md)).
It is **not** a FIDO2 token, so the `-sk` path above does not apply; its
route into git signing is the agent. Git and GitHub both accept
`ecdsa-sha2-nistp256`, and `ssh-keygen -Y sign` uses the agent whenever the
key it is handed is a public key, so the whole question is whether Immurok's
agent answers a signing request from `ssh-keygen` as it does one from `ssh`.

**Untested.** The measurement, with the Immurok daemon running and its
socket in `SSH_AUTH_SOCK`:

```sh
ssh-add -L                      # the device key should be listed
echo test > /tmp/t
ssh-keygen -Y sign -n git -f <(ssh-add -L | grep ecdsa-sha2-nistp256) /tmp/t
```

A fingerprint prompt and a `/tmp/t.sig` afterwards means it works, and the
`user.signingkey` line is then `key::ecdsa-sha2-nistp256 AAAA…` (the
`key::` prefix tells git the value is a literal key, not a file). No prompt,
or an agent error, means the Linux app does not yet serve that request, and
the result goes in this section either way.

As of 2026-09-03 the device is a pilot batch of fifty, its Linux companion
is a month-old Rust rewrite, the firmware is source-available (BSL 1.1) but
not rebuildable, and the keys cannot be exported. That is a **second** key,
with `valid-after` set to the day the test above passes — never the only
one.

## When a key is lost or compromised

Nothing already signed changes. Tags are not re-signed and history is not
rewritten; a moved tag is a rewrite every operator's clone notices, and it
would make the tags signed with the good key indistinguishable from the ones
that were not. The record of what happened is the validity window.

**Lost** (a dead disk, a token through the wash, a device whose company
folded): the key signed nothing it should not have. Close its window at the
last day it was in the maintainer's hands, generate the replacement, and
remove the lost key from GitHub:

```
… valid-after="20260910" valid-before="20270301" ssh-ed25519 AAAA…   # lost 2027-03-01
```

**Compromised** (the machine it lived on was, or it was seen somewhere it
should not have been): the window closes at the last date the key is *known*
to have been under control, not the date the compromise was noticed. Every
tag signed after that date is suspect. Each one is re-cut from the same
commit under a **new** version number with a surviving key — `v0.9.1` for a
suspect `v0.9.0` — and the release note of the new tag says why, in those
words. The suspect tag stays, and fails verification for anyone whose
`allowed_signers` is current, which is the point. Remove the key from GitHub
the same day.

GitHub's "Verified" badge on past tags follows whether the key is still
registered there, not the window; expect the badge on tags a removed key
signed to go, and treat the badge as a convenience. `.github/allowed_signers`
and `git verify-tag` are the record.

## Cutting a release

From an up-to-date `main` with a clean tree:

```sh
# 1. The version lives in one place.
sed -i 's/^version = ".*"/version = "0.8.0"/' pyproject.toml
git commit -am "release: v0.8.0"          # by pull request, like everything else

# 2. Once merged, tag the merge commit. -s signs; -a is implied.
git checkout main && git pull --ff-only
git tag -s v0.8.0 -m "v0.8.0"

# 3. Look at it before pushing. Both must say the tag is good.
git tag -v v0.8.0
git verify-tag v0.8.0

# 4. Push the tag alone.
git push origin v0.8.0
```

GitHub shows "Verified" on the tag once the signing key is registered.
A tag that shows "Unverified" is a tag to delete and re-cut, not to
explain: `git push --delete origin v0.8.0 && git tag -d v0.8.0`. (That is
the one case a tag moves: it was never verified, so nobody could have
trusted it.)

## What a release note says

The tag message is the release note. It names what changed for an operator
— which profiles install on which targets, which decisions changed the
engine's behaviour — with the evidence, not a commit list. The capability
matrix and `docs/reference/install-verification.md` are the record; the note
points at them.

## Verifying a release as an operator

```sh
git clone https://github.com/ChiefGyk3D/Hammunition
cd Hammunition
git config gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
git verify-tag v0.8.0
```

after checking the file against the maintainer's profile as described in
[More than one key](#more-than-one-key). A `key has expired` or `No
principal matched` from a tag *older* than the key's `valid-before` is the
git 2.34 behaviour, not a bad tag; run it on a machine with git 2.35 or
later. Until a key exists, `v0.7.0` is what there is, and it is unsigned.
