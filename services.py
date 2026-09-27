"""
Servis katmanı — iş kuralları ve doğrulama burada yaşar.
Veritabanı katmanını sarmalayarak uygulama mantığını yönetir.
"""

import io
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

import database as db
from models import Kategori, Urun

# Dönüş tipi: (başarılı mı, mesaj)
Sonuc = tuple[bool, str]


class StokServisi:
    """Tüm stok yönetimi iş kurallarını içeren servis sınıfı."""

    # ── Kategori İşlemleri ────────────────────────────────────────────────────

    def kategori_ekle(self, ad: str, aciklama: str = "") -> Sonuc:
        ad = ad.strip()
        if not ad:
            return False, "Kategori adı boş olamaz."
        try:
            k = Kategori(ad=ad, aciklama=aciklama)
            db.kategori_ekle(k)
            return True, f"'{ad}' kategorisi başarıyla eklendi."
        except Exception as e:
            if "UNIQUE" in str(e):
                return False, f"'{ad}' adında bir kategori zaten mevcut."
            return False, f"Kategori eklenemedi: {e}"

    def kategori_sil(self, kategori_id: int) -> Sonuc:
        # Kategoriye bağlı ürün varsa silme
        urunler = db.urunleri_getir(kategori_id=kategori_id)
        if urunler:
            return False, f"Bu kategoriye bağlı {len(urunler)} ürün var. Önce ürünleri silin veya taşıyın."
        try:
            db.kategori_sil(kategori_id)
            return True, "Kategori silindi."
        except Exception as e:
            return False, f"Kategori silinemedi: {e}"

    def kategorileri_getir(self) -> list[dict]:
        return db.kategorileri_getir()

    # ── Ürün İşlemleri ────────────────────────────────────────────────────────

    def urun_ekle(
        self,
        ad: str,
        fiyat: float,
        stok_miktari: int,
        kritik_esik: int,
        kategori_id: Optional[int] = None,
    ) -> Sonuc:
        if db.urun_adi_var_mi(ad):
            return False, f"'{ad}' adında bir ürün zaten mevcut."
        try:
            u = Urun(
                ad=ad,
                fiyat=fiyat,
                stok_miktari=stok_miktari,
                kritik_esik=kritik_esik,
                kategori_id=kategori_id,
            )
            db.urun_ekle(u)
            return True, f"'{ad}' ürünü başarıyla eklendi."
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Ürün eklenemedi: {e}"

    def urun_guncelle(
        self,
        urun_id: int,
        ad: str,
        fiyat: float,
        stok_miktari: int,
        kritik_esik: int,
        kategori_id: Optional[int] = None,
    ) -> Sonuc:
        try:
            u = Urun(
                id=urun_id,
                ad=ad,
                fiyat=fiyat,
                stok_miktari=stok_miktari,
                kritik_esik=kritik_esik,
                kategori_id=kategori_id,
            )
            db.urun_guncelle(u)
            return True, f"'{ad}' ürünü güncellendi."
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Ürün güncellenemedi: {e}"

    def urun_sil(self, urun_id: int) -> Sonuc:
        urun = db.urun_getir(urun_id)
        if not urun:
            return False, "Ürün bulunamadı."
        hareket_sayisi = db.urun_hareket_sayisi(urun_id)
        try:
            db.urun_sil(urun_id)
            mesaj = f"'{urun['ad']}' silindi."
            if hareket_sayisi > 0:
                mesaj += f" ({hareket_sayisi} hareket kaydı da silindi.)"
            return True, mesaj
        except Exception as e:
            return False, f"Ürün silinemedi: {e}"

    def urunleri_getir(self, kategori_id: Optional[int] = None) -> list[dict]:
        return db.urunleri_getir(kategori_id)

    # ── Stok Hareketleri ─────────────────────────────────────────────────────

    def stok_girisi_yap(self, urun_id: int, miktar: int, aciklama: str = "") -> Sonuc:
        if miktar <= 0:
            return False, "Giriş miktarı sıfırdan büyük olmalıdır."
        try:
            sonuc = db.stok_hareketi_uygula(urun_id, "giriş", miktar, aciklama)
        except LookupError:
            return False, "Ürün bulunamadı."
        except Exception as e:
            return False, f"Stok girişi yapılamadı: {e}"
        return True, f"✅ {miktar} adet giriş yapıldı. Yeni stok: {sonuc['yeni_stok']}"

    def stok_cikisi_yap(self, urun_id: int, miktar: int, aciklama: str = "") -> Sonuc:
        if miktar <= 0:
            return False, "Çıkış miktarı sıfırdan büyük olmalıdır."
        try:
            sonuc = db.stok_hareketi_uygula(urun_id, "çıkış", miktar, aciklama)
        except LookupError:
            return False, "Ürün bulunamadı."
        except db.YetersizStokHatasi as e:
            return (
                False,
                f"Yetersiz stok! Mevcut: {e.mevcut} adet, talep edilen: {e.talep} adet.",
            )
        except Exception as e:
            return False, f"Stok çıkışı yapılamadı: {e}"
        yeni_stok = sonuc["yeni_stok"]
        uyari = " ⚠️ Kritik stok seviyesine ulaşıldı!" if yeni_stok <= sonuc["kritik_esik"] else ""
        return True, f"✅ {miktar} adet çıkış yapıldı. Yeni stok: {yeni_stok}{uyari}"

    # ── Raporlama ─────────────────────────────────────────────────────────────

    def kritik_stok_kontrol(self) -> list[dict]:
        """Stok miktarı kritik eşiğin altındaki ürünleri döner."""
        urunler = db.urunleri_getir()
        return [u for u in urunler if u["stok_miktari"] <= u["kritik_esik"]]

    def hareket_gecmisi(
        self,
        urun_id: Optional[int] = None,
        baslangic: Optional[str] = None,
        bitis: Optional[str] = None,
        tur: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        return db.hareketleri_getir(
            urun_id=urun_id, baslangic=baslangic, bitis=bitis, tur=tur, limit=limit
        )

    def son_hareketler(self, n: int = 15) -> list[dict]:
        return db.son_hareketleri_getir(n)

    def dashboard_verileri(self) -> dict:
        return db.dashboard_verisi_getir()

    def dashboard_analiz_yorumu(self, veri: dict) -> list[tuple[str, str]]:
        """Dashboard için kısa, kullanıcı dostu analiz yorumları üretir."""
        yorumlar: list[tuple[str, str]] = []  # (ikon, metin)

        # Kritik stok durumu
        if veri["stok_biten"] > 0:
            yorumlar.append(("🚨", f"{veri['stok_biten']} ürünün stoğu tamamen tükendi. Acil tedarik gerekiyor."))
        if veri["kritik_sayi"] > 0:
            yorumlar.append(("⚠️", f"{veri['kritik_sayi']} ürün kritik stok seviyesinde (toplam ürünlerin %{veri['kritik_oran']}). Tedarik planı gözden geçirilmeli."))
        else:
            yorumlar.append(("✅", "Tüm ürünler normal stok seviyesinde. Kritik eşiği aşan ürün yok."))

        # Son 7 gün hareket dengesi
        giris, cikis = veri["son7_giris"], veri["son7_cikis"]
        if giris == 0 and cikis == 0:
            yorumlar.append(("💤", "Son 7 günde hiç stok hareketi yapılmamış."))
        elif cikis == 0:
            yorumlar.append(("📥", f"Son 7 günde yalnızca {giris} giriş işlemi yapılmış, çıkış yok."))
        elif giris == 0:
            yorumlar.append(("📤", f"Son 7 günde yalnızca {cikis} çıkış işlemi var, yeni giriş yapılmamış."))
        else:
            yorumlar.append(("📊", f"Son 7 günde {giris} giriş, {cikis} çıkış işlemi gerçekleşti."))

        # En yüksek değerli ürün
        en_degerli = db.en_yuksek_degerli_urun()
        if en_degerli and veri["toplam_deger"] > 0:
            oran = round(en_degerli["toplam_deger"] / veri["toplam_deger"] * 100, 1)
            yorumlar.append(("💰", f"Toplam stok değerinin %{oran}'i '{en_degerli['ad']}' ürününde yoğunlaşıyor."))

        # En aktif ürün
        if veri["en_aktif_urun"]:
            yorumlar.append(("🔥", f"Son 30 günde en aktif ürün '{veri['en_aktif_urun']['ad']}' ({veri['en_aktif_urun']['hareket_sayisi']} hareket)."))

        return yorumlar

    def dusuk_stok_csv_aktar(self) -> str:
        """Kritik stoktaki ürünleri CSV string olarak döner."""
        kritik = self.kritik_stok_kontrol()
        if not kritik:
            return ""
        df = pd.DataFrame(kritik)[["ad", "kategori_adi", "stok_miktari", "kritik_esik", "fiyat"]]
        df.columns = ["Ürün Adı", "Kategori", "Mevcut Stok", "Kritik Eşik", "Birim Fiyat (₺)"]
        return self._df_to_csv(df)

    def tum_urunler_csv_aktar(self) -> str:
        """Tüm ürünleri CSV string olarak döner."""
        urunler = db.urunleri_getir()
        if not urunler:
            return ""
        df = pd.DataFrame(urunler)[["ad", "kategori_adi", "fiyat", "stok_miktari", "kritik_esik"]]
        df["toplam_deger"] = df["fiyat"] * df["stok_miktari"]
        df.columns = ["Ürün Adı", "Kategori", "Birim Fiyat (₺)", "Stok", "Kritik Eşik", "Toplam Değer (₺)"]
        return self._df_to_csv(df)

    def tum_hareketler_csv_aktar(self) -> str:
        """Tüm stok hareketlerini CSV string olarak döner."""
        hareketler = db.hareketleri_getir()
        if not hareketler:
            return ""
        df = pd.DataFrame(hareketler)[
            ["tarih", "urun_adi", "tur", "miktar", "islem_sonrasi_stok", "aciklama"]
        ]
        df.columns = ["Tarih", "Ürün", "Tür", "Miktar", "Sonraki Stok", "Açıklama"]
        return self._df_to_csv(df)

    def kategori_raporu_csv_aktar(self) -> str:
        """Kategori bazlı ürün ve değer raporunu CSV olarak döner."""
        dagilim = db.kategori_dagilimi()
        if not dagilim:
            return ""
        df = pd.DataFrame(dagilim)
        df.columns = ["Kategori", "Ürün Sayısı", "Toplam Stok Değeri (₺)"]
        return self._df_to_csv(df)

    def demo_veri_yukle(self) -> Sonuc:
        """
        Gerçekçi demo verisi yükler; yalnızca ürün yokken çalışır.
        Tüm yükleme tek transaction'dır: hata olursa hiçbir şey yazılmaz.
        Hareketler kronolojik sırayla uygulanır, böylece "işlem sonrası stok"
        zinciri ve ürünlerin son stoğu birbiriyle tutarlı olur.
        """
        kategoriler_data = [
            ("Elektronik",        "Bilgisayar ve çevre birimleri"),
            ("Ofis & Kırtasiye",  "Kağıt, kalem ve ofis malzemeleri"),
            ("Temizlik & Hijyen", "Temizlik ürünleri ve sarf malzemeleri"),
        ]
        # (ad, kategori sırası, fiyat, hedef son stok, kritik eşik) — bazıları kritik stokta
        urunler_data = [
            ("Laptop Dell XPS 15",        0, 35000.0,  8,  3),
            ('Monitör 27" 4K',            0,  7500.0,  4,  5),   # kritik
            ("Mekanik Klavye",            0,  1200.0, 12,  5),
            ("USB Hub 7 Port",            0,   450.0,  9,  3),
            ("A4 Fotokopi Kağıdı (koli)", 1,   350.0, 45, 10),
            ("Tükenmez Kalem Seti",       1,    85.0,  3, 10),   # kritik
            ("Dezenfektan 5L",            2,   280.0, 18,  5),
            ("Kâğıt Havlu Koli",          2,    95.0, 22,  8),
        ]
        # (ürün sırası, tür, miktar, kaç gün önce, açıklama)
        hareketler_data = [
            (0, "giriş",  5, 28, "İlk sevkiyat"),
            (0, "çıkış",  2, 21, "Satış - Müşteri A"),
            (0, "çıkış",  1, 14, "Satış - Müşteri B"),
            (1, "giriş",  3, 25, "Tedarikçi: TechPro"),
            (1, "çıkış",  2, 10, "Ofis kurulumu"),
            (2, "giriş", 10, 20, "Toplu sipariş"),
            (2, "çıkış",  3,  8, "Yeni personel"),
            (4, "giriş", 20, 15, "Aylık sipariş"),
            (4, "çıkış",  8,  7, "Ofis kullanımı"),
            (4, "çıkış",  3,  3, "Toplantı odası"),
            (5, "giriş", 15, 30, "Başlangıç stoku"),
            (5, "çıkış", 12,  5, "Satış"),
            (6, "giriş", 10, 18, "Tedarikçi: CleanPro"),
            (6, "çıkış",  4,  2, "Haftalık kullanım"),
            (7, "giriş", 15, 12, "Toplu sipariş"),
        ]

        # Başlangıç stoku = hedef son stok − hareketlerin net etkisi
        net = [0] * len(urunler_data)
        for i, tur, miktar, _, _ in hareketler_data:
            net[i] += miktar if tur == "giriş" else -miktar

        try:
            with db.transaction() as conn:
                if db.urun_sayisi(conn) > 0:
                    return False, "Demo verisi yalnızca ürün bulunmayan bir veritabanına yüklenebilir."

                kat_ids = []
                for ad, aciklama in kategoriler_data:
                    mevcut = db.kategori_adla_getir(ad, conn)
                    kat_ids.append(
                        mevcut["id"] if mevcut
                        else db.kategori_ekle(Kategori(ad=ad, aciklama=aciklama), conn)
                    )

                u_ids = [
                    db.urun_ekle(
                        Urun(ad=ad, kategori_id=kat_ids[k], fiyat=fiyat,
                             stok_miktari=hedef - net[i], kritik_esik=esik),
                        conn,
                    )
                    for i, (ad, k, fiyat, hedef, esik) in enumerate(urunler_data)
                ]

                bugun = datetime.now()
                for i, tur, miktar, gun, aciklama in sorted(hareketler_data, key=lambda h: -h[3]):
                    tarih = (bugun - timedelta(days=gun)).strftime("%Y-%m-%d %H:%M:%S")
                    db.stok_hareketi_uygula(u_ids[i], tur, miktar, aciklama, tarih=tarih, conn=conn)
        except Exception as e:
            return False, f"Demo veri yüklenemedi: {e}"

        return True, (
            f"Demo verisi başarıyla yüklendi ({len(kategoriler_data)} kategori, "
            f"{len(urunler_data)} ürün, {len(hareketler_data)} hareket)."
        )

    @staticmethod
    def _df_to_csv(df: pd.DataFrame) -> str:
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        return buf.getvalue()
