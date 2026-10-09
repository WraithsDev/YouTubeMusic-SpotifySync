"""YouTube Music'te beğenilen şarkıları Spotify'da bir çalma listesine aktarır.

Kullanım:
    python sync.py              # aktar
    python sync.py --dry-run    # sadece eşleştir, Spotify'a yazma
    python sync.py --limit 50   # sadece ilk 50 beğeniyi işle
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from ytmusicapi import YTMusic

BASE = Path(__file__).parent
YT_AUTH_FILE = BASE / "browser.json"
STATE_FILE = BASE / "state.json"
NOT_FOUND_FILE = BASE / "bulunamayanlar.txt"
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"playlist_id": None, "synced": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_title(title):
    """'Şarkı (Official Video) [HD]' -> 'Şarkı'"""
    title = re.sub(r"[\(\[][^\)\]]*(official|video|audio|lyric|lyrics|hd|4k|mv|clip|klip|snippet)[^\)\]]*[\)\]]",
                   "", title, flags=re.I)
    title = re.sub(r"\s+-\s+topic$", "", title, flags=re.I)
    title = title.split(" | ")[0]  # "Şarkı | KANAL ADI"
    title = re.sub(r"\s+[—–]\s+", " - ", title)
    return re.sub(r"\s+", " ", title).strip()


VERSION_WORDS = ("instrumental", "karaoke", "sped up", "speed up", "slowed", "nightcore",
                 "acapella", "a cappella", "8d")


def unwanted_version(track, song):
    """Spotify sonucu enstrümantal/sped up vb. ise ve YouTube'daki öyle değilse True."""
    sp_name, yt_title = norm(track["name"]), norm(song["title"])
    return any(re.search(rf"\b{w}\b", sp_name) and not re.search(rf"\b{w}\b", yt_title)
               for w in VERSION_WORDS)


def norm(text):
    """Karşılaştırma için: küçük harf, Türkçe/aksan harfleri sadeleştir, noktalamayı at."""
    text = text.replace("ı", "i").replace("İ", "i").casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def core_title(title):
    """'Sil Baştan - 10 Mart Konseri' / 'Him & I (with Halsey)' -> 'sil bastan' / 'him i'"""
    title = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", title)
    return norm(title.split(" - ")[0])


def titles_match(a, b):
    a, b = core_title(a), core_title(b)
    if not a or not b:
        return False
    if SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    short, long_ = sorted((a, b), key=len)
    return short in long_ and len(short) / len(long_) >= 0.5


def artist_match(track, song):
    yt_artists = [norm(a) for a in song["artists"]]
    raw_title = norm(song["title"])
    for sa in (norm(a["name"]) for a in track["artists"]):
        if not sa:
            continue
        if any(sa == ya or sa in ya or ya in sa for ya in yt_artists if ya):
            return True
        if re.search(rf"\b{re.escape(sa)}\b", raw_title):
            return True
    return False


def get_liked_songs(limit):
    if not YT_AUTH_FILE.exists():
        sys.exit("browser.json bulunamadı. README'deki 'YouTube Music girişi' adımını uygula.")
    yt = YTMusic(str(YT_AUTH_FILE))
    data = yt.get_liked_songs(limit=limit)
    songs = []
    for t in data.get("tracks", [])[:limit]:
        if not t.get("videoId") or not t.get("title"):
            continue
        artists = [a["name"] for a in (t.get("artists") or []) if a.get("name")]
        songs.append({
            "id": t["videoId"],
            "title": t["title"],
            "artists": artists,
            "duration": t.get("duration_seconds"),
        })
    return songs


def spotify_client():
    for key in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        if not os.getenv(key):
            sys.exit(f"{key} eksik. .env.example dosyasını .env olarak kopyalayıp doldur.")
    auth = SpotifyOAuth(scope=SCOPES, cache_path=str(BASE / ".spotify_cache"), open_browser=True)
    return spotipy.Spotify(auth_manager=auth, requests_timeout=20, retries=5)


def find_on_spotify(sp, song):
    title = clean_title(song["title"])
    artist = song["artists"][0] if song["artists"] else ""
    # (başlık, sanatçı) denemeleri. Kullanıcı yüklemelerinde başlık çoğu zaman "Sanatçı - Şarkı" olur.
    attempts = [(title, artist)]
    if " - " in title:
        left, right = title.rsplit(" - ", 1)
        attempts.append((right, left.split(" - ")[-1]))

    queries = []
    for t, a in attempts:
        queries += [f"track:{t} artist:{a}" if a else f"track:{t}", f"{t} {a}".strip()]
    # "(feat. X)" gibi ekler Spotify aramasını bozabiliyor, eksiz hâlini de dene
    for t, a in attempts:
        bare = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", t).strip()
        if bare and bare != t:
            queries.append(f"{bare} {a}".strip())

    for q in dict.fromkeys(queries):
        items = sp.search(q=q, type="track", limit=5)["tracks"]["items"]
        good = [i for i in items
                if artist_match(i, song) and not unwanted_version(i, song) and any(titles_match(i["name"], t) for t, _ in attempts)]
        if not good:
            continue
        if song["duration"]:
            return min(good, key=lambda i: abs(i["duration_ms"] / 1000 - song["duration"]))
        return good[0]
    return None


def ensure_playlist(sp, state, name):
    if state["playlist_id"]:
        try:
            sp.playlist(state["playlist_id"], fields="id")
            return state["playlist_id"]
        except spotipy.SpotifyException:
            print("Kayıtlı çalma listesi bulunamadı, yenisi oluşturuluyor.")
            state["synced"] = {}

    body = {"name": name, "public": False,
            "description": "YouTube Music'te beğenilen şarkılardan otomatik oluşturuldu."}
    try:
        pl = sp._post("me/playlists", payload=body)
    except spotipy.SpotifyException:
        pl = sp.user_playlist_create(sp.me()["id"], **body)
    state["playlist_id"] = pl["id"]
    save_state(state)
    print(f"Çalma listesi oluşturuldu: {pl['external_urls']['spotify']}")
    return pl["id"]


def add_tracks(sp, playlist_id, uris):
    for i in range(0, len(uris), 100):
        chunk = uris[i:i + 100]
        try:
            sp._post(f"playlists/{playlist_id}/items", payload={"uris": chunk})
        except spotipy.SpotifyException:
            sp.playlist_add_items(playlist_id, chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Spotify'a yazmadan sadece eşleştir")
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek en fazla beğeni sayısı")
    parser.add_argument("--retry", action="store_true", help="Daha önce bulunamayanları tekrar ara")
    parser.add_argument("--log", action="store_true", help="Çıktıyı sync.log dosyasına yaz (zamanlanmış görev için)")
    args = parser.parse_args()

    if args.log:
        log = open(BASE / "sync.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n===== {datetime.now():%Y-%m-%d %H:%M} =====")

    load_dotenv(BASE / ".env")
    state = load_state()
    state.setdefault("missing", {})

    print("YouTube Music beğenileri alınıyor...")
    songs = get_liked_songs(args.limit)
    # En eski beğeni listede en üstte olsun
    songs.reverse()
    new_songs = [s for s in songs if s["id"] not in state["synced"]
                 and (args.retry or s["id"] not in state["missing"])]
    print(f"{len(songs)} beğeni bulundu, {len(new_songs)} tanesi yeni.")
    if not new_songs:
        return

    sp = spotify_client()
    found, not_found = [], []
    for n, song in enumerate(new_songs, 1):
        label = f"{', '.join(song['artists'])} - {song['title']}"
        track = find_on_spotify(sp, song)
        if track:
            found.append((song, track))
            print(f"[{n}/{len(new_songs)}] ✓ {label}  ->  "
                  f"{track['artists'][0]['name']} - {track['name']}")
        else:
            not_found.append((song["id"], label))
            print(f"[{n}/{len(new_songs)}] ✗ {label}")

    print(f"\nEşleşen: {len(found)}, bulunamayan: {len(not_found)}")
    if args.dry_run:
        print("--dry-run: Spotify'a bir şey eklenmedi.")
        return

    for song, _ in found:
        state["missing"].pop(song["id"], None)
    state["missing"].update(not_found)
    save_state(state)
    NOT_FOUND_FILE.write_text("\n".join(state["missing"].values()) + "\n", encoding="utf-8")

    if found:
        playlist_id = ensure_playlist(sp, state, os.getenv("PLAYLIST_NAME", "YouTube Music Beğenilenler"))
        already = set(state["synced"].values())
        uris = [u for u in dict.fromkeys(t["uri"] for _, t in found) if u not in already]
        add_tracks(sp, playlist_id, uris)
        for song, track in found:
            state["synced"][song["id"]] = track["uri"]
        save_state(state)
        print(f"{len(uris)} şarkı çalma listesine eklendi.")
    if not_found:
        print(f"Bulunamayanlar {NOT_FOUND_FILE.name} dosyasına yazıldı.")


if __name__ == "__main__":
    main()
