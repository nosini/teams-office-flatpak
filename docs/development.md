# Development

## How the package works

The app is the `feature/mcp-office` branch of
[nosini/teams-for-linux](https://github.com/nosini/teams-for-linux): Teams
for Linux with the Office MCP bridge and its Word and Excel add-ins. Its
releases are tagged `office-vVERSION`, after the Teams for Linux version they
are based on. A later app release on the same version adds a revision, such as
`office-v2.27.0-1`. The manifest pins such a tag and its commit.

The `teams-office` module builds that checkout the way upstream builds its
Linux packages, with electron-builder, but offline: `npm ci` installs from
an npm cache made of the sources in `generated-sources.json`, and
electron-builder takes the Electron release for the build's architecture
(`electronDist`) and Electron's headers from the same sources. With the
headers, it compiles the one native module, cbor-extract, from source.
Install scripts are skipped; they would only download Electron and
Playwright's test browsers. The unpacked app goes to
`/app/teams-office`, next to the Electron2 BaseApp's Zypak, which provides
Chromium's sandbox inside Flatpak.

`launcher/teams-office` starts it with `--mcp.enabled --mcp.addin.enabled
--mcp.documentSession.enabled`, so the bridge, automatic setup and bounded
document-session retention are enabled without changes to `config.json`.
The app's default retention is seven days; existing cookie expiry and sign-out
are respected. An explicit `--mcp.documentSession.enabled=false` argument
disables retention for that launch; the wrapper then omits its default flag
to avoid duplicate values in the app's parser. The app ID
differs from the upstream Flatpak's, so both can be installed and keep
separate profiles. libcbor and libfido2 provide the `fido2-assert` tool that
Teams for Linux uses for security-key sign-in, as in the upstream Flatpak.

The permissions follow the upstream Flatpak, with two exceptions: Downloads
instead of the whole home folder, and no `org.gtk.Notifications`, which
Electron doesn't use. The README explains each one.

## Layout

- `eu.nosini.TeamsOffice.yml`: the Flatpak manifest.
- `eu.nosini.TeamsOffice.metainfo.xml` and `.desktop`: software-center
  metadata and launcher. The icon comes from the app's source.
- `generated-sources.json`: the pinned npm packages and Electron downloads,
  generated from the app's `package-lock.json` by
  `scripts/generate-node-deps.sh`.
- `launcher/teams-office`: the start script installed as `/app/bin/teams-office`.
- `lint-exceptions.json`: linter errors that don't apply to a self-hosted
  repository, each with its reason.
- `tests/check-installed.sh`: checks that run inside the installed app.
- `scripts/test-installed.sh`: installs a local build and runs those checks.
- `scripts/prepare-repository.sh`: signs tested builds for publishing.
- `scripts/update-upstream.sh`: turns the update checker's changes into a
  pull request.
- `scripts/tests/`: tests for these scripts.
- `scripts/builder-tools.sh`: fetches the pinned
  [flatpak-builder-tools](https://github.com/flatpak/flatpak-builder-tools).

A checkout of the app in `upstream/` is ignored by Git. It is handy for
reading the source.

## Building

The simplest way to build is with `org.flatpak.Builder` from Flathub. It
contains flatpak-builder and the linter in the versions Flathub uses:

```sh
flatpak install --user flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --install-deps-from=flathub \
  --default-branch=stable --force-clean --repo=repo build-dir eu.nosini.TeamsOffice.yml
```

The build downloads the pinned sources, including an Electron release, so
it needs a network connection.
Building from a checkout installs the app from a local remote named
`eu.nosini.TeamsOffice-origin`. Once the build directories are gone,
`flatpak update` warns that it can't reach it. Switch to the published
remote as the README describes, or disable it with
`flatpak remote-modify --user --disable eu.nosini.TeamsOffice-origin`.

To get a single-file bundle instead of installing:

```sh
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
  repo teams-office.flatpak eu.nosini.TeamsOffice stable
```

## Checking

CI runs the same linter checks as Flathub. Run them locally with:

```sh
alias lint='flatpak run --command=flatpak-builder-lint org.flatpak.Builder'
lint --exceptions --user-exceptions lint-exceptions.json manifest eu.nosini.TeamsOffice.yml
lint appstream eu.nosini.TeamsOffice.metainfo.xml
lint --exceptions --user-exceptions lint-exceptions.json repo repo
```

Only add an exception when the rule doesn't apply to a package published
outside Flathub, and say why in `lint-exceptions.json`.

To run the checks inside the installed app, build without `--install` (but
with `--repo=repo`), then run:

```sh
bash scripts/test-installed.sh
```

The script adds a `local-test` remote for `repo/`, installs the app from
it and runs `tests/check-installed.sh` with `flatpak run`, so the checks see
the Platform runtime the app runs with, not the SDK. It refuses to replace
an existing installation. Afterwards, remove the test installation with
`flatpak --user uninstall eu.nosini.TeamsOffice` and the remote with
`flatpak --user remote-delete local-test`.

## Debugging

A shell in the sandbox of the last build, without installing it:

```sh
flatpak run org.flatpak.Builder --run build-dir eu.nosini.TeamsOffice.yml sh
```

A shell in the installed app's sandbox, with the SDK and its debugging tools
in place of the Platform runtime (the SDK must be installed):

```sh
flatpak run --devel --command=sh eu.nosini.TeamsOffice
```

To see which D-Bus names the app tries to reach, and so which `--talk-name`
permissions it needs:

```sh
flatpak run --log-session-bus eu.nosini.TeamsOffice 2>&1 | grep '(required 1)'
```

Permissions granted through portals, such as notifications or background
running, are listed with `flatpak permission-show eu.nosini.TeamsOffice` and
cleared with `flatpak permission-reset eu.nosini.TeamsOffice`.

## GitHub Actions

`.github/workflows/flatpak.yml` runs for pushes of `v*` version tags, pull
requests and manual runs. It checks out the event's exact commit, including
on reruns. Ordinary branch pushes run only the lightweight Checks workflow.
For each architecture, it lints the manifest and metainfo,
builds with [flatpak-github-actions](https://github.com/flatpak/flatpak-github-actions),
lints the exported build, runs the installed-app checks and uploads an
installable bundle as an artifact. Install a downloaded artifact with
`flatpak install --user teams-office-x86_64.flatpak`. Bundles are unsigned and
don't update; the published repository does.

Like Flathub, CI builds for x86_64 and aarch64. If the app can't work on one
of them, add a `flathub.json`, for example `{"only-arches": ["x86_64"]}`.
The aarch64 build uses GitHub's Arm runners, which are free for public
repositories only.

`.github/workflows/checks.yml` lints the scripts and workflows, checks that
the manifest and metadata files parse, and runs the tests in
`scripts/tests/`. The publishing test makes small fake builds and publishes
them several times to a local web server.

### Build cache

CI restores `.flatpak-builder`, including downloaded sources, completed
module results and the C/C++ compiler cache. Flatpak checks the inputs and
rebuilds affected modules when sources, dependencies, patches or the SDK
change. Lint and installed-app checks still run on every build, and the
cache is saved only after they pass.

Each run saves a fresh snapshot, separated by app ID, architecture, Flatpak
branch and build workflow version, which includes the CI container image.
The next run restores the newest compatible snapshot. To start a new cache
namespace, bump `flatpak-v1` in both the key and restore prefix in the
workflow. Cache misses build normally.

GitHub lets tags and pull requests restore the default branch's cache,
but caches from one tag cannot be restored by another tag. To populate a
shared cache in a package repository without publishing or creating a
release, run the workflow on `main` with **cache_only** selected, or use:

```sh
gh workflow run flatpak.yml --ref main -f cache_only=true
```

Run this from the package repository's checkout.

Refresh it before releases when needed. GitHub removes caches unused for
more than seven days and evicts older entries when the repository's storage
limit is reached; see its [cache access and retention rules](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

### Publishing

When the repository variable `PUBLISH_FLATPAK` is `true`, stable version
tags and manual runs on `main` without **cache_only** publish a signed
Flatpak repository to GitHub Pages. A separate job, which never runs
upstream build code, downloads the published repository and checks it
against the signing key. It adds the tested builds
of all architectures as new signed commits, generates static deltas, signs a
new software catalog and summary, and writes `teams-office.flatpakrepo` and
`teams-office.flatpakref` with the public key embedded. Both files take the app's
summary from its metainfo and point to a copy of its icon, which software
centers show when the remote or app is added. Before deploying, a fresh
remote that only knows the public key must accept the result.

The repository keeps the five previous versions of the app and each
extension, so users can go back to one with `flatpak update --commit`. A
build whose files didn't change adds no version. Static deltas let Flatpak
download an install or update as a few large files instead of one request
per file. They add about a third to the repository's size, and each kept
version adds only the files that changed. If the published repository can't
be downloaded or doesn't match the signing key, for example after replacing
the key, the job fails. Set the variable `FLATPAK_KEEP_HISTORY` to `false`
to publish a new repository without the earlier versions.

The repository URL defaults to `https://OWNER.github.io/REPOSITORY/`. For a
custom domain, set the `FLATPAK_REPO_URL` variable to the real URL,
including the trailing slash.

To set publishing up:

1. In **Settings → Pages**, select **GitHub Actions** as the source.
2. Store the signing key as the secret `FLATPAK_GPG_PRIVATE_KEY` (see
   below).
3. Set the variable:
   `gh variable set PUBLISH_FLATPAK --body true --repo nosini/teams-office-flatpak`.
4. In **Settings → Environments → github-pages**, allow version tags to
   deploy. With **Selected branches and tags**, add a **Tag** rule `v*` and
   retain the **Branch** rule `main` for manual publication. These are
   separate rules; allowing `main` alone does not allow tags. See GitHub's
   [deployment branch and tag rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).
5. Push a stable version tag, or run the workflow manually on `main`.

### Releases

Push a tag such as `v1.2.3` on the commit to package. A numeric packaging
revision, such as `v1.2.3-1`, is also stable. Other suffixes, such as
`v1.2.4-rc1`, are prereleases: they build and test, but never publish to the
stable Flatpak repository and never become the latest stable GitHub Release.
Tag this repository with the version of the app tag it packages, such as
`v2.27.0` for `office-v2.27.0` and `v2.27.0-1` for `office-v2.27.0-1`. Both
repositories share the revision numbers: a packaging change alone takes the
next unused revision, and the next app release on that version skips it.

After all architecture builds and tests succeed, and after signing,
verification and Pages deployment succeed when publication is enabled, a
separate job creates the GitHub Release and attaches the tested `.flatpak`
bundles. It uses the runner's `GITHUB_TOKEN` with `contents: write`; no
manual GitHub Release or additional release token is needed. With
`PUBLISH_FLATPAK` disabled, tag builds still create a release with bundles.
Manual branch builds do not create releases.

Reruns replace matching assets on an existing release, finish an interrupted
draft after uploading its assets, and enforce prerelease status before
uploading assets for prerelease tags. Release assets must remain mutable
for replacement on reruns. Release publication does not trigger another
packaging build. Bundles remain unsigned; signed updates come from the
Flatpak repository.

### Signing key

The key has to be an ASCII-armored GnuPG private key without a passphrase.
An existing Flatpak signing key can be reused. To make a new one, generate
it on your own machine, outside the source checkout, in a separate GnuPG
directory:

```sh
mkdir -p -m 700 "$HOME/.gnupg-flatpak/private-keys-v1.d"
gpgconf --homedir "$HOME/.gnupg-flatpak" --create-socketdir
gpg --homedir "$HOME/.gnupg-flatpak" --batch --pinentry-mode loopback \
  --passphrase '' --quick-generate-key 'Nosini Flatpak signing' ed25519 sign 0
```

Upload it through a private temporary file, so a failed export can't upload
an empty secret:

```sh
(
  set -eu
  umask 077
  key_file=$(mktemp "$HOME/.gnupg-flatpak/export.XXXXXX")
  trap 'rm -f "$key_file"' EXIT
  gpg --homedir "$HOME/.gnupg-flatpak" --armor \
    --export-secret-keys 'Nosini Flatpak signing' > "$key_file"
  test -s "$key_file"
  gh secret set FLATPAK_GPG_PRIVATE_KEY --repo nosini/teams-office-flatpak < "$key_file"
)
```

Keep a backup of the key. Installed copies trust the public key from the
`.flatpakref` they were installed with, so replacing the key breaks their
updates.

### Shared remote

[flatpak-repo](https://github.com/nosini/flatpak-repo) collects the
published packages into the shared `nosini` remote. After the first
publication, add an entry for this app to its `apps.json`, listing every
extension the build exports. This one exports `Debug`, for the native
libraries; Electron keeps its translations in the app, so there is no
`Locale`.

## Updating

`.github/workflows/update.yml` runs
[flatpak-external-data-checker](https://github.com/flathub-infra/flatpak-external-data-checker)
every Monday at 05:17 UTC, and on manual runs. It follows the
`x-checker-data` of each source in the manifest: the newest `office-v*` tag
of the app, and the libcbor and libfido2 releases. When the app's tag is
newer, it updates the pins, adds a release to the metainfo file and
regenerates `generated-sources.json` from the new commit's lockfile. It
pushes the change to the `update/upstream` branch, opens a pull request and
starts the Flatpak build of that branch. Its result shows on the pull
request. After merging the pull request, push a version tag on the commit to
publish the update.

The workflow needs **Allow GitHub Actions to create and approve pull
requests** under **Settings → Actions → General**.

To merge updates without review, set the variable `AUTO_MERGE_UPDATES` to
`true`. The workflow then waits for the build, merges the pull request when
the build and the installed-app checks pass. Publication still waits for a
version tag; auto-merge does not dispatch a publishing build on `main`. A
failed build leaves the pull request open.

Changes pushed to `update/upstream` by anyone but the workflow are kept:
while the pull request is open, later runs commit newer releases on top of
them, comment on the pull request and leave it for review even with
`AUTO_MERGE_UPDATES`. Once the pull request is closed or merged, the next
update starts again from `main`. If someone pushes to the branch while the
workflow runs, the run fails instead of replacing the branch; the next one
picks the push up.

GitHub disables scheduled workflows in public repositories after 60 days
without activity. Re-enable the workflow under **Actions** if that happens.

### Releasing a new app version

In the app's repository, tag the commit to package and push the tag:

```sh
git tag -s office-v2.27.0 -m 'Teams Office 2.27.0'
git push origin office-v2.27.0
```

Then wait for the update workflow, or run it from this repository's
checkout with `gh workflow run update.yml`.

## npm dependencies

`generated-sources.json` holds every package in the app's
`package-lock.json`, including the development tools the build needs, the
Electron release for each architecture and Electron's headers for compiling
native modules. After changing the app's commit
by hand, regenerate it:

```sh
bash scripts/generate-node-deps.sh
```

The script reads the commit from the manifest, fetches that commit's
lockfile and runs flatpak-node-generator from flatpak-builder-tools in a
virtual environment under `.cache/`. To use a lockfile from a commit that
isn't pushed yet, pass it with `LOCKFILE=path/to/package-lock.json`.

The generator also adds Playwright's browsers, which upstream uses for its
end-to-end tests. The script leaves them out: they are only downloaded by
install scripts, which the build doesn't run, and are several hundred
megabytes.

## Moving to a newer runtime

Change `runtime-version` and `base-version` in the manifest and the image
tag in `.github/workflows/flatpak.yml` and `checks.yml` (`freedesktop-26.08`).
The Electron2 BaseApp and the Node.js SDK extension must exist for the new
version.
