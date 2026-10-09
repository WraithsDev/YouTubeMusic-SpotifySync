# YouTube Music → Spotify Sync

YouTube Music'te beğenilen şarkıları Spotify'daki bir çalma listesine aktaran Python aracı.

Her çalıştırmada yalnızca yeni beğenileri işler. YouTube başlıklarını temizler, Spotify'da arar, sonuçları sanatçı, başlık ve süreye göre doğrular, eşleşenleri tek bir çalma listesine ekler.

## Özellikler

- **Artımlı aktarım:** Aktarılan şarkılar kaydedilir. Aynı şarkı iki kez eklenmez.
- **Başlık temizleme:** `(Official Video)`, `[HD]`, `| KANAL ADI` gibi ekleri kaldırır. `Sanatçı - Şarkı` biçimindeki başlıkları ayrıştırır.
- **Doğrulama:** Spotify sonuçlarını sanatçı ve başlık benzerliğine göre kontrol eder. Türkçe karakterleri ve aksanları sadeleştirerek karşılaştırır.
- **Sürüm filtresi:** YouTube'daki şarkı öyle değilse instrumental, sped up, slowed, nightcore ve karaoke sürümlerini eler.
- **Süreye göre seçim:** Birden fazla aday kalırsa süresi en yakın olanı seçer.
- **Raporlama:** Eşleşmeyen şarkıları ayrı bir dosyaya yazar.

## Gereksinimler

- Python 3.10 veya üzeri
- Spotify hesabı
- YouTube Music hesabı

## Kurulum

```bash
git clone https://github.com/WraithsDev/YouTubeMusic-SpotifySync.git
cd YouTubeMusic-SpotifySync
pip install -r requirements.txt
```

### 1. Spotify uygulaması

1. [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) üzerinden yeni bir uygulama oluşturun.
2. Redirect URI olarak `http://127.0.0.1:8888/callback` ekleyin ve API türü olarak Web API'yi seçin.
3. `.env.example` dosyasını `.env` adıyla kopyalayın ve uygulamanın Client ID ile Client Secret değerlerini girin.

```env
SPOTIPY_CLIENT_ID=
SPOTIPY_CLIENT_SECRET=
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
PLAYLIST_NAME=YouTube Music Beğenilenler
```

### 2. YouTube Music kimlik doğrulaması

YouTube Music'in herkese açık bir API'si yok. Bu araç [ytmusicapi](https://github.com/sigma67/ytmusicapi) üzerinden tarayıcı oturumu bilgilerini kullanır.

1. Tarayıcıda [music.youtube.com](https://music.youtube.com) adresinde oturum açın.
2. Geliştirici araçlarını açın (F12) ve Network sekmesine geçin.
3. Filtreye `browse` yazın, ardından kütüphane sayfasını açın.
4. Listelenen `browse` isteklerinden birini **Copy as cURL** ile kopyalayın.
5. Kopyaladığınız metni proje klasöründe `istek.txt` adlı bir dosyaya yapıştırın.
6. Aşağıdaki komutu çalıştırın:

```bash
python yt_giris.py
```

Komut `browser.json` dosyasını oluşturur ve `istek.txt` dosyasını siler.

### 3. Çalıştırma

```bash
python sync.py --dry-run --limit 20   # eşleşmeleri Spotify'a yazmadan kontrol et
python sync.py                        # tüm beğenileri aktar
```

İlk çalıştırmada Spotify yetkilendirmesi için tarayıcı açılır. Verilen yetki yerel olarak saklanır.

## Kullanım

| Seçenek | Açıklama |
|---|---|
| `--dry-run` | Eşleştirme yapar, Spotify'a yazmaz |
| `--limit N` | Yalnızca ilk N beğeniyi işler |
| `--retry` | Daha önce bulunamayan şarkıları yeniden arar |
| `--log` | Çıktıyı `sync.log` dosyasına yazar |

## Nasıl çalışır

1. **Beğenilerin alınması:** Beğenilen şarkılar `ytmusicapi` ile alınır ve en eskiden en yeniye sıralanır. `state.json` içinde kayıtlı olanlar atlanır.
2. **Başlık temizleme:** Video ekleri, kanal adları ve `- Topic` sonekleri başlıktan çıkarılır.
3. **Arama:** Her şarkı için şu sorgular sırayla denenir:
   - Alan filtreli sorgu: `track:<başlık> artist:<sanatçı>`
   - Serbest metin sorgusu
   - `Sanatçı - Şarkı` başlıklarında sanatçı ile şarkı adının yer değiştirildiği sorgu
   - `(feat. X)` gibi parantezli eklerin çıkarıldığı sorgu
4. **Doğrulama:** Her aday üç kontrolden geçer:
   - Sanatçı adı, YouTube'daki sanatçı bilgisiyle ya da başlıktaki bir adla eşleşmelidir.
   - Başlıklar arasında en az %75 benzerlik (`difflib.SequenceMatcher`) olmalıdır. Bu sağlanmazsa kısa başlık uzun başlığın içinde geçmelidir.
   - Aday, YouTube'daki şarkıda bulunmayan bir sürüm etiketi (instrumental, sped up vb.) taşımamalıdır.
5. **Seçim:** Kontrolleri geçen adaylar arasından süresi YouTube'dakine en yakın olan seçilir.
6. **Kayıt:** Eşleşen şarkılar 100'lük gruplar hâlinde gizli bir çalma listesine eklenir. Eşleşmeler `state.json` dosyasına, bulunamayanlar `bulunamayanlar.txt` dosyasına yazılır.

## Proje yapısı

```
YouTubeMusic-SpotifySync/
├── sync.py            Beğenileri alır, eşleştirir ve Spotify'a ekler
├── yt_giris.py        cURL çıktısından browser.json oluşturur
├── requirements.txt
└── .env.example
```

Çalışma sırasında oluşturulan dosyalar `.gitignore` kapsamındadır:

| Dosya | İçerik |
|---|---|
| `.env` | Spotify uygulama bilgileri |
| `browser.json` | YouTube Music oturum bilgileri |
| `.spotify_cache` | Spotify erişim token'ı |
| `state.json` | Aktarılan şarkılar ve çalma listesi kimliği |
| `bulunamayanlar.txt` | Eşleşmeyen şarkılar |
| `sync.log` | `--log` seçeneğiyle üretilen çıktı |

`.env`, `browser.json` ve `.spotify_cache` hesaplarınıza erişim sağlar. Bu dosyaları paylaşmayın ve depoya eklemeyin.

## Zamanlanmış çalıştırma

**Windows (Görev Zamanlayıcı)**, proje klasöründe çalıştırın:

```powershell
$action  = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "sync.py --log" -WorkingDirectory (Get-Location)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "YTMusic-Spotify Sync" -Action $action -Trigger $trigger
```

Görevi kaldırmak için:

```powershell
Unregister-ScheduledTask "YTMusic-Spotify Sync" -Confirm:$false
```

**Linux / macOS (cron):**

```
0 * * * * cd /path/to/YouTubeMusic-SpotifySync && python3 sync.py --log
```

## Sorun giderme

| Sorun | Çözüm |
|---|---|
| `browser.json bulunamadı` | YouTube Music kimlik doğrulaması adımını uygulayın. |
| YouTube kimlik doğrulama hatası | Oturum bilgilerinin süresi dolmuştur. 2. adımı tekrarlayın. |
| `INVALID_CLIENT: Invalid redirect URI` | Spotify panelindeki Redirect URI, `.env` dosyasındakiyle birebir aynı olmalıdır. |
| Yanlış eşleşme | Şarkıyı Spotify'da elle düzeltin. Kayıtlı olduğu için tekrar eklenmez. |

## Bağımlılıklar

- [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- [spotipy](https://github.com/spotipy-dev/spotipy)
- [python-dotenv](https://github.com/theskumar/python-dotenv)

## Lisans

MIT
