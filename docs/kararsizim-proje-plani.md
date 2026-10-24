# kararsızım — Proje Planı

> Bu dosya kararsızım projesi için alınan tüm kararları ve Claude Code'a verilecek uygulama planını bir arada tutar.
> **Claude Code ile kullanım:** Dosyayı repo'nun kök dizinine `CLAUDE.md` adıyla koy; Claude Code her oturumun başında otomatik okur. Fazları tek tek uygulat (bkz. Ek A).
> Proje fazlar halinde ilerler. **Sadece istenen fazı uygula, sonraki fazlara geçme.** Her faz sonunda kabul kriterlerini kontrol et, testleri çalıştır ve kısa bir özet vererek dur.

---

## 1. Proje Özeti

**kararsızım**, insanların kararsız kaldıkları konularda diğer kullanıcılara danışabildiği basit bir anket platformudur.

Örnek: *"Bugün sinemaya mı gitsem, restorana mı?"* → kullanıcı soruyu yazar, 2–5 seçenek ekler, diğer kullanıcılar oy verir.

### Temel kurallar
- Takip / arkadaşlık sistemi **yok**. Herkes platformdaki tüm anketleri görür.
- **Üye olmadan:** anketleri görüntüleme ve oy verme serbest.
- **Üye olmak zorunlu:** anket oluşturmak için.
- Kayıtta **e-posta, kullanıcı adı, parola** istenir.
- Anketlerde **kullanıcı adı görünür**, e-posta **hiçbir yerde görünmez** (şablonlar, JSON yanıtları, sayfa kaynağı dahil).
- Her anket **en az 2, en fazla 5** seçenek içerir.
- Hedef: **çalışan bir prototip.** Gereksiz karmaşıklıktan kaçın; basit, okunur, Django'nun yerleşik özelliklerini kullanan kod yaz.

---

## 2. Teknoloji Yığını

| Katman | Seçim | Not |
|---|---|---|
| Dil | Python 3.12 | Vercel Python runtime ile uyumlu sürüm |
| Backend | Django (güncel LTS / kararlı sürüm) | Şablon tabanlı (server-side rendering) |
| Veritabanı | Supabase (PostgreSQL) | **Yalnızca Postgres veritabanı olarak** kullanılır |
| Kimlik doğrulama | Django'nun yerleşik auth sistemi | Supabase Auth **kullanılmaz** |
| Frontend | Saf HTML + CSS + JavaScript | Framework yok, build adımı yok, aynı repo içinde |
| Deployment | Vercel | Django, `manage.py` üzerinden otomatik algılanır |

### Bağımlılıklar (minimum tut)
- `Django`
- `dj-database-url` — `DATABASE_URL` ortam değişkenini okumak için
- `psycopg2-binary` — PostgreSQL sürücüsü (Supabase transaction pooler ile sorunsuz çalışır)
- `python-dotenv` — yerel geliştirmede `.env` okumak için
- `whitenoise` — yalnızca Vercel'in statik dosya sunumu yetersiz kalırsa (Faz 4'te karar verilecek)

Yeni bir bağımlılık eklemeden önce gerçekten gerekli olup olmadığını sorgula; Django'nun kendi araçlarıyla çözülebiliyorsa onu kullan.

### Önemli mimari kararlar ve nedenleri
1. **Supabase Auth yerine Django auth:** İki ayrı kullanıcı sistemi yönetmek prototipi gereksiz karmaşıklaştırır. Django auth; parola hash'leme, oturum, CSRF ve admin paneliyle hazır gelir.
2. **Supabase JS istemcisi / anon key kullanılmaz:** Tarayıcı veritabanına doğrudan bağlanmaz; tüm veri erişimi Django üzerinden olur.
3. **Ayrı API + SPA yok:** Sayfalar Django şablonlarıyla üretilir. JavaScript yalnızca etkileşimi iyileştirmek için kullanılır (sayfa yenilemeden oy verme, seçenek ekleme/çıkarma). JS kapalıyken de temel akış çalışmalıdır (form POST + yönlendirme).


### Çatı seçimi: Neden Django, neden FastAPI değil?
Vercel'de Django yerine FastAPI kullanmak değerlendirildi ve **Django'da kalınmasına** karar verildi.

| Konu | Django | FastAPI |
|---|---|---|
| Kullanıcı / parola hash / oturum | ✓ Hazır | ✗ Elle kurulur (pwdlib, session veya JWT) |
| ORM + migrasyon | ✓ Hazır | ✗ SQLAlchemy + Alembic eklenir |
| HTML şablonları ve formlar | ✓ Hazır | ✗ Jinja2 eklenir, form doğrulaması elle yazılır |
| CSRF koruması | ✓ Hazır | ✗ Elle eklenir |
| Admin paneli (moderasyon) | ✓ Hazır | ✗ Yok |
| Vercel'de çalışma | ✓ Resmi destek, `manage.py` ile otomatik algılanır | ✓ Çalışır |
| Platform kaynaklı sorunlar (soğuk başlatma, bağlantı havuzu, statik dosyalar, kalıcı olmayan dosya sistemi) | Çatıdan bağımsız | Çatıdan bağımsız |
| Supabase transaction pooler (6543) uyumu | ✓ `psycopg2` ile sorunsuz | ✗ Yaygın async sürücü `asyncpg` prepared statement kullanır, ek ayar gerekir |
| Soğuk başlatma süresi | ⚠ Daha ağır, ilk istek biraz daha yavaş (prototipte önemsiz) | ✓ Daha hafif |
| Ayrı frontend (React / mobil) için JSON API | ✓ Django REST Framework veya Django Ninja ile eklenir | ✓ Doğal kullanım alanı |

**Gerekçe:** Uygulamanın ihtiyaç duyduğu parçalar (kayıt/giriş, oturum, formlar, CSRF, şablonlu HTML, migrasyonlar, admin) Django'da hazır geliyor; FastAPI'de her biri ayrıca seçilip bağlanmalı. Her ek parça hata çıkabilecek yeni bir yer demek ve "önce basit prototip" hedefine ters düşer.

**FastAPI ne zaman doğru olurdu?** Frontend tamamen ayrı yazılacaksa ve backend yalnızca JSON döndürecekse. O durumda bile Django REST Framework veya Django Ninja ile Django korunabilir.

**B planı:** Vercel'de Django ile ciddi sorun çıkarsa çatıyı değil barındırma platformunu değiştir (ör. Render, Railway). Kod neredeyse hiç değişmez.

---

## 3. Klasör Yapısı

```
kararsizim/
├── CLAUDE.md
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── config/                 # Django proje ayarları
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── accounts/               # Kullanıcı modeli, kayıt, giriş, çıkış
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   └── tests.py
├── polls/                  # Anket, seçenek, oy
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── voting.py           # Oy verme ve seçmen kimliği mantığı
│   └── tests.py
├── templates/
│   ├── base.html
│   ├── partials/           # navbar, poll_card, messages, pagination
│   ├── accounts/           # register.html, login.html
│   └── polls/              # feed.html, detail.html, create.html, user_polls.html
└── static/
    ├── css/main.css
    ├── js/main.js
    └── img/                # logo, favicon
```

---

## 4. Veri Modeli

### `accounts.User` (özel kullanıcı modeli — `AbstractUser`'dan türetilir)
> ⚠️ Özel kullanıcı modeli **ilk `migrate` komutundan önce** oluşturulmalı ve `AUTH_USER_MODEL = "accounts.User"` ayarlanmalı. Sonradan değiştirmek çok zahmetlidir.

| Alan | Kural |
|---|---|
| `email` | Zorunlu, benzersiz (büyük/küçük harf duyarsız), giriş için kullanılır |
| `username` | Zorunlu, benzersiz (büyük/küçük harf duyarsız), 3–20 karakter, yalnızca `a-z`, `0-9`, `_` ve `.`; kaydederken küçük harfe çevrilir |
| `password` | Django'nun varsayılan parola doğrulayıcıları |

- `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = ["username"]` → giriş e-posta + parola ile yapılır.
- Özel bir `UserManager` yaz (`create_user`, `create_superuser` e-postayla çalışmalı).
- Ayrılmış kullanıcı adları reddedilir: `admin`, `kararsizim`, `destek`, `yonetim`, `giris`, `kayit`, `cikis`, `anket`, `api`, `static`.

### `polls.Poll`
| Alan | Tip / Kural |
|---|---|
| `author` | FK → User, `on_delete=CASCADE` |
| `question` | CharField, 5–140 karakter, boşluklar temizlenir |
| `created_at` | DateTimeField, `auto_now_add`, indeksli |

- Varsayılan sıralama: `-created_at`.
- Anket oluşturulduktan sonra **düzenlenemez** (oy verildikten sonra seçeneklerin değişmesini engellemek için). Sahibi yalnızca silebilir.

### `polls.Option`
| Alan | Tip / Kural |
|---|---|
| `poll` | FK → Poll, `related_name="options"`, CASCADE |
| `text` | CharField, 1–60 karakter |
| `position` | PositiveSmallIntegerField (0–4), görüntüleme sırası ve renk ataması için |

- Aynı anket içinde seçenek metinleri benzersiz olmalı (büyük/küçük harf duyarsız kontrol formda yapılır).

### `polls.Vote`
| Alan | Tip / Kural |
|---|---|
| `poll` | FK → Poll, CASCADE |
| `option` | FK → Option, CASCADE |
| `user` | FK → User, `null=True`, `on_delete=SET_NULL` (üye olmayanlar için boş) |
| `voter_key` | CharField(64) — seçmeni tanımlayan anahtar |
| `created_at` | DateTimeField, `auto_now_add` |

- **Kısıt:** `UniqueConstraint(fields=["poll", "voter_key"])` → bir seçmen bir ankete yalnızca bir kez oy verir.
- `option.poll_id == poll_id` olduğu model/servis katmanında doğrulanır.

### Seçmen kimliği (`polls/voting.py`)
- **Üye kullanıcı:** `voter_key = f"u:{user.id}"`
- **Üye olmayan:** Tarayıcıya imzalı bir çerez (`kz_voter`) yerleştirilir; değeri rastgele bir UUID4'tür. `voter_key = f"a:{uuid}"`.
  - `set_signed_cookie` / `get_signed_cookie` kullan; `max_age` 1 yıl, `httponly=True`, `samesite="Lax"`, üretimde `secure=True`.
  - Çerez yoksa veya imza geçersizse yeni UUID üret.
- Oy kaydı `transaction.atomic()` içinde yapılır; `IntegrityError` yakalanırsa "zaten oy verdin" olarak ele alınır (aynı anda gelen çift tıklamalara karşı).

> **Bilinen sınırlama (prototip için kabul edildi):** Üye olmayanların oyu çereze bağlıdır; gizli sekme veya çerez silme ile tekrar oy verilebilir. Üye olmadan oy veren biri sonra giriş yaparsa aynı ankete bir kez daha oy verebilir. Bu, sonraki fazlarda IP tabanlı hız sınırı vb. ile sıkılaştırılacak (bkz. Bölüm 9).

---

## 5. Sayfalar ve URL'ler

Tüm URL'ler ve arayüz metinleri **Türkçe**dir.

| URL | Görünüm | Erişim | Açıklama |
|---|---|---|---|
| `/` | Ana akış | Herkes | En yeni anketler, sayfa başına 20, sayfalama |
| `/?sirala=populer` | Ana akış | Herkes | En çok oy alanlar (Faz 3) |
| `/anket/<id>/` | Anket detayı | Herkes | Soru, seçenekler, oy formu / sonuçlar |
| `/anket/<id>/oy/` | Oy ver (POST) | Herkes | JSON veya yönlendirme döner |
| `/anket/olustur/` | Anket oluştur | Giriş gerekli | Giriş yoksa `/giris/?next=...` adresine yönlendirir |
| `/anket/<id>/sil/` | Anket sil (POST) | Yalnızca sahibi | Onay sonrası silme |
| `/anket/<id>/kapat/` | Anket kapat (POST) | Yalnızca sahibi | Kapatınca oy verilemez, sonuçlar herkese açılır |
| `/?sirala=kapananlar` | Ana akış | Herkes | Kapanan anketler, en son kapanan üstte |
| `/u/<kullanici_adi>/` | Kullanıcının anketleri | Herkes | Yalnızca kullanıcı adı ve anketleri (Faz 3) |
| `/kayit/` | Kayıt | Misafir | E-posta, kullanıcı adı, parola, parola tekrar |
| `/giris/` | Giriş | Misafir | E-posta + parola |
| `/cikis/` | Çıkış (POST) | Üye | GET ile çıkış yapılmaz |
| `/yonetim/` | Django admin | Süper kullanıcı | Varsayılan `/admin/` yerine bu yol |

### Oy verme davranışı
- Kullanıcı **oy vermeden önce sonuçları görmez** (sonuçların kararı etkilememesi için). Anketin sahibi sonuçları her zaman görür.
- Oy verdikten sonra: seçenekler yüzdelik çubuklara dönüşür, kullanıcının seçtiği seçenek işaretlenir (✓), toplam oy sayısı gösterilir.
- Oy **değiştirilemez** (prototip kuralı).
- `POST /anket/<id>/oy/` yanıtları:
  - İstek `Accept: application/json` içeriyorsa JSON döner:
    - `200` → `{"ok": true, "results": [{"option_id", "text", "votes", "percent"}], "total": N, "voted_option_id": X}`
    - `409` → zaten oy verilmiş; yine de sonuçları aynı formatta döner
    - `400` → geçersiz seçenek
  - Aksi halde detay sayfasına yönlendirir ve Django `messages` ile bilgi verir.
- JSON yanıtlarında yazar için yalnızca `username` döner; **e-posta asla dönmez.**

### Anket oluşturma formu
- Soru alanı (karakter sayacı: `0/140`).
- Başlangıçta 2 seçenek alanı; "+ Seçenek ekle" ile 5'e kadar artar, her ekstra alanın yanında kaldırma butonu bulunur; 2'nin altına inilemez.
- Sunucu tarafı doğrulama JS'den bağımsız olarak her zaman yapılır: boş seçenekler atılır, kalan seçenek sayısı 2–5 aralığında olmalı, tekrar eden seçenekler reddedilir.
- Başarılı oluşturma sonrası anketin detay sayfasına yönlendir.

### Performans notu
- Akışta N+1 sorgu olmamalı: seçenekleri `prefetch_related`, oy sayılarını `annotate(Count(...))` ile al; mevcut seçmenin görüntülenen anketlerdeki oylarını **tek sorguda** çek.

---

## 6. Arayüz ve Tasarım Rehberi

**Hedef kitle:** Gençler. **His:** Açık arka planlı, temiz, canlı renklerle tonlanmış, eğlenceli ama dağınık değil.

### Renk paleti (CSS değişkenleri olarak `:root` içinde tanımla)
```css
:root {
  /* Zemin ve metin */
  --bg: #FAF7FF;            /* çok açık lavanta tonlu zemin */
  --surface: #FFFFFF;       /* kartlar */
  --text: #1F1B2D;          /* ana metin */
  --text-muted: #6B6680;    /* ikincil metin */
  --border: #ECE7F7;

  /* Marka */
  --primary: #7C5CFF;       /* elektrik moru */
  --primary-2: #FF4FA3;     /* pembe — gradyan için */
  --gradient: linear-gradient(135deg, var(--primary), var(--primary-2));

  /* Seçenek renkleri (position 0–4 sırasıyla) */
  --opt-1: #FF6B6B;         /* mercan */
  --opt-2: #7C5CFF;         /* mor */
  --opt-3: #14B8A6;         /* nane */
  --opt-4: #FFB020;         /* güneş */
  --opt-5: #FF4FA3;         /* pembe */

  /* Durum */
  --success: #16A34A;
  --danger: #E11D48;

  /* Biçim */
  --radius: 16px;
  --radius-lg: 24px;
  --shadow: 0 8px 24px rgba(124, 92, 255, 0.10);
}
```

### İlkeler
- **Tonlama:** Her seçenek kendi rengini alır. Oy öncesi buton zemini o rengin ~%12 opaklıktaki tonu, kenarlığı ~%40 tonu; sonuç çubuğu rengin kendisi. (`color-mix()` veya rgba kullan.)
- **Zemin:** Düz `--bg` üzerine, sayfanın köşelerinde çok soluk, bulanık renkli 2–3 daire (dekoratif, `position: fixed`, `pointer-events: none`).
- **Kartlar:** Beyaz, `--radius-lg`, ince kenarlık, yumuşak mor gölge, bol iç boşluk.
- **Birincil buton:** `--gradient` zeminli, beyaz yazı, tam yuvarlak köşeler; hover'da hafif yukarı kayma.
- **Tipografi:** Google Fonts'tan **Plus Jakarta Sans** (Türkçe karakter desteği var), 400/600/800 ağırlıkları. Sorular 600–700 ağırlıkta ve belirgin.
- **Kontrast:** Metin her zaman koyu (`--text`); canlı renkler zemin/vurgu olarak kullanılır, açık renk üstüne beyaz küçük metin konmaz.
- **Mobil öncelikli:** 360px genişlikte kusursuz çalışmalı; içerik genişliği masaüstünde en fazla ~680px, ortalanmış.
- **Mikro etkileşimler:** Oy sonrası sonuç çubukları 0'dan genişleyerek dolar (~600ms); kendi oyun ✓ ile vurgulanır. `prefers-reduced-motion` açıksa animasyonları kapat.
- Erişilebilirlik: tüm form alanlarında `<label>`, butonlarda görünür `:focus-visible` halkası, renk tek başına anlam taşımaz (yüzde ve ✓ metinle de belirtilir).

### Anket kartı anatomisi
```
┌────────────────────────────────────────┐
│ (A) @kullaniciadi · 2 saat önce         │  ← avatar: kullanıcı adının ilk harfi,
│                                        │    renk kullanıcı adından türetilir
│ Bugün sinemaya mı gitsem,              │
│ restorana mı?                          │  ← soru (büyük, kalın)
│                                        │
│ [ 🎬 Sinema                         ]  │  ← oy öncesi: tonlu buton
│ [ 🍝 Restoran                       ]  │
│                                        │
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░  Sinema   ✓  64%      │  ← oy sonrası: renkli çubuk
│ ▓▓▓▓▓▓░░░░░░░░░░  Restoran     36%     │
│                                        │
│ 25 oy                    Detay →       │
└────────────────────────────────────────┘
```

### Navbar
- Solda "kararsızım" logosu (yazı logosu, gradyan renkli, sonunda küçük bir "?" vurgusu).
- Sağda: misafirse "Giriş yap" ve "Kayıt ol"; üyeyse "+ Anket oluştur" (gradyan buton), `@kullaniciadi` ve "Çıkış".

### Boş durumlar ve mesajlar
- Hiç anket yoksa: dostane bir mesaj ve "İlk anketi sen oluştur" butonu.
- Django `messages` çıktıları sayfanın üstünde kısa süreli bildirimler olarak gösterilir.

---

## 7. Kodlama Kuralları

- Ayarlar ortam değişkenlerinden okunur; gizli bilgi **asla** koda veya git'e girmez. `.env` dosyası `.gitignore` içinde, `.env.example` repoda.
- `LANGUAGE_CODE = "tr"`, `TIME_ZONE = "Europe/Istanbul"`, `USE_TZ = True`. Zaman gösterimi için `django.contrib.humanize` (`naturaltime` → "2 saat önce").
- Tüm formlarda CSRF koruması; JS `fetch` isteklerinde CSRF token gönderilir.
- Durum değiştiren her işlem (oy, silme, çıkış) **POST** ile yapılır.
- Yetki kontrolleri sunucu tarafında: anket oluşturma `login_required`, silme yalnızca sahibine (`403` aksi halde).
- Kullanıcı girdileri şablonlarda otomatik kaçışlanır; `|safe` kullanılmaz.
- Görünümler kısa tutulur; oy mantığı `polls/voting.py` içinde, test edilebilir fonksiyonlarda.
- Kod ve değişken isimleri İngilizce, kullanıcıya görünen tüm metinler Türkçe.
- Her faz sonunda `python manage.py test` başarılı olmalı ve `python manage.py check` uyarı vermemeli.

### Ortam değişkenleri (`.env.example`)
```
DJANGO_SECRET_KEY=degistir-beni
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
# Boş bırakılırsa yerelde SQLite kullanılır
DATABASE_URL=
```

---

## 8. Fazlar

Her faz bağımsız bir Claude Code görevidir. Faz bittiğinde: kabul kriterlerini tek tek kontrol et, testleri çalıştır, yapılanları ve varsa açık kalan noktaları özetle, **sonraki faza geçmeden dur.**

### Faz 0 — Proje iskeleti
**Kapsam**
- Django projesi (`config`) ve `accounts`, `polls` uygulamaları.
- `requirements.txt`, `.gitignore`, `.env.example`, ayarların ortam değişkenlerinden okunması.
- `DATABASE_URL` yoksa SQLite'a düşen veritabanı ayarı (`dj-database-url`).
- **Özel `User` modeli ve `UserManager`** (Bölüm 4) — ilk migrate'ten önce.
- Türkçe dil/saat dilimi ayarları, `humanize`.
- `templates/base.html` (Google Fonts, `main.css`, `main.js`, navbar iskeleti, mesaj alanı), `static/css/main.css` içinde Bölüm 6'daki CSS değişkenleri ve temel sıfırlama.
- Admin yolu `/yonetim/`.

**Kabul kriterleri**
- `python manage.py migrate` ve `runserver` hatasız çalışır.
- `/` adresinde temel düzen ve renkli zemin görünür.
- `createsuperuser` e-posta + kullanıcı adı ile çalışır, `/yonetim/` girişi yapılabilir.

### Faz 1 — Üyelik
**Kapsam**
- Kayıt (`/kayit/`): e-posta, kullanıcı adı, parola, parola tekrar; Bölüm 4'teki doğrulamalar; Türkçe hata mesajları; başarılı kayıtta otomatik giriş ve ana sayfaya yönlendirme.
- Giriş (`/giris/`) e-posta + parola, `next` parametresi desteği; çıkış (`/cikis/`, POST).
- Navbar'ın giriş durumuna göre değişmesi.
- Giriş yapmış kullanıcının `/kayit/` ve `/giris/` sayfalarına girince ana sayfaya yönlendirilmesi.

**Kabul kriterleri**
- Aynı e-posta veya kullanıcı adıyla (farklı büyük/küçük harfle bile) ikinci kayıt reddedilir.
- Geçersiz kullanıcı adları (`ab`, `Ali Veli`, `admin`) reddedilir.
- Testler: başarılı kayıt, tekrar eden e-posta/kullanıcı adı, giriş/çıkış akışı.

### Faz 2 — Anket çekirdeği
**Kapsam**
- `Poll`, `Option`, `Vote` modelleri, kısıtlar ve admin kayıtları (admin'de anket listesinde soru, yazar, tarih, oy sayısı; seçenekler inline).
- Anket oluşturma (form + dinamik seçenek alanları için minimal JS; JS olmadan 5 alan gösterilip boşlar atılabilir).
- Ana akış (sayfalama ile), anket detayı, oy verme (`polls/voting.py`, imzalı çerez), sonuç gösterimi, sahibinin anketi silmesi.
- Bu fazda oy verme normal form POST + yönlendirme ile çalışsın; görsel cila Faz 3'te.

**Kabul kriterleri**
- Üye olmayan kullanıcı anket görüp oy verebilir; `/anket/olustur/` adresinde giriş sayfasına yönlendirilir.
- Aynı tarayıcıdan aynı ankete ikinci oy kaydedilmez.
- 1 veya 6 seçenekli anket, tekrar eden seçenekler ve başka ankete ait `option_id` reddedilir.
- Sayfa kaynağında ve JSON'da hiçbir kullanıcının e-postası yer almaz.
- Başkasının anketini silme denemesi `403` döner.
- Testler: yukarıdaki her madde için.

### Faz 3 — Arayüz cilası ve etkileşim
**Kapsam**
- Bölüm 6'daki tasarımın eksiksiz uygulanması (kart, seçenek renkleri, gradyan buton, dekoratif zemin, boş durumlar, bildirimler).
- `main.js`: sayfa yenilemeden oy verme (`fetch` + JSON yanıt), sonuç çubuklarının animasyonla dolması, hata durumunda kullanıcıya mesaj; JS kapalıyken Faz 2'deki form akışı çalışmaya devam eder.
- Anket oluşturma formunda karakter sayacı ve seçenek ekle/kaldır etkileşimi.
- "Yeni / Popüler" sekmeleri (`?sirala=populer` → oy sayısına göre).
- `/u/<kullanici_adi>/` kullanıcı anketleri sayfası; kartlardaki kullanıcı adları bu sayfaya bağlanır.
- Avatar rengi kullanıcı adından deterministik olarak türetilir.
- Silme işlemi için onay (JS `confirm` yeterli).

**Kabul kriterleri**
- 360px, 768px ve 1280px genişliklerde düzen bozulmaz, yatay kaydırma oluşmaz.
- Oy verildiğinde sayfa yenilenmez, sonuçlar animasyonla gelir; ağ hatasında anlaşılır mesaj görünür.
- Klavye ile tüm akış (oy verme, anket oluşturma) kullanılabilir.

### Faz 4 — Supabase bağlantısı ve Vercel'e yayın
**Kapsam**
1. **Supabase**
   - Proje bölgesi olarak İstanbul'a yakın bir AB bölgesi seç (ör. Frankfurt / `eu-central-1`).
   - Uygulama (Vercel) için **Transaction pooler** bağlantı dizesi kullanılır (port `6543`); sunucusuz ortam için önerilen mod budur.
   - Django ayarları (Postgres kullanılırken): `CONN_MAX_AGE = 0`, `DISABLE_SERVER_SIDE_CURSORS = True` (transaction pooling ile uyum için), `sslmode=require`.
   - Migrasyonlar **yerelden** çalıştırılır: `.env` içinde Supabase bağlantı dizesiyle `python manage.py migrate`. Vercel build adımında migrate **çalıştırılmaz**.
   - Süper kullanıcı yerelden Supabase'e karşı `createsuperuser` ile oluşturulur.
   - 🔒 **Güvenlik:** Django tabloları `public` şemasında oluşacak. Supabase'in Data API'si bu şemayı anon key üzerinden dışarı açabilir. Bu projede Data API kullanılmadığı için: Supabase panelinde Data API erişimini kapat **veya** tüm tablolarda RLS'yi (politikasız) etkinleştir. Ardından Supabase Security Advisor'da "RLS disabled" uyarısı kalmadığını doğrula. Django `postgres` rolüyle bağlandığı için bu, uygulamayı etkilemez.
2. **Vercel**
   - Güncel resmi rehbere göre yapılandır: https://vercel.com/docs/frameworks/full-stack/django (Vercel, Django'yu `manage.py` üzerinden algılar).
   - Statik dosyalar: `STATIC_ROOT` ayarla; Vercel'in statik dosya algılaması yeterli değilse `whitenoise` ekle.
   - Ortam değişkenleri Vercel panelinden: `DJANGO_SECRET_KEY` (yeni, güçlü), `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` (`.vercel.app` alan adı), `DJANGO_CSRF_TRUSTED_ORIGINS` (`https://<proje>.vercel.app`), `DATABASE_URL` (transaction pooler).
   - Fonksiyon bölgesini Supabase'e yakın seç (ör. Frankfurt `fra1`).
   - Üretim güvenlik ayarları: `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`.
3. Kısa bir `README.md`: yerel kurulum, ortam değişkenleri, migrate ve deploy adımları.

**Kabul kriterleri**
- Canlı adreste kayıt, giriş, anket oluşturma, oy verme ve silme çalışır.
- `DEBUG=False` iken statik dosyalar (CSS/JS/font) yüklenir, 404/500 sayfaları sade ve markaya uygun.
- `python manage.py check --deploy` kritik uyarı vermez.
- Supabase Security Advisor'da RLS / açık tablo uyarısı yoktur.

---

## 9. Prototip Sonrası (şimdilik YAPMA)

Aşağıdakiler bilerek kapsam dışıdır; ileride ayrı fazlar olarak eklenecek:
- Hız sınırlama (IP hash'i ile oy ve anket oluşturma sınırları) ve bot koruması (ör. Cloudflare Turnstile)
- Anket bitiş süresi / anketi kapatma
- Uygunsuz içerik bildirme ve basit moderasyon (küfür filtresi)
- Paylaşım bağlantısı ve sosyal medya önizleme görseli (Open Graph)
- Kategoriler / etiketler, arama
- Profil düzenleme, parola sıfırlama (e-posta gönderimi gerektirir)
- Oy değiştirme, yorumlar
- Karanlık mod
- Üye olmadan verilen oyun girişten sonra hesaba bağlanması

---

## Ek A — Claude Code'da Faz Faz Kullanım

1. Boş bir klasör aç, bu dosyayı kök dizine `CLAUDE.md` adıyla koy, `git init` yap.
2. Claude Code'a her faz için şu kalıpla yaz:

   > CLAUDE.md'yi oku ve yalnızca **Faz 0**'ı uygula. Bitince kabul kriterlerini kontrol et, testleri çalıştır, özet ver ve dur.

3. Faz bitince uygulamayı tarayıcıda kendin de dene, sorun yoksa commit at.
4. Sonraki faza geç: Faz 0 → Faz 1 → Faz 2 → Faz 3 → Faz 4.
5. Büyük fazlardan (özellikle Faz 2 ve Faz 4) önce Claude Code'da plan modunu kullanıp önce planı onaylamak, yanlış yöne gitmeyi erken yakalar.

---

## Ek B — Karar Kaydı

| # | Karar | Neden |
|---|---|---|
| 1 | Backend: Django (FastAPI değil) | Auth, formlar, CSRF, ORM, admin hazır; prototip için en az parça |
| 2 | Supabase yalnızca Postgres veritabanı | İki ayrı kullanıcı sistemiyle uğraşmamak |
| 3 | Kimlik doğrulama: Django auth, e-posta ile giriş | Hazır ve güvenli; kullanıcı adı ayrıca seçilir ve görünür |
| 4 | Supabase anon key / JS istemcisi yok | Tüm veri erişimi Django üzerinden; tarayıcı veritabanına bağlanmaz |
| 5 | Data API kapalı veya tüm tablolarda RLS açık | Django tabloları (parola hash'leri dahil) `public` şemasından dışarı sızmasın |
| 6 | Vercel → Supabase bağlantısı transaction pooler (6543) | Sunucusuz ortam için önerilen mod |
| 7 | Migrasyonlar yerelden çalıştırılır | Deploy sırasında veritabanını değiştirme riskini önlemek |
| 8 | Bölge: Frankfurt (Supabase `eu-central-1`, Vercel `fra1`) | İstanbul'a yakın, düşük gecikme |
| 9 | Üye olmayanların tekrar oyu imzalı çerezle engellenir | Prototip için yeterli; gizli sekmeyle aşılabilir (bilinen sınırlama) |
| 10 | Oy vermeden sonuç görünmez, oy değiştirilemez | Çoğunluğa bakarak oy verilmesin |
| 11 | Anket oluşturulduktan sonra düzenlenemez | Oy verildikten sonra seçenekler değiştirilemesin |
| 12 | Frontend: saf HTML/CSS/JS, JS'siz de çalışır | Build adımı yok, basit ve sağlam |
| 13 | Akış ve kullanıcı sayfası: geniş ekranda iki sütun, kompakt kartlar; parçalı renkli dağılım çubuğu ve durum etiketi ("Karar net", "Az farkla önde", "Kalabalık da kararsız", "Kafa kafaya", "İlk oyu sen ver") | Referans tasarıma yakın, kartlar bir bakışta okunur; palet ve yazı tipi bizim |
| 14 | Dağılım çubuğu ve etiketler oy vermeden görünmez (gri çubuk + "N kişi oy verdi") | Karar #10 korunur |
| 15 | Anket sahibi anketi elle kapatabilir (`POST /anket/<id>/kapat/`); kapalı ankete oy verilmez, sonuçlar herkese açılır; "Kapalı" etiketi ve "Kapananlar" sekmesi eklendi. Süreli kapanma eklenmedi | Oy kararını etkileme riski kapanışla biter; süreli kapanma Bölüm 9'daki sonraki işler arasında kalır |
| 16 | Anket sahibi kendi anketine oy verebilir; oy verene kadar sonuçları ve oy butonlarını birlikte görür | Sahibin oyu da sayılır; sahip sonuçları önceden bildiği için oyu çoğunluğa bakılarak verilmiş olabilir, bu bilinçli kabul edildi |

---

## Kaynaklar
- [Vercel — Deploy a Django app](https://vercel.com/docs/frameworks/full-stack/django)
- [Supabase — Connecting to your database](https://supabase.com/docs/guides/database/connecting-to-postgres)
