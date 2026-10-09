"""istek.txt içindeki 'Copy as cURL' çıktısından (veya ham header'lardan) browser.json üretir."""

import re
import sys
from pathlib import Path

import ytmusicapi

BASE = Path(__file__).parent
SRC = BASE / "istek.txt"


def headers_from_text(text):
    if "curl" not in text[:50].lower():
        return text  # zaten ham header formatı
    # Windows cmd formatındaki ^ kaçışlarını temizle
    text = re.sub(r"\^(.)", r"\1", text)
    args = re.findall(r"""(-H|--header|-b|--cookie)\s+(["'])(.*?)\2""", text, flags=re.S)
    lines = []
    for flag, _, value in args:
        lines.append(f"cookie: {value}" if flag in ("-b", "--cookie") else value)
    return "\n".join(lines)


def main():
    if not SRC.exists() or not SRC.read_text(encoding="utf-8").strip():
        sys.exit("istek.txt boş veya yok. README'deki 3. adımı uygula.")
    headers = headers_from_text(SRC.read_text(encoding="utf-8"))
    out = sys.argv[1] if len(sys.argv) > 1 else str(BASE / "browser.json")
    try:
        ytmusicapi.setup(filepath=out, headers_raw=headers)
    except Exception as e:
        sys.exit(f"Olmadı: {e}\nmusic.youtube.com'daki bir 'browse' isteğini kopyaladığından emin ol.")
    if len(sys.argv) == 1:
        SRC.unlink()
    print("browser.json oluşturuldu. Şimdi: python sync.py --dry-run --limit 20")


if __name__ == "__main__":
    main()
