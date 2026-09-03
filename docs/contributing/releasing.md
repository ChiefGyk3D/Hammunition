# Releasing

A release is an annotated, **signed** git tag on `main`. The README has
promised signed tags since the first commit, because a tag anyone can verify
is the difference between "git, tagged releases" and a tarball on a download
site. `v0.7.0` (2026-09-02) is annotated but not signed: no key existed on
the maintainer's machine when it was cut. The first signed release is the
one after it, and this page is the procedure so it is not rediscovered each
time.

## Signing with an SSH key

Git signs with SSH keys since 2.34 (Ubuntu 22.04's git is 2.34.1, so
every target here qualifies). It needs no GPG keyring and GitHub shows
"Verified" for it exactly as for GPG. The key is the maintainer's identity;
**only the maintainer generates it**, and it is a key used for nothing else —
not the one that opens the dev VMs, not the one that pushes.

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
#    The same key added as an authentication key does not count.
cat ~/.ssh/hammunition_release_ed25519.pub
```

Local verification needs an allowed-signers file, because SSH signatures
carry no identity of their own:

```sh
printf '%s %s\n' 19499446+ChiefGyk3D@users.noreply.github.com \
    "$(cut -d' ' -f1,2 ~/.ssh/hammunition_release_ed25519.pub)" \
    > ~/.config/git/allowed_signers
git config --global gpg.ssh.allowedSignersFile ~/.config/git/allowed_signers
```

Back up the private key and its passphrase somewhere that is not this
machine. A lost signing key is a new identity, and every previous tag then
verifies against a key GitHub no longer lists.

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
explain: `git push --delete origin v0.8.0 && git tag -d v0.8.0`.

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
git verify-tag v0.8.0
```

which needs the maintainer's public key in an allowed-signers file as above.
When the key exists, its public half goes in the README's release section
and on the maintainer's GitHub profile; if the two disagree, trust neither
and ask. Until then `v0.7.0` is what there is, and it is unsigned.
