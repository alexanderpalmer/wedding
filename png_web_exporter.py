#!/usr/bin/env python3
"""
png_web_exporter.py
-------------------
Verkleinert (proportional) hochauflösende Bilder aus einem Quellverzeichnis
und speichert sie als webtaugliche PNGs im Zielverzeichnis.

Features
- Skalierungsfaktor einstellbar (Variable SCALE oder per CLI-Argument --scale)
- Nur "hochauflösende" Bilder werden verarbeitet (Schwellwert MIN_WIDTH/MIN_HEIGHT)
- Proportionale Verkleinerung mit hochwertigem LANCZOS-Filter
- Automatisches Drehen gemäß EXIF
- Entfernt Metadaten (durch Neuaufbau des Bildes)
- PNG-Optimierung:
    * Opaque Bilder werden vor dem Speichern auf 256 Farben quantisiert
    * Transparente Bilder werden ohne Quantisierung, aber mit Optimierung gespeichert
- Überspringt Bilder, die kleiner als Zielgröße wären (optional per --force erzwingen)

Benötigt: Pillow (PIL)
  pip install pillow
"""

from __future__ import annotations
import argparse
from pathlib import Path
from typing import Iterable, Tuple

from PIL import Image, ImageOps
from PIL.Image import Resampling, Quantize, Dither

# === Basiskonfiguration ===
# Du kannst diese Werte direkt hier ändern ODER beim Aufruf per CLI überschreiben.
SCALE: float = 0.5              # z.B. 0.5 für 50% der Originalgröße
MIN_WIDTH: int = 1600           # ab welcher Breite gilt "hochauflösend"
MIN_HEIGHT: int = 1200          # ab welcher Höhe gilt "hochauflösend"
INPUT_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def is_high_res(size: Tuple[int, int], min_w: int, min_h: int) -> bool:
    w, h = size
    return (w >= min_w) or (h >= min_h)


def iter_images(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in INPUT_EXTS:
            yield p


def make_output_path(src: Path, src_root: Path, out_root: Path) -> Path:
    rel = src.relative_to(src_root)
    # Ersetze Endung durch .jpg (wird ggf. in save_web_optimized angepasst)
    rel = rel.with_suffix(".jpg")
    return out_root / rel


def resize_image(img: Image.Image, scale: float) -> Image.Image:
    w, h = img.size
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    if (new_w, new_h) == (w, h):
        return img.copy()
    return img.resize((new_w, new_h), Resampling.LANCZOS)


def count_unique_colors(img: Image.Image) -> int:
    """Zählt die einzigartigen Farben in einem Bild (Sample-basiert für Performance)"""
    # Verkleinere für Analyse auf max 200x200 für Performance
    w, h = img.size
    if w > 200 or h > 200:
        factor = min(200/w, 200/h)
        sample_w, sample_h = int(w * factor), int(h * factor)
        sample = img.resize((sample_w, sample_h), Resampling.NEAREST)
    else:
        sample = img
    
    return len(sample.getcolors(maxcolors=16777216) or [])


def save_web_optimized(img: Image.Image, dst: Path) -> None:
    """
    Speichert ein Bild weboptimiert - JPEG für Fotos, PNG nur bei Transparenz:
    - JPEG: Hohe Qualität ohne Farbfragmente, kleine Dateien für Fotos
    - PNG: Nur bei Transparenz (behält Alpha-Kanal)
    - Vollfarb ohne Quantisierungsartefakte
    """
    # Sicherstellen, dass Bild in sinnvoller Farbraumform vorliegt
    if img.mode not in ("RGB", "RGBA"):
        # Konvertiert entfernt EXIF/Metadaten implizit
        if "A" in img.getbands():
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

    has_alpha = (img.mode == "RGBA")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not has_alpha:
        # JPEG für Fotos: Keine Farbfragmente, kleine Dateien, hohe Qualität
        # Ändere Dateiendung zu .jpg
        dst_jpg = dst.with_suffix('.jpg')
        # Konvertiere zu RGB für JPEG (falls noch nicht geschehen)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dst_jpg, format="JPEG", quality=90, optimize=True)
        return dst_jpg
    else:
        # Transparenz: PNG ohne Quantisierung
        img.save(dst, format="PNG", optimize=True, compress_level=9)
        return dst


def process_one(src: Path, dst: Path, scale: float, force: bool,
                min_w: int, min_h: int, verbose: bool) -> str:
    try:
        with Image.open(src) as im0:
            im = ImageOps.exif_transpose(im0)  # Orientierung korrigieren
            orig_size = im.size

            if not is_high_res(orig_size, min_w, min_h):
                return f"SKIP (nicht hochauflösend): {src}"

            # Zielgröße berechnen
            tw, th = int(round(orig_size[0] * scale)), int(round(orig_size[1] * scale))
            if (tw < 1 or th < 1):
                return f"SKIP (Zielgröße < 1px): {src}"

            # Wenn skaliertes Bild größer als Original (scale>1) oder kaum kleiner, ggf. überspringen
            if not force and (tw >= orig_size[0] or th >= orig_size[1]):
                return f"SKIP (würde nicht verkleinern, nutze --force zum Erzwingen): {src}"

            im_resized = resize_image(im, scale)
            actual_dst = save_web_optimized(im_resized, dst)
            return f"OK   {src} -> {actual_dst} ({orig_size[0]}x{orig_size[1]} -> {im_resized.size[0]}x{im_resized.size[1]})"
    except Exception as e:
        return f"ERR  {src}: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Konvertiert hochauflösende Bilder proportional in optimierte PNGs."
    )
    parser.add_argument("input", type=Path, help="Quellverzeichnis")
    parser.add_argument("output", type=Path, help="Zielverzeichnis")
    parser.add_argument("--scale", type=float, default=SCALE,
                        help=f"Skalierungsfaktor (Standard: {SCALE})")
    parser.add_argument("--min-width", type=int, default=MIN_WIDTH,
                        help=f"Schwellwert Breite für 'hochauflösend' (Standard: {MIN_WIDTH})")
    parser.add_argument("--min-height", type=int, default=MIN_HEIGHT,
                        help=f"Schwellwert Höhe für 'hochauflösend' (Standard: {MIN_HEIGHT})")
    parser.add_argument("--force", action="store_true",
                        help="Auch speichern, wenn Zielgröße nicht kleiner wäre")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mehr Ausgaben")
    args = parser.parse_args()

    input_dir: Path = args.input
    output_dir: Path = args.output
    scale: float = args.scale

    if scale <= 0:
        raise SystemExit("Fehler: --scale muss > 0 sein.")

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Quellverzeichnis existiert nicht: {input_dir}")

    processed = 0
    skipped = 0
    errors = 0

    for src in iter_images(input_dir):
        dst = make_output_path(src, input_dir, output_dir)
        msg = process_one(src, dst, scale, args.force, args.min_width, args.min_height, args.verbose)
        if args.verbose:
            print(msg)
        if msg.startswith("OK"):
            processed += 1
        elif msg.startswith("SKIP"):
            skipped += 1
        else:
            errors += 1

    print(f"Fertig. OK={processed}, SKIP={skipped}, ERR={errors}")


if __name__ == "__main__":
    main()
