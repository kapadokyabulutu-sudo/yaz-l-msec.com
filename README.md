# YazilimSec Yerel SQLite Sunucusu

Bu klasör, YazılımSeç sitesini yerel bilgisayarda **SQLite veritabanı** ile çalıştırır.
Ek ücretli hizmet, bulut aboneliği veya harici API kullanılmaz. Tek gereksinim Python 3'tür.

## Başlatma

1. `start-server.bat` dosyasına çift tıkla.
2. Tarayıcıda şu adresi aç:

   http://127.0.0.1:3000/

3. Site ilk açılışta mevcut yazılım/kategori verilerini otomatik olarak SQLite veritabanına aktarır.
4. Admin panelinden yapılan kayıtlar artık `data/yazilimsec.db` dosyasına yazılır.

Sunucuyu durdurmak için komut penceresinde `Ctrl+C` kullanabilirsin.

## Dosyalar

| Dosya | Açıklama |
|---|---|
| `server.py` | Yerel HTTP sunucusu ve SQLite API |
| `schema.sql` | Veritabanı şeması (inceleme/referans) |
| `start-server.bat` | Sunucuyu başlatır |
| `db-yedekle.bat` | Veritabanının tarihli yedeğini alır |
| `db-yedek-goruntule.bat` | Alınan yedeklerin içeriğini gösterir |
| `db_yedek_goruntule.py` | Yedek görüntüleme yardımcı betiği |
| `db-kontrol.bat` | Kayıt sayılarını, son kayıt zamanını ve son işlemleri gösterir |
| `admin_sifre.py` | Admin şifresini belirler veya güçlü yeni şifre üretir |
| `admin-sifre-degistir.bat` | Admin şifresini kolayca değiştirir |
| `data/yazilimsec.db` | SQLite veritabanı (ilk çalıştırmada oluşur) |

## İşlem Geçmişi

Admin panelindeki **İşlem Geçmişi** sayfasında yazılım, kategori, fiyat ve yorumlarda yapılan değişiklikler tarih-saat ve ayrıntılarıyla görünür.

- Son 500 işlem veritabanında saklanır.
- Sayfada en yeni 200 işlem listelenir.
- Kayıtlar `activity_log` tablosuna yazılır.
- `db-kontrol.bat` dosyası son kayıt zamanını ve son 5 işlemi komut penceresinde gösterir.
- İşlem geçmişi yalnızca veritabanı modunda tutulur; HTML dosyası tek başına açıldığında geçmiş gösterilmez.

## Admin Girişi ve Gizli Rota

Admin paneli kullanıcı arayüzünde görünmez ve sunucu tarafında korunur.

Giriş adresi **gizli ve rastgele** bir yoldur. Bu kurulumda giriş adresi, kullanıcı adı ve şifre size ayrıca bildirilir; ayrıca `ADMIN-SIFRE.txt` dosyasında yazar.

- İlk çalıştırmada **rastgele güçlü kullanıcı adı** ve **28 karakterlik güçlü şifre** üretilir.
- Bilgiler komut penceresinde ve `ADMIN-ILK-SIFRE.txt` dosyasında bir kez gösterilir.
- Giriş başarılı olursa **HttpOnly + SameSite=Strict** oturum çerezi oluşturulur.
- Oturum süresi 12 saattir. Sunucu yeniden başlarsa oturumlar geçersiz olur.
- Şifre yanlış girilirse 5 hatalı denemeden sonra 10 dakika kilit uygulanır.

Gizli kısayollar yalnızca **giriş yapmış oturumda** admin panelini açar:

- **Ctrl+Shift+A**
- `http://127.0.0.1:3000/#admin`
- `http://127.0.0.1:3000/?admin=1`

> Oturum yoksa bu kısayollar giriş adresini açığa çıkarmaz; yalnızca yetkili giriş gerektiğini bildirir. Giriş için doğrudan gizli adresi açın.

Admin sayfasındaki **Güvenli Çıkış** butonu oturumu kapatır.

### Giriş Bilgilerini Değiştirme

```text
admin-sifre-degistir.bat
```

Çalıştırınca 28 karakterlik güçlü bir şifre üretir, veritabanındaki eski hash'i değiştirir ve tüm eski oturumları kapatır. Kullanıcı adı verilmezse **mevcut kullanıcı adı korunur**. Yeni şifre ekranda ve `ADMIN-SIFRE.txt` dosyasında gösterilir.

Belirli bir şifre veya kullanıcı adı vermek için:

```bat
python admin_sifre.py --password "YeniGucluSifre!2026"
python admin_sifre.py --username yz_yeni_kullanici
```

### Güvenlik Notları

- Şifre veritabanında **scrypt + rastgele salt** ile hash'lenmiş olarak tutulur; düz metin saklanmaz.
- Oturum belirteçleri veritabanında yalnızca SHA-256 özetiyle tutulur.
- `PUT /api/state`, `POST /api/state`, `POST /api/seed` ve `GET /api/activity` oturum gerektirir.
- `GET /api/state` herkese açıktır ancak **bekleyen yorumlar** yalnızca giriş yapmış yöneticiye döner.
- Gizli giriş adresi public HTML kaynağına yazılmaz; yalnızca yetkili oturumda istemciye verilir. Eski `/admin` yolu **404** döner.
- Tek dosya (HTML) modunda admin paneli kapalıdır; admin yalnızca yerel sunucu üzerinden açılabilir.

## Veritabanı Yedeği

`db-yedekle.bat` dosyasına çift tıkla. Yedek şu klasöre yazılır:

```
data/yazilimsec-YYYYMMDD-HHMMSS.db
```

Ayrıca `data/yazilimsec.db` dosyasını doğrudan kopyalayarak da yedek alabilirsin.

### Yedeğin İçeriğine Bakma

`db-yedek-goruntule.bat` dosyasına çift tıkla. Program önce mevcut yedekleri listeler, sonra:

- Hiç seçim yapmadan **Enter**'a basarsan **en yeni yedeği** açar.
- Listeden bir **numara** yazıp Enter'a basarsan o yedeği açar (ör. `1`, `2`).
- **Dosya adının bir kısmını** yazıp Enter'a basarsan eşleşen yedeği açar (ör. `20261019`).

Program yedekte şunları gösterir:

- Tablo kayıt sayıları (yazılım, kategori, yorumlar, işlem geçmişi)
- Son kayıt zamanı
- Yazılım listesi ve fiyatları
- Kategoriler
- Son 10 işlem geçmişi kaydı

Komut satırından belirli bir yedeği doğrudan da açabilirsin:

```bat
db-yedek-goruntule.bat 1
db-yedek-goruntule.bat yazilimsec-20261019-185016.db
```

Yedekler `data/yazilimsec-YYYYMMDD-HHMMSS.db` biçimindedir. İstersen bu `.db` dosyalarını ücretsiz **DB Browser for SQLite** programıyla da açıp tabloları tek tek inceleyebilirsin.

## Port Değiştirme

Varsayılan port 3000'dir. Başka bir port kullanmak için:

```bat
start-server.bat --port 3001
```

Sonra `http://127.0.0.1:3001/` adresini aç.

## Nasıl Çalışır?

- Site sunucu üzerinden açıldığında `/api/state` adresinden SQLite verisini okur.
- Kaydet işlemleri `/api/state` adresine `PUT` isteği ile yazılır; bu istek admin oturumu gerektirir.
- Sunucu modunda SQLite verisi önceliklidir; tarayıcıdaki eski localStorage kaydı yok sayılır.
- Site doğrudan HTML dosyası olarak açılırsa eski tek dosya / localStorage modu çalışmaya devam eder; ancak admin paneli açılmaz.
- API yalnızca `127.0.0.1` üzerinde dinlenir; internete açık değildir.

## Notlar

- Bu sunucu yerel kullanım için tasarlandı. Admin girişi vardır; yine de internete açmadan önce HTTPS ve ek sunucu güvenliği gerekir.
- `ADMIN-ILK-SIFRE.txt` ve `ADMIN-SIFRE.txt` dosyaları düz metin şifre içerir. Şifreyi ezberledikten sonra bu dosyaları sil.
- HTML dosyasını tek başına paylaştığında, veritabanındaki son değişiklikler dosyada bulunmaz.
  Tek dosya paylaşımı için verilerin HTML dosyasına ayrıca aktarılması gerekir.
