# Teams Office Flatpak

An unofficial Flatpak package of Teams Office: [Teams for Linux](https://github.com/IsmaelMartinez/teams-for-linux),
the unofficial Microsoft Teams client, with an Office bridge that lets AI
agents on your computer work in the Word documents and Excel workbooks you
have open in Teams. Agents can read and change Excel cells and formulas, and
read Word paragraphs and replace their text. The changes go through an Office
add-in, so Office saves them and coauthors see them as usual.

This repository only contains the packaging. The app, including the Office
bridge, lives in [nosini/teams-for-linux-mcp](https://github.com/nosini/teams-for-linux-mcp);
Teams for Linux itself is developed upstream.

## Installing

Install [Flatpak](https://flatpak.org/setup/) if you don't already have it,
then:

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user https://nosini.github.io/teams-office-flatpak/teams-office.flatpakref
```

This adds a remote named `teams-office`. Updates come through it like any
other Flatpak, from your software center or with:

```sh
flatpak update --user eu.nosini.TeamsOffice
```

If an update causes problems, the `teams-office` remote still has the five
previous versions. List them and go back to one by its commit:

```sh
flatpak remote-info --user --log teams-office eu.nosini.TeamsOffice
flatpak update --user --commit=COMMIT eu.nosini.TeamsOffice
```

`flatpak mask --user eu.nosini.TeamsOffice` then keeps it from updating until
you run `flatpak mask --user --remove eu.nosini.TeamsOffice`.

Teams Office is also available from the shared
[nosini remote](https://github.com/nosini/flatpak-repo), together with the
other packages published there.

## Using it

Start **Teams Office** from your application menu, or with:

```sh
flatpak run eu.nosini.TeamsOffice
```

Sign in to Teams. Agents can open Word and Excel documents in independent
background tabs and import the Office Bridge automatically. They can also
create a Word document in the current folder or another existing SharePoint
folder. Sign-in, MFA and your organization's add-in policy can require your
interaction.

Point your agent at the bridge's private socket:

```text
~/.var/app/eu.nosini.TeamsOffice/config/teams-for-linux/mcp/bridge.sock
```

The [Office agents guide](https://github.com/nosini/teams-for-linux-mcp/blob/main/docs/office-agents.md)
explains the tools, background tabs, automatic setup, how to export a small
MCP relay and how to pass the socket into a container.

For manual setup, open a Word or Excel file with **Edit in Teams**. In
Office's **Add-ins** menu, choose **Upload My Add-in** and select the
corresponding manifest:

```text
~/.var/app/eu.nosini.TeamsOffice/config/teams-for-linux/mcp/excel-addin.xml
~/.var/app/eu.nosini.TeamsOffice/config/teams-for-linux/mcp/word-addin.xml
```

Keep the **Teams Office Bridge** pane open until it says **Ready for local
agent access**. Each document needs its own pane.

The paths above are the defaults; Teams Office prints the real ones when it
starts from a terminal. Expose only the socket to agents, never the whole
`mcp` folder: it also holds the private key of the add-in's local
certificate.

Reads give the agent short-lived tokens. If someone else changes the same
cells or paragraph in the meantime, the write is refused and the agent has to
read again.

### Differences from a regular install

- Teams Office has its own app ID, so it installs next to the regular Teams
  for Linux Flatpak or package. You sign in to it separately, and its
  settings are kept in `~/.var/app/eu.nosini.TeamsOffice`.
- The bridge and its add-in are switched on at every start; you don't need
  to change `config.json`.
- Document-session retention is enabled. Session-only SharePoint sign-in
  cookies get a local expiry of up to seven days, so opening a document can
  keep working after a restart. Existing server expiry, sign-out and
  organizational authentication requirements still apply. You can turn it
  off for a launch with
  `flatpak run eu.nosini.TeamsOffice --mcp.documentSession.enabled=false`.
- The add-in is served from `https://127.0.0.1:39847`. Only one copy of Teams
  with the Office bridge can run at a time.

## Permissions

- **Display and audio:** Wayland with an X11 fallback, and PulseAudio for
  calls and notification sounds.
- **All devices:** for the GPU, webcams in video calls and security keys
  for signing in. Chromium opens these devices itself, and Flatpak has no
  narrower permission that covers cameras and security keys.
- **Network:** for Teams, and for the add-in host on 127.0.0.1 that the Office
  pane loads its files from.
- **Downloads folder:** to save files from Teams. Other files are opened and
  saved through the desktop's file chooser.
- **PipeWire:** for sharing your screen in calls.
- **Desktop services:** notifications, the tray icon, preventing the screen
  saver during calls, unread badges on the launcher, and noticing when the
  computer suspends and resumes.

Teams Office has no access to your home folder or to the regular Teams for
Linux profile. Agents only reach it through the socket in its own data
folder.

## License

The packaging files in this repository are licensed under the GNU Affero
General Public License, version 3 (see [LICENSE](LICENSE)). Teams for Linux
and the Office bridge are under the GNU General Public License, version 3 or
later; see the [app's repository](https://github.com/nosini/teams-for-linux-mcp).

Building it yourself, publishing, and how the package works are described
in [docs/development.md](docs/development.md).
