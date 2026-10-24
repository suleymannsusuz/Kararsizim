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

### Notlar
- Ücretsiz planda proje bir süre kullanılmazsa duraklatılabilir; ilk istek veritabanı uyanana kadar yavaş olabilir veya hata verebilir (panelden *Restore* edilir).
- Transaction pooler IPv4 üzerinden çalışır. Doğrudan bağlantı (`db.<ref>.supabase.co:5432`) IPv6 gerektirebilir; kullanma.

## Yayın (Vercel)

Sonraki aşamada eklenecek.
