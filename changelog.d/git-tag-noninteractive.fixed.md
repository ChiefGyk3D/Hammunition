- **A git build no longer stops in a text editor on a machine whose git signs
  tags.** `tag.gpgsign true` in the operator's `~/.gitconfig` turned the git
  backend's plain `git tag -f` into an annotated, signed tag, and nano opened
  inside a navigation install on the bench (2026-10-03). Every git step now
  runs with `GIT_TERMINAL_PROMPT=0` and `GIT_EDITOR=true`, and the tag step
  disables `tag.gpgSign` and `tag.forceSignAnnotated` for that one command;
  the operator's configuration is never changed. Two tests hold it, and
  `docs/troubleshooting/install-failures.md#git-editor` names the symptom.
