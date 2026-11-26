#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT_ENV = os.getenv("LINGOREEL_ARTIFACT_DIR", "").strip()
ARTIFACT_DIR = Path(_ARTIFACT_ENV) if _ARTIFACT_ENV else None
RELEASES_DIR = ROOT / "releases"
RELEASES_DIR.mkdir(parents=True, exist_ok=True)


def _inspect_macho64(data: bytes) -> tuple[int, int, bool]:
    """Return (cputype, cpusubtype, has_lc_code_signature) for a 64-bit little-endian Mach-O binary."""
    magic, cputype, cpusubtype, _filetype, ncmds, _sizeofcmds, _flags, _reserved = struct.unpack("<IIIIIIII", data[:32])
    if magic != 0xFEEDFACF:
        raise RuntimeError(f"Unexpected Mach-O magic: {hex(magic)}")
    has_cs = False
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack("<II", data[off : off + 8])
        if cmd == 0x1D:  # LC_CODE_SIGNATURE
            has_cs = True
        off += cmdsize
    return cputype, cpusubtype, has_cs


def build_universal_macos_launcher(out_path: Path, tmp_dir: Path) -> None:
    """Cross-compile macos/launcher/main.go to arm64 + amd64 and assemble an Apple Universal Fat Mach-O binary."""
    go_src = ROOT / "macos" / "launcher" / "main.go"
    if not go_src.is_file():
        raise FileNotFoundError(f"Missing Go launcher source: {go_src}")

    go_bin = shutil.which("go") or "/usr/local/go/bin/go"
    if not Path(go_bin).is_file():
        raise RuntimeError("Go toolchain not found; required to compile native macOS Universal Mach-O launcher")

    base_env = os.environ.copy()
    base_env["CGO_ENABLED"] = "0"
    base_env["PATH"] = f"/usr/local/go/bin:{base_env.get('PATH', '')}"

    slices: list[tuple[int, int, bytes]] = []
    for arch in ("amd64", "arm64"):
        slice_path = tmp_dir / f"LingoReelApp_{arch}"
        env = dict(base_env, GOOS="darwin", GOARCH=arch)
        subprocess.run(
            [go_bin, "build", "-trimpath", "-ldflags=-s -w", "-o", str(slice_path), str(go_src)],
            cwd=str(go_src.parent),
            env=env,
            check=True,
        )
        raw = slice_path.read_bytes()
        cputype, cpusubtype, has_cs = _inspect_macho64(raw)
        if arch == "arm64" and not has_cs:
            raise RuntimeError("arm64 Mach-O slice missing required LC_CODE_SIGNATURE!")
        print(f"    built darwin/{arch}: {len(raw)/1024:.1f} KB (cputype={hex(cputype)}, LC_CODE_SIGNATURE={has_cs})")
        slices.append((cputype, cpusubtype, raw))

    # Assemble Apple Universal Fat Mach-O (FAT_MAGIC 0xCAFEBABE, 16KB page alignment = 2^14 for Apple Silicon)
    align_bits = 14
    align_size = 1 << align_bits
    header_entries = []
    offset = align_size
    for cputype, cpusubtype, raw in slices:
        header_entries.append((cputype, cpusubtype, offset, len(raw), align_bits))
        offset = ((offset + len(raw) + align_size - 1) // align_size) * align_size

    buf = bytearray()
    buf += struct.pack(">II", 0xCAFEBABE, len(slices))
    for cputype, cpusubtype, off, size, abits in header_entries:
        buf += struct.pack(">IIIII", cputype, cpusubtype, off, size, abits)

    for (_cputype, _cpusubtype, off, _size, _abits), (_ct, _cst, raw) in zip(header_entries, slices):
        if len(buf) < off:
            buf += b"\x00" * (off - len(buf))
        buf += raw

    out_path.write_bytes(bytes(buf))
    os.chmod(out_path, 0o755)

    file_out = subprocess.run(["file", str(out_path)], capture_output=True, text=True)
    print(f"[✓] Built Universal Mach-O Launcher: {out_path.name} ({len(buf)/1024:.1f} KB)")
    if file_out.stdout.strip():
        print("   ", file_out.stdout.strip())


def write_apple_png_icns(src_png: Path, out_dir: Path) -> Path:
    """Build a genuine modern Apple Retina PNG-backed .icns directly from transparent 1024x1024 RGBA squircle."""
    img = Image.open(src_png).convert("RGBA")
    w, h = img.size
    if (w, h) != (1024, 1024):
        img = img.resize((1024, 1024), Image.Resampling.LANCZOS)

    # Hard-assert corners are 100% transparent (ZERO white residue outside squircle!)
    for pt in ((0, 0), (1023, 0), (0, 1023), (1023, 1023), (12, 12), (1011, 12)):
        px = img.getpixel(pt)
        assert px[3] == 0, f"Icon corner {pt} is opaque ({px}) — refusing to ship icon with white corners!"

    # All standard modern Apple macOS PNG-backed ICNS OSTypes (16px up to 1024px Retina)
    icon_slots: list[tuple[bytes, int]] = [
        (b"icp4", 16),    # 16x16
        (b"icp5", 32),    # 32x32
        (b"ic11", 32),    # 16x16@2x
        (b"icp6", 64),    # 64x64
        (b"ic12", 64),    # 32x32@2x
        (b"ic07", 128),   # 128x128
        (b"ic13", 256),   # 128x128@2x
        (b"ic08", 256),   # 256x256
        (b"ic14", 512),   # 256x256@2x
        (b"ic09", 512),   # 512x512
        (b"ic10", 1024),  # 512x512@2x (1024x1024)
    ]

    png_cache: dict[int, bytes] = {}
    chunks = bytearray()
    for ostype, sz in icon_slots:
        if sz not in png_cache:
            resized = img if sz == 1024 else img.resize((sz, sz), Image.Resampling.LANCZOS)
            # Confirm top-left corner stays pure transparent at every size
            assert resized.getpixel((0, 0))[3] == 0, f"Non-transparent corner at size {sz}"
            bio = io.BytesIO()
            resized.save(bio, format="PNG", optimize=True)
            png_cache[sz] = bio.getvalue()
        payload = png_cache[sz]
        chunks += ostype + struct.pack(">I", 8 + len(payload)) + payload

    total_len = 8 + len(chunks)
    icns_path = out_dir / "AppIcon.icns"
    icns_path.write_bytes(b"icns" + struct.pack(">I", total_len) + bytes(chunks))
    return icns_path


def hash_directory(directory: Path) -> str:
    """Compute a deterministic SHA-256 fingerprint of all SwiftUI source files."""
    h = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(directory).as_posix()
        if "/.build/" in f"/{rel}/" or rel.startswith(".build/") or p.name == ".DS_Store":
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def build_macos_dmg_and_zip() -> None:
    # 1. Verify bash syntax of all macOS scripts
    cmd_script = ROOT / "启动Lingo.command"
    for script in (ROOT / "macos" / "LingoReelApp", ROOT / "macos" / "bootstrap.sh", ROOT / "macos" / "build_swift_dmg.sh", cmd_script):
        if script.exists():
            os.chmod(script, 0o755)
            subprocess.run(["bash", "-n", str(script)], check=True)
    hud_jxa = ROOT / "macos" / "setup_progress.jxa"
    if hud_jxa.exists():
        os.chmod(hud_jxa, 0o755)
        subprocess.run(
            [
                "node",
                "-e",
                "const fs=require('fs'),vm=require('vm');const s=fs.readFileSync(process.argv[1],'utf8').replace(/^#!.*\\n/,'');new vm.Script(s,{filename:process.argv[1]});",
                str(hud_jxa),
            ],
            check=True,
        )
    print("[✓] All macOS shell & JXA scripts passed syntax check")

    # 2. Build fresh frontend production bundle
    subprocess.run(["npm", "run", "build"], cwd=str(ROOT / "frontend"), check=True)
    print("[✓] Rebuilt frontend/dist cleanly")

    with tempfile.TemporaryDirectory(prefix="lingo_dmg_build_") as tmp:
        tmp_dir = Path(tmp)
        icns_file = write_apple_png_icns(ROOT / "macos" / "LingoAppIcon.png", tmp_dir)
        info_out = subprocess.run(["icns2png", "-l", str(icns_file)], capture_output=True, text=True)
        print(f"[✓] Generated transparent Apple Retina PNG-backed AppIcon.icns ({icns_file.stat().st_size / 1024:.1f} KB):")
        for ln in (info_out.stdout or "").splitlines()[:10]:
            print("   ", ln)

        # 3. Assemble Lingo.app bundle with native Universal Fat Mach-O + SwiftUI source + Playful 3D GUI
        dmg_stage = tmp_dir / "dmg_stage"
        app_root = dmg_stage / "Lingo.app"
        macos_dir = app_root / "Contents" / "MacOS"
        res_dir = app_root / "Contents" / "Resources"
        res_backend = res_dir / "backend"
        res_frontend = res_dir / "frontend" / "dist"
        res_swift = res_dir / "native-app"

        macos_dir.mkdir(parents=True)
        res_backend.mkdir(parents=True)

        shutil.copy2(ROOT / "macos" / "Info.plist", app_root / "Contents" / "Info.plist")
        (app_root / "Contents" / "PkgInfo").write_bytes(b"APPL????")
        build_universal_macos_launcher(macos_dir / "LingoReelApp", tmp_dir)

        shutil.copy2(icns_file, res_dir / "AppIcon.icns")
        shutil.copy2(ROOT / "frontend" / "public" / "lingo-logo.png", res_dir / "lingo-logo.png")
        shutil.copy2(ROOT / "macos" / "bootstrap.sh", res_dir / "bootstrap.sh")
        os.chmod(res_dir / "bootstrap.sh", 0o755)
        if hud_jxa.exists():
            shutil.copy2(hud_jxa, res_dir / "setup_progress.jxa")
            os.chmod(res_dir / "setup_progress.jxa", 0o755)

        # Bundle complete SwiftUI source tree + backend + frontend before computing unified fingerprint
        shutil.copytree(
            ROOT / "macos" / "native-app",
            res_swift,
            ignore=shutil.ignore_patterns(".build", ".swiftpm", ".DS_Store"),
        )
        for py_file in sorted((ROOT / "backend").glob("*.py")):
            shutil.copy2(py_file, res_backend / py_file.name)
        shutil.copy2(ROOT / "backend" / "requirements.txt", res_backend / "requirements.txt")
        shutil.copytree(ROOT / "backend" / "assets", res_backend / "assets")
        shutil.copytree(ROOT / "frontend" / "dist", res_frontend)

        # Write deterministic frontend/backend payload build ID so launcher, SwiftUI, PyQt6, and /api/health
        # can detect stale running processes or cached bundles across upgrades
        payload_hash = hashlib.sha256()
        for part_name, part_dir in (("frontend", res_frontend), ("backend", res_backend)):
            for p in sorted(part_dir.rglob("*")):
                if not p.is_file() or p.name == ".lingo_build_id" or p.name == ".DS_Store":
                    continue
                payload_hash.update(f"{part_name}/{p.relative_to(part_dir).as_posix()}".encode("utf-8"))
                payload_hash.update(b"\x00")
                payload_hash.update(p.read_bytes())
                payload_hash.update(b"\x00")
        build_id = payload_hash.hexdigest()[:12]
        (res_frontend / ".lingo_build_id").write_text(build_id + "\n", encoding="utf-8")
        (ROOT / "frontend" / "dist" / ".lingo_build_id").write_text(build_id + "\n", encoding="utf-8")

        # Include SwiftUI source + backend + frontend + Info.plist + brand assets in swift_source.sha256
        # so cached on-device SwiftUI Lingo-<hash>.app automatically refreshes whenever UI or backend updates
        full_hash = hashlib.sha256()
        full_hash.update(hash_directory(res_swift).encode("utf-8"))
        full_hash.update(b"\x00")
        full_hash.update(build_id.encode("utf-8"))
        full_hash.update(b"\x00")
        for extra_file in (
            app_root / "Contents" / "Info.plist",
            res_dir / "lingo-logo.png",
            res_dir / "AppIcon.icns",
        ):
            full_hash.update(extra_file.name.encode("utf-8"))
            full_hash.update(b"\x00")
            full_hash.update(extra_file.read_bytes())
            full_hash.update(b"\x00")
        swift_hash = full_hash.hexdigest()
        (res_dir / "swift_source.sha256").write_text(swift_hash + "\n", encoding="utf-8")
        print(f"[✓] Bundled native SwiftUI + Web payload (build_id={build_id}, swift_sha256={swift_hash[:12]}...)")

        # Verify the staged .app backend + redesigned Playful 3D native desktop GUI boot cleanly
        test_data = tmp_dir / "app_test_data"
        env = os.environ.copy()
        env["LINGOREEL_DATA_DIR"] = str(test_data)
        env["LINGOREEL_FRONTEND_DIST"] = str(res_frontend)
        env["LINGOREEL_DESKTOP_APP"] = "1"
        env["LINGOREEL_VENV_DIR"] = str(ROOT / "backend" / ".venv")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["QT_QPA_PLATFORM"] = "offscreen"
        subprocess.run(
            [
                str(ROOT / "backend" / ".venv" / "bin" / "python"),
                "-B",
                "-c",
                (
                    "import main, db, desktop_console, desktop_native_gui\n"
                    "db.init_db()\n"
                    "assert main.FRONTEND_DIST.is_dir()\n"
                    "assert main._is_desktop_mode()\n"
                    "assert (main.FRONTEND_DIST / 'lingo-logo.png').is_file()\n"
                    "assert (main.FRONTEND_DIST / 'lingo-icon.png').is_file()\n"
                    "info = desktop_console.inspect_environment()\n"
                    "assert info['core_ready']\n"
                    "from PyQt6.QtWidgets import QApplication\n"
                    "app = QApplication([])\n"
                    "win = desktop_native_gui.LingoReelNativeWindow(enable_ipc=False, enable_tray=False)\n"
                    "assert 'Lingo' in win.windowTitle() and '词影精研' not in win.windowTitle()\n"
                    "for sid in ('citrus', 'lavender', 'ceramic'):\n"
                    "    win.apply_skin(sid)\n"
                    "win._cleanup_before_exit()\n"
                    "win.close()\n"
                    "print('APP_BUNDLE_AND_NATIVE_GUI_SELF_TEST_OK')\n"
                ),
            ],
            cwd=str(res_backend),
            env=env,
            check=True,
        )

        # Add /Applications symlink & guide inside DMG root
        os.symlink("/Applications", dmg_stage / "Applications")
        shutil.copy2(ROOT / "macOS安装说明.txt", dmg_stage / "安装说明.txt")

        # 4. Build modern HFS+ macOS DMG via xorriso (compatible with macOS 12–15 Sequoia!)
        dmg_primary = RELEASES_DIR / "Lingo-macOS.dmg"
        if dmg_primary.exists():
            dmg_primary.unlink()

        subprocess.run(
            [
                "xorriso",
                "-as",
                "mkisofs",
                "-V",
                "Lingo",
                "-hfsplus",
                "-apm-block-size",
                "2048",
                "-R",
                "-J",
                "-no-pad",
                "-o",
                str(dmg_primary),
                str(dmg_stage),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        inspect = subprocess.run(
            ["xorriso", "-indev", str(dmg_primary), "-find", "/Lingo.app", "-maxdepth", "3"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"[✓] Built HFS+ macOS DMG: {dmg_primary} ({dmg_primary.stat().st_size / 1024:.1f} KB)")
        print("    Contents sample:", len(inspect.stdout.splitlines()), "entries inside Lingo.app")

        # 5. Refresh the macOS zip package
        zip_primary = RELEASES_DIR / "lingo-macos.zip"
        if zip_primary.exists():
            zip_primary.unlink()

        with zipfile.ZipFile(zip_primary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            prefix = "Lingo-macOS"
            for name in ("README.md", "LICENSE", "macOS安装说明.txt", "启动Lingo.command"):
                fp = ROOT / name
                if fp.is_file():
                    zf.write(fp, f"{prefix}/{name}")
            for py_file in sorted((ROOT / "backend").glob("*.py")):
                zf.write(py_file, f"{prefix}/backend/{py_file.name}")
            zf.write(ROOT / "backend" / "requirements.txt", f"{prefix}/backend/requirements.txt")
            for asset in sorted((ROOT / "backend" / "assets").rglob("*")):
                if asset.is_file():
                    zf.write(asset, f"{prefix}/backend/{asset.relative_to(ROOT / 'backend')}")
            for dist_file in sorted((ROOT / "frontend" / "dist").rglob("*")):
                if dist_file.is_file():
                    zf.write(dist_file, f"{prefix}/frontend/dist/{dist_file.relative_to(ROOT / 'frontend' / 'dist')}")
            for swift_file in sorted(res_swift.rglob("*")):
                if swift_file.is_file():
                    zf.write(swift_file, f"{prefix}/macos/native-app/{swift_file.relative_to(res_swift)}")
            for rel_macos in ("macos/Info.plist", "macos/LingoAppIcon.png", "macos/build_swift_dmg.sh", "macos/bootstrap.sh", "macos/setup_progress.jxa"):
                fp = ROOT / rel_macos
                if fp.is_file():
                    zf.write(fp, f"{prefix}/{rel_macos}")
        print(f"[✓] Refreshed macOS ZIP: {zip_primary} ({zip_primary.stat().st_size / 1024:.1f} KB)")

        if ARTIFACT_DIR is not None and ARTIFACT_DIR.is_dir():
            shutil.copy2(dmg_primary, ARTIFACT_DIR / "Lingo-macOS.dmg")
            shutil.copy2(zip_primary, ARTIFACT_DIR / "lingo-macos.zip")
            print("[✓] Copied DMG and ZIP to artifacts directory")


if __name__ == "__main__":
    build_macos_dmg_and_zip()
