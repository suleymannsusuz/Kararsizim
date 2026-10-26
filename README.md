# kararsızım

İnsanların kararsız kaldıkları konularda diğer kullanıcılara danıştığı basit bir anket platformu.
Django (şablon tabanlı), saf HTML/CSS/JS, veritabanı olarak Supabase Postgres. Ayrıntılı plan: [docs/kararsizim-proje-plani.md](docs/kararsizim-proje-plani.md).

## Yerel kurulum

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver
```

`.env` içindeki `DATABASE_URL` boşsa yerelde SQLite (`db.sqlite3`) kullanılır. Yönetim paneli: `/yonetim/`.

### Ortam değişkenleri

| Değişken | Açıklama |
|---|---|
| `DJANGO_SECRET_KEY` | Zorunlu (`DJANGO_DEBUG=True` iken boş bırakılabilir) |
| `DJANGO_DEBUG` | `True` / `False` (varsayılan `False`) |
| `DJANGO_ALLOWED_HOSTS` | Virgülle ayrılmış alan adları |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Virgülle ayrılmış kaynaklar (ör. `https://alanadi.com`) |
| `DATABASE_URL` | Boşsa SQLite; doluysa Postgres (Supabase) |
| `DATABASE_SSL_REQUIRE` | Postgres için SSL zorunlu mu (varsayılan `True`; yerel Postgres için `False`) |

### Testler

```
.venv\Scripts\python.exe manage.py test
```

Testler `DATABASE_URL` dolu olsa bile **her zaman geçici SQLite** üzerinde çalışır; Supabase'e bağlanmaz.

## Supabase bağlantısı

Supabase yalnızca **Postgres veritabanı** olarak kullanılır. Supabase Auth, anon key ve JS istemcisi kullanılmaz; tüm veri erişimi Django üzerindendir.

### 1. Proje oluşturma
1. [supabase.com](https://supabase.com) üzerinde yeni proje oluştur. Bölge: **Frankfurt (eu-central-1)**.
2. Veritabanı parolasını güçlü seç ve bir yere kaydet (sonradan görüntülenemez, yalnızca sıfırlanabilir).

### 2. Bağlantı dizesi
1. Projede **Connect** düğmesine bas → **Transaction pooler** (port `6543`) dizesini kopyala.
2. `.env` dosyasındaki `DATABASE_URL` alanına yapıştır, `[YOUR-PASSWORD]` yerine parolanı yaz.
   Parolada `@ : / # ? %` gibi özel karakterler varsa [URL-kodlaması](https://developer.mozilla.org/en-US/docs/Glossary/Percent-encoding) gerekir (ör. `@` → `%40`).
3. `.env` dosyası `.gitignore` içindedir; **hiçbir zaman commit'leme**.

Postgres kullanılırken `config/settings.py` otomatik olarak `CONN_MAX_AGE=0`, `DISABLE_SERVER_SIDE_CURSORS=True` ve `sslmode=require` ayarlarını uygular (transaction pooling ile uyum için).

### 3. Migrasyon ve süper kullanıcı (yerelden)
```
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
```
Migrasyonlar her zaman yerelden çalıştırılır; yayın (build) adımında migrate çalıştırılmaz.

### 4. Güvenlik: Data API ve RLS
Django tabloları `public` şemasında oluşur. Supabase'in otomatik Data API'si bu şemayı anon key ile dışarı açabilir; bu projede Data API kullanılmadığı için iki önlemi birlikte uygula:

1. **Data API'yi kapat:** Supabase paneli → *Project Settings → Data API* (veya *API*) → Data API'yi devre dışı bırak.
2. **Tüm tablolarda RLS'yi (politikasız) aç:** *SQL Editor*'de çalıştır:

```sql
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END $$;
```

Django, tabloların sahibi olan `postgres` rolüyle bağlandığı için RLS uygulamayı etkilemez. **Yeni bir migrasyon yeni tablo oluşturursa SQL'i tekrar çalıştır.** Ardından *Advisors → Security Advisor* sayfasında "RLS disabled" uyarısı kalmadığını doğrula.

### Hız sınırı tablosu
`throttle_ratelimithit` tablosu IP'nin tuzlu özetini ve zaman damgasını tutar (ham IP saklanmaz). Eski kayıtlar kendiliğinden silinir. Tablo bir migrasyonla gelir; Supabase'e `migrate` çalıştırıp yukarıdaki RLS adımını tekrarlamak yeterli.

### Notlar
- Ücretsiz planda proje bir süre kullanılmazsa duraklatılabilir; ilk istek veritabanı uyanana kadar yavaş olabilir veya hata verebilir (panelden *Restore* edilir).
- Transaction pooler IPv4 üzerinden çalışır. Doğrudan bağlantı (`db.<ref>.supabase.co:5432`) IPv6 gerektirebilir; kullanma.

## Yayın (Vercel)

Vercel, projeyi `manage.py` üzerinden Django olarak tanır ve `config.wsgi.application` giriş noktasını `WSGI_APPLICATION` ayarından okur. Ek bir yapılandırma dosyası gerekmez; depodaki iki küçük dosya yeterlidir:

- `.python-version`: Python sürümü (3.13).
- `vercel.json`: fonksiyon bölgesi `fra1` (Frankfurt, Supabase'e yakın).

### Statik dosyalar
`STATIC_ROOT` tanımlı olduğu için Vercel, yayın sırasında `collectstatic`'i kendisi çalıştırır ve dosyaları CDN'den sunar. WhiteNoise gerekmez. `staticfiles/` klasörü `.gitignore`'dadır, depoya girmez.

### Kurulum adımları
1. Vercel panelinde **Add New → Project** ile GitHub deposunu içe aktar (Vercel'e GitHub erişimi vermen gerekir). Framework **Django** olarak algılanır; build ve çıktı ayarlarına dokunma.
2. **Settings → Environment Variables** bölümünde şunları **Production** (ve istersen Preview) için ekle:

| Değişken | Değer |
|---|---|
| `DJANGO_SECRET_KEY` | Yeni ve uzun rastgele bir anahtar (**Sensitive** işaretle). Üretmek için: `python -c "import secrets; print(secrets.token_urlsafe(60))"` |
| `DJANGO_DEBUG` | `False` |
| `DATABASE_URL` | Supabase **Transaction pooler** bağlantı dizesi (**Sensitive** işaretle) |

3. Deploy et. Sonraki her `git push` otomatik yayınlanır.

Alan adı için `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` gerekmez: Vercel'in `VERCEL_PROJECT_PRODUCTION_URL`, `VERCEL_URL` ve `VERCEL_BRANCH_URL` sistem değişkenleri otomatik kullanılır. Özel alan adı eklersen bu iki değişkene de yaz (virgülle ayrılmış; CSRF için `https://` ile).

Vercel'de `SECURE_SSL_REDIRECT`, güvenli çerezler, HSTS (1 yıl) ve `X-Forwarded-Proto` ayarı otomatik açılır. Başka bir barındırmada `DJANGO_SECURE=True` ile aynısını aç. Yerelde `DEBUG=False` ile denerken bunlar kapalıdır, böylece `http://localhost` çalışır.

### Yayından önce ve sonra
- Migrasyonlar yayın sırasında **çalışmaz**; yeni bir migrasyon eklediğinde yerelden `migrate` çalıştır (Supabase'e) ve yeni tablo oluşuyorsa RLS adımını tekrarla.
- Yayın ortamını yerelde taklit etmek için: `VERCEL=1`, `DJANGO_DEBUG=False`, uzun bir `DJANGO_SECRET_KEY` ve `VERCEL_PROJECT_PRODUCTION_URL` ile `python manage.py check --deploy` çalıştır. Kalan iki uyarı (HSTS alt alan adları ve preload) `vercel.app` ortak alan adı olduğu için bilerek açık bırakılmıştır.
- 500 sayfası bağımsız bir şablondur ve CSS'ini `/static/` yolundan alır; statik dosya sunumu çalışmazsa stilsiz görünür.
