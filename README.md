# PrintEasy

**Connect any printer without the headache.** Made for people who aren't comfortable with computers:
big buttons, plain words, one job per screen.

| What it does | How |
|---|---|
| **Find a printer** on Wi-Fi or a network cable | Listens for printers announcing themselves (Bonjour/mDNS) and checks every address on the local network for printer ports (631 IPP, 9100 raw, 515 LPD). Shows name, model, status and ink levels. |
| **Connect in one click** | Driverless IPP first (works with almost every printer from the last ~10 years), then the maker's driver if installed, then a generic driver. Names it, makes it the main printer, prints a test page. |
| **Private vs public network** | Home/work = full automatic search. Café/hotel/airport = no scanning at all; connect by typing the printer's address. Windows' own Public/Private label is used automatically; on Mac/Linux it asks once per network and remembers. |
| **Plug in with USB** | Finds printers on the USB cable and sets them up for this computer only. |
| **Wi-Fi setup** | Join a Wi-Fi network, and a guided flow for getting a *new* printer onto home Wi-Fi via its setup network (`DIRECT-…`, `HP-Setup…`, `Canon_ij_…`). |
| **Fixed printer address** | Finds a free address on the network, shows the exact settings with Copy buttons, opens the printer's (or router's) settings page, then checks it worked and updates the computer. Fixes the #1 "printer is offline" cause. |
| **Printer for each program** | e.g. Word → office laser, Photos → colour printer. Switches the default printer while that program is in front and switches back afterwards. Runs quietly from the tray. |
| **It stopped working** | Checks network, main printer, whether each printer answers, paper/ink problems, and finds printers whose address changed — with a one-click fix. |

## Installers

| Computer | File | How a person installs it |
|---|---|---|
| Windows 10/11 | `PrintEasy-Setup-1.0.0-Windows.exe` | Double-click → Next → Install |
| Mac (Apple Silicon) | `PrintEasy-1.0.0-macOS-arm64.dmg` | Open → drag PrintEasy into Applications |
| Linux (Ubuntu, Mint, Debian…) | `PrintEasy-1.0.0-Linux-amd64.deb` | Double-click → Install |

### Building them

Each installer must be built on its own kind of computer. Two ways:

**Automatic (recommended):** put this folder in a GitHub repository and push a tag:
```
git tag v1.0.0 && git push origin v1.0.0
```
`.github/workflows/build.yml` runs the tests, builds all three installers on GitHub's Windows, Mac and Linux machines, and attaches them to a Release page you can share.

**By hand:**
- Windows: `powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1` (needs Python 3.11+ and Inno Setup 6)
- Mac: `bash packaging/macos/build_dmg.sh`
- Linux: `bash packaging/linux/build_deb.sh`

### Before giving it to the public: code signing
Unsigned apps trigger scary warnings that non-technical people won't click through.
- **Windows:** buy a code-signing certificate, set `WIN_SIGN_CERT` / `WIN_SIGN_PASSWORD` (the build script signs automatically).
- **Mac:** join the Apple Developer Program ($99/yr), set `MAC_SIGN_ID` and `MAC_NOTARY_PROFILE` (the build script signs and notarises).

## Run from source
```
pip install -r requirements.txt
python -m printeasy          # add --tray to start hidden in the tray
python -m pytest tests       # tests run on any OS, no printer needed
python tests/fake_printer.py --ip <your-ip>   # a pretend network printer for trying things out
```

## How it's built
```
printeasy/core/   no UI: network.py (private/public), discovery.py (mDNS + scan), ipp.py (talks to printers),
                  system_printers.py (Windows spooler / CUPS on Mac+Linux), wifi.py, ipassign.py,
                  apps.py (per-program printers), config.py, autostart.py
printeasy/ui/     PySide6 (Qt) screens, one file per screen
packaging/        icons, Windows Inno Setup, Mac .dmg, Linux .deb
```

## Known limits
- **Changing a printer's address** can't be done fully automatically from outside — there's no universal standard; every brand's settings page differs. PrintEasy does everything around that step and walks the person through it.
- **Linux on Wayland** (default on new Ubuntu/Fedora) doesn't let apps see which window is in front, so per-program printers switch based on which listed program was opened most recently.
- **Windows Wi-Fi list** needs Location turned on (Windows 11 24H2+); PrintEasy explains how if it's off. Wi-Fi text parsing assumes Windows is in English.
- **Mac** builds target Apple Silicon. For Intel Macs, run `build_dmg.sh` on an Intel Mac.
