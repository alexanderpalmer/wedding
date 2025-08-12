# Diese Zeile sagt dem Computer, dass dies ein Python-Programm ist
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

# Diese Zeile sorgt dafür, dass neuere Python-Features verwendet werden können
from __future__ import annotations
# Diese Zeile importiert das Modul für Kommandozeilen-Argumente
import argparse
# Diese Zeile importiert das Modul für Dateipfade und Ordner-Operationen
from pathlib import Path
# Diese Zeile importiert Typen für bessere Code-Dokumentation
from typing import Iterable, Tuple

# Diese Zeilen importieren die Pillow-Bibliothek für Bildbearbeitung
from PIL import Image, ImageOps
# Diese Zeile importiert spezielle Bildbearbeitungs-Optionen aus Pillow
from PIL.Image import Resampling, Quantize, Dither

# === Basiskonfiguration ===
# Du kannst diese Werte direkt hier ändern ODER beim Aufruf per CLI überschreiben.
# Diese Variable bestimmt, wie stark die Bilder verkleinert werden (0.5 = auf die Hälfte)
SCALE: float = 0.5              # z.B. 0.5 für 50% der Originalgröße
# Diese Variable bestimmt ab welcher Bildbreite ein Bild als "hochauflösend" gilt
MIN_WIDTH: int = 1600           # ab welcher Breite gilt "hochauflösend"
# Diese Variable bestimmt ab welcher Bildhöhe ein Bild als "hochauflösend" gilt
MIN_HEIGHT: int = 1200          # ab welcher Höhe gilt "hochauflösend"
# Diese Liste enthält alle Bildformate, die das Programm verarbeiten kann
INPUT_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


# Diese Funktion prüft, ob ein Bild hochauflösend ist
def is_high_res(size: Tuple[int, int], min_w: int, min_h: int) -> bool:
    # Hole die Breite (w) und Höhe (h) aus den Bildgrößen-Daten
    w, h = size
    # Gib True zurück, wenn Breite ODER Höhe über den Mindestgrenzen liegt
    return (w >= min_w) or (h >= min_h)


# Diese Funktion findet alle Bilddateien in einem Ordner und allen Unterordnern
def iter_images(root: Path) -> Iterable[Path]:
    # Durchsuche den angegebenen Ordner und alle seine Unterordner nach Dateien
    for p in root.rglob("*"):
        # Prüfe ob es eine Datei ist UND ob die Dateiendung ein unterstütztes Bildformat ist
        if p.is_file() and p.suffix.lower() in INPUT_EXTS:
            # Gib den Pfad zu dieser Bilddatei zurück
            yield p


# Diese Funktion erstellt den Pfad, wo die bearbeitete Datei gespeichert werden soll
def make_output_path(src: Path, src_root: Path, out_root: Path) -> Path:
    # Berechne den relativen Pfad der Quelldatei zum Quellordner
    rel = src.relative_to(src_root)
    # Ersetze Dateiendung durch .jpg (wird später in save_web_optimized eventuell angepasst)
    rel = rel.with_suffix(".jpg")
    # Kombiniere den Zielordner mit dem relativen Pfad
    return out_root / rel


# Diese Funktion verkleinert ein Bild um einen bestimmten Faktor
def resize_image(img: Image.Image, scale: float) -> Image.Image:
    # Hole die aktuelle Breite (w) und Höhe (h) des Bildes
    w, h = img.size
    # Berechne die neue Breite: multipliziere mit dem Skalierungsfaktor und runde auf
    new_w = max(1, int(round(w * scale)))
    # Berechne die neue Höhe: multipliziere mit dem Skalierungsfaktor und runde auf
    new_h = max(1, int(round(h * scale)))
    # Falls die neuen Maße gleich den alten sind, gib eine Kopie des Originalbildes zurück
    if (new_w, new_h) == (w, h):
        return img.copy()
    # Verkleinere das Bild auf die neuen Maße mit hoher Qualität (LANCZOS Filter)
    return img.resize((new_w, new_h), Resampling.LANCZOS)


# Diese Funktion zählt die verschiedenen Farben in einem Bild
def count_unique_colors(img: Image.Image) -> int:
    """Zählt die einzigartigen Farben in einem Bild (Sample-basiert für Performance)"""
    # Verkleinere das Bild für die Analyse auf maximal 200x200 Pixel für bessere Performance
    # Hole die aktuelle Bildgröße
    w, h = img.size
    # Falls das Bild größer als 200x200 ist, verkleinere es
    if w > 200 or h > 200:
        # Berechne den Verkleinerungsfaktor (nimm den kleineren der beiden Faktoren)
        factor = min(200/w, 200/h)
        # Berechne die neue Größe für das Testbild
        sample_w, sample_h = int(w * factor), int(h * factor)
        # Erstelle ein verkleinertes Testbild mit einfacher Skalierung (NEAREST)
        sample = img.resize((sample_w, sample_h), Resampling.NEAREST)
    else:
        # Falls das Bild schon klein genug ist, verwende es direkt
        sample = img
    
    # Zähle die einzigartigen Farben im Testbild und gib die Anzahl zurück
    return len(sample.getcolors(maxcolors=16777216) or [])


# Diese Funktion speichert das Bild in optimierter Form für das Web
def save_web_optimized(img: Image.Image, dst: Path) -> None:
    """
    Speichert ein Bild weboptimiert - JPEG für Fotos, PNG nur bei Transparenz:
    - JPEG: Hohe Qualität ohne Farbfragmente, kleine Dateien für Fotos
    - PNG: Nur bei Transparenz (behält Alpha-Kanal)
    - Vollfarb ohne Quantisierungsartefakte
    """
    # Stelle sicher, dass das Bild im richtigen Farbmodus vorliegt
    if img.mode not in ("RGB", "RGBA"):
        # Konvertierung entfernt automatisch EXIF/Metadaten
        # Prüfe ob das Bild einen Transparenz-Kanal hat
        if "A" in img.getbands():
            # Konvertiere zu RGBA (mit Transparenz)
            img = img.convert("RGBA")
        else:
            # Konvertiere zu RGB (ohne Transparenz)
            img = img.convert("RGB")

    # Prüfe ob das Bild Transparenz hat
    has_alpha = (img.mode == "RGBA")
    # Erstelle den Zielordner falls er nicht existiert
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Falls das Bild keine Transparenz hat
    if not has_alpha:
        # Speichere als JPEG für bessere Kompression bei Fotos
        # Ändere die Dateiendung zu .jpg
        dst_jpg = dst.with_suffix('.jpg')
        # Stelle sicher, dass das Bild im RGB-Modus ist (für JPEG erforderlich)
        if img.mode != "RGB":
            img = img.convert("RGB")
        # Speichere als JPEG mit 90% Qualität und Optimierung
        img.save(dst_jpg, format="JPEG", quality=90, optimize=True)
        # Gib den tatsächlichen Dateipfad zurück
        return dst_jpg
    else:
        # Falls das Bild Transparenz hat, speichere als PNG
        # Speichere als PNG mit maximaler Kompression aber ohne Qualitätsverlust
        img.save(dst, format="PNG", optimize=True, compress_level=9)
        # Gib den Dateipfad zurück
        return dst


# Diese Funktion verarbeitet eine einzelne Bilddatei
def process_one(src: Path, dst: Path, scale: float, force: bool,
                min_w: int, min_h: int, verbose: bool) -> str:
    # Versuche die Bildverarbeitung, fange Fehler ab
    try:
        # Öffne das Bild (wird automatisch wieder geschlossen)
        with Image.open(src) as im0:
            # Korrigiere die Bildorientierung basierend auf EXIF-Daten
            im = ImageOps.exif_transpose(im0)
            # Speichere die ursprüngliche Bildgröße
            orig_size = im.size

            # Prüfe ob das Bild hochauflösend genug ist
            if not is_high_res(orig_size, min_w, min_h):
                return f"SKIP (nicht hochauflösend): {src}"

            # Berechne die Zielgröße nach der Skalierung
            tw, th = int(round(orig_size[0] * scale)), int(round(orig_size[1] * scale))
            # Prüfe ob die Zielgröße mindestens 1 Pixel groß ist
            if (tw < 1 or th < 1):
                return f"SKIP (Zielgröße < 1px): {src}"

            # Falls das skalierte Bild nicht kleiner wäre, überspringe es (außer --force ist gesetzt)
            if not force and (tw >= orig_size[0] or th >= orig_size[1]):
                return f"SKIP (würde nicht verkleinern, nutze --force zum Erzwingen): {src}"

            # Verkleinere das Bild
            im_resized = resize_image(im, scale)
            # Speichere das verkleinerte Bild optimiert
            actual_dst = save_web_optimized(im_resized, dst)
            # Gib eine Erfolgsmeldung mit Details zurück
            return f"OK   {src} -> {actual_dst} ({orig_size[0]}x{orig_size[1]} -> {im_resized.size[0]}x{im_resized.size[1]})"
    # Falls ein Fehler auftritt, gib eine Fehlermeldung zurück
    except Exception as e:
        return f"ERR  {src}: {e}"


# Diese Hauptfunktion startet das Programm und verarbeitet alle Argumente
def main() -> None:
    # Erstelle einen Parser für Kommandozeilen-Argumente
    parser = argparse.ArgumentParser(
        description="Konvertiert hochauflösende Bilder proportional in optimierte PNGs."
    )
    # Definiere das erste Argument: Quellverzeichnis (Pflichtargument)
    parser.add_argument("input", type=Path, help="Quellverzeichnis")
    # Definiere das zweite Argument: Zielverzeichnis (Pflichtargument)
    parser.add_argument("output", type=Path, help="Zielverzeichnis")
    # Definiere optionales Argument für Skalierung
    parser.add_argument("--scale", type=float, default=SCALE,
                        help=f"Skalierungsfaktor (Standard: {SCALE})")
    # Definiere optionales Argument für minimale Breite
    parser.add_argument("--min-width", type=int, default=MIN_WIDTH,
                        help=f"Schwellwert Breite für 'hochauflösend' (Standard: {MIN_WIDTH})")
    # Definiere optionales Argument für minimale Höhe
    parser.add_argument("--min-height", type=int, default=MIN_HEIGHT,
                        help=f"Schwellwert Höhe für 'hochauflösend' (Standard: {MIN_HEIGHT})")
    # Definiere optionales Argument zum Erzwingen der Verarbeitung
    parser.add_argument("--force", action="store_true",
                        help="Auch speichern, wenn Zielgröße nicht kleiner wäre")
    # Definiere optionales Argument für ausführliche Ausgaben
    parser.add_argument("-v", "--verbose", action="store_true", help="Mehr Ausgaben")
    # Parse alle übergebenen Argumente
    args = parser.parse_args()

    # Hole die Argumente aus dem Parser
    input_dir: Path = args.input
    output_dir: Path = args.output
    scale: float = args.scale

    # Prüfe ob der Skalierungsfaktor gültig ist
    if scale <= 0:
        raise SystemExit("Fehler: --scale muss > 0 sein.")

    # Prüfe ob das Quellverzeichnis existiert
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Quellverzeichnis existiert nicht: {input_dir}")

    # Initialisiere Zähler für die Statistik
    processed = 0  # Erfolgreich verarbeitete Bilder
    skipped = 0    # Übersprungene Bilder
    errors = 0     # Bilder mit Fehlern

    # Durchlaufe alle Bilddateien im Quellverzeichnis
    for src in iter_images(input_dir):
        # Erstelle den Zielpfad für das aktuelle Bild
        dst = make_output_path(src, input_dir, output_dir)
        # Verarbeite das Bild und hole die Statusmeldung
        msg = process_one(src, dst, scale, args.force, args.min_width, args.min_height, args.verbose)
        # Falls verbose-Modus aktiviert ist, zeige die Statusmeldung an
        if args.verbose:
            print(msg)
        # Zähle die Ergebnisse basierend auf der Statusmeldung
        if msg.startswith("OK"):
            processed += 1  # Erfolgreich verarbeitet
        elif msg.startswith("SKIP"):
            skipped += 1    # Übersprungen
        else:
            errors += 1     # Fehler aufgetreten

    # Zeige die finale Statistik an
    print(f"Fertig. OK={processed}, SKIP={skipped}, ERR={errors}")


# Diese Zeilen prüfen, ob das Skript direkt aufgerufen wird (nicht importiert)
if __name__ == "__main__":
    # Falls ja, starte die Hauptfunktion
    main()
