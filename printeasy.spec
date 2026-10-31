# PyInstaller build recipe for PrintEasy (works on Windows, macOS and Linux).
#   pyinstaller --noconfirm printeasy.spec
# Output: dist/PrintEasy/ (Windows, Linux) or dist/PrintEasy.app (macOS)
import sys

block_cipher = None
is_mac = sys.platform == "darwin"
is_win = sys.platform.startswith("win")

a = Analysis(
    ["run_printeasy.py"],
    pathex=["."],
    datas=[("packaging/assets/printeasy.png", "assets")],
    hiddenimports=["zeroconf._utils.ipaddress", "zeroconf._handlers.answers"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PrintEasy",
    console=False,                       # no black terminal window
    icon="packaging/assets/printeasy.ico" if is_win else "packaging/assets/printeasy.icns" if is_mac else None,
    version="packaging/windows/version_info.txt" if is_win else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PrintEasy")

if is_mac:
    app = BUNDLE(
        coll,
        name="PrintEasy.app",
        icon="packaging/assets/printeasy.icns",
        bundle_identifier="com.printeasy.app",
        info_plist={
            "CFBundleDisplayName": "PrintEasy",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            # macOS asks the person before an app may look at the local network or Wi-Fi names.
            "NSLocalNetworkUsageDescription":
                "PrintEasy looks for printers on your home or office network so you can connect to them.",
            "NSBonjourServices": ["_ipp._tcp", "_ipps._tcp", "_printer._tcp", "_pdl-datastream._tcp"],
            "NSLocationWhenInUseUsageDescription":
                "macOS needs Location permission before apps can see Wi-Fi network names. "
                "PrintEasy uses it only to list Wi-Fi networks for printer setup.",
        },
    )
