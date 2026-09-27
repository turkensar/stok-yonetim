import pytest
import sqlite3
import threading

import database as db


# ── Kategoriler ──────────────────────────────────────────────────────────────

def test_kategori_ekle_ve_tekrar_reddi(servis):
    assert servis.kategori_ekle("Gıda")[0]
    basari, mesaj = servis.kategori_ekle("Gıda")
    assert not basari and "zaten mevcut" in mesaj


def test_kategori_tekrari_turkce_harf_duyarsiz(servis):
    assert servis.kategori_ekle("İçecek")[0]
    assert not servis.kategori_ekle("içecek")[0]
    assert servis.kategori_ekle("Icecek")[0]  # 'I' → 'ı', farklı bir ad


def test_bos_kategori_adi_reddedilir(servis):
    assert not servis.kategori_ekle("   ")[0]


def test_urunu_olan_kategori_silinemez(servis, kategori_id, urun_id):
    assert not servis.kategori_sil(kategori_id)[0]


def test_yalnizca_silinmis_urunu_olan_kategori_silinebilir(servis, kategori_id, urun_id):
    servis.urun_sil(urun_id)
    assert servis.kategori_sil(kategori_id)[0]
    # Silinen ürünün geçmişi yerinde kalır
    assert len(servis.hareket_gecmisi()) == 1


# ── Ürünler ──────────────────────────────────────────────────────────────────

def test_baslangic_stogu_hareket_olarak_kaydedilir(servis, urun_id):
    hareketler = servis.hareket_gecmisi(urun_id=urun_id)
    assert len(hareketler) == 1
    h = hareketler[0]
    assert (h["tur"], h["miktar"], h["islem_sonrasi_stok"]) == ("giriş", 10, 10)
    assert h["aciklama"] == "Başlangıç stoku"


def test_sifir_stoklu_urun_hareket_olusturmaz(servis, kategori_id):
    servis.urun_ekle("Silgi", 5.0, 0, 1, kategori_id)
    assert servis.hareket_gecmisi() == []


def test_ayni_isimli_urun_eklenemez(servis, kategori_id, urun_id):
    basari, _ = servis.urun_ekle("  kalem ", 1.0, 1, 1, kategori_id)
    assert not basari
    assert len(servis.urunleri_getir()) == 1


@pytest.mark.parametrize("ilk, ikinci", [("IŞIK", "ışık"), ("İpek İp", "ipek ip")])
def test_urun_tekrari_turkce_harf_duyarsiz(servis, kategori_id, ilk, ikinci):
    assert servis.urun_ekle(ilk, 1.0, 0, 0, kategori_id)[0]
    assert not servis.urun_ekle(ikinci, 1.0, 0, 0, kategori_id)[0]


def test_gecersiz_urun_hicbir_sey_yazmaz(servis, kategori_id):
    assert not servis.urun_ekle("Bozuk", -5.0, 3, 1, kategori_id)[0]
    assert servis.urunleri_getir() == []
    assert servis.hareket_gecmisi() == []


def test_guncelleme_stogu_degistirmez(servis, kategori_id, urun_id):
    assert servis.urun_guncelle(urun_id, "Kurşun Kalem", 12.0, 5, kategori_id)[0]
    urun = db.urun_getir(urun_id)
    assert urun["ad"] == "Kurşun Kalem"
    assert urun["fiyat"] == 12.0 and urun["kritik_esik"] == 5
    assert urun["stok_miktari"] == 10


def test_guncellemede_isim_cakismasi_reddedilir(servis, kategori_id, urun_id):
    servis.urun_ekle("Defter", 5.0, 0, 1, kategori_id)
    basari, mesaj = servis.urun_guncelle(urun_id, "defter", 1.0, 1, kategori_id)
    assert not basari and "zaten mevcut" in mesaj


def test_urun_silme_gecmisi_korur(servis, urun_id):
    servis.stok_cikisi_yap(urun_id, 2)
    basari, mesaj = servis.urun_sil(urun_id)
    assert basari and "korunuyor" in mesaj
    assert servis.urunleri_getir() == []
    assert db.urun_getir(urun_id) is None
    gecmis = servis.hareket_gecmisi()
    assert len(gecmis) == 2
    assert all(h["urun_adi"] == "Kalem (silindi)" for h in gecmis)
    assert servis.dashboard_verileri()["toplam_urun"] == 0


def test_silinen_urunun_adi_yeniden_kullanilabilir(servis, kategori_id, urun_id):
    servis.urun_sil(urun_id)
    assert servis.urun_ekle("Kalem", 1.0, 0, 0, kategori_id)[0]


# ── Stok hareketleri ─────────────────────────────────────────────────────────

def test_giris_ve_cikis_stogu_gunceller(servis, urun_id):
    assert servis.stok_girisi_yap(urun_id, 5)[0]
    assert servis.stok_cikisi_yap(urun_id, 3)[0]
    assert db.urun_getir(urun_id)["stok_miktari"] == 12
    son = servis.hareket_gecmisi(urun_id=urun_id, tur="çıkış")[0]
    assert son["islem_sonrasi_stok"] == 12


def test_yetersiz_stokta_cikis_reddedilir(servis, urun_id):
    basari, mesaj = servis.stok_cikisi_yap(urun_id, 11)
    assert not basari and "Mevcut: 10" in mesaj
    assert db.urun_getir(urun_id)["stok_miktari"] == 10
    assert len(servis.hareket_gecmisi(urun_id=urun_id)) == 1


def test_kritik_esige_inince_uyari_verilir(servis, urun_id):
    basari, mesaj = servis.stok_cikisi_yap(urun_id, 7)
    assert basari and "Kritik" in mesaj


def test_gecersiz_miktar_ve_urun(servis, urun_id):
    assert not servis.stok_girisi_yap(urun_id, 0)[0]
    assert not servis.stok_cikisi_yap(urun_id, -1)[0]
    assert servis.stok_girisi_yap(9999, 1) == (False, "Ürün bulunamadı.")


def test_silinmis_urune_hareket_yapilamaz(servis, urun_id):
    servis.urun_sil(urun_id)
    assert not servis.stok_girisi_yap(urun_id, 1)[0]


def test_eszamanli_cikislar_stogu_negatife_dusurmez(servis, urun_id):
    servis.stok_girisi_yap(urun_id, 90)  # stok: 100
    sonuclar = []

    def cikis():
        sonuclar.append(servis.stok_cikisi_yap(urun_id, 10)[0])

    threadler = [threading.Thread(target=cikis) for _ in range(20)]
    for t in threadler:
        t.start()
    for t in threadler:
        t.join()

    assert sonuclar.count(True) == 10
    assert db.urun_getir(urun_id)["stok_miktari"] == 0
    cikislar = servis.hareket_gecmisi(urun_id=urun_id, tur="çıkış")
    assert sorted(h["islem_sonrasi_stok"] for h in cikislar) == list(range(0, 100, 10))


def test_db_kisitlari_negatif_stogu_engeller(servis, urun_id):
    with sqlite3.connect(db.DB_PATH) as conn:
        try:
            conn.execute("UPDATE urunler SET stok_miktari = -1 WHERE id = ?", (urun_id,))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("CHECK kısıtı çalışmadı")


# ── Demo verisi ──────────────────────────────────────────────────────────────

def test_demo_verisi_tutarli(servis):
    basari, _ = servis.demo_veri_yukle()
    assert basari
    assert len(servis.urunleri_getir()) == 8
    assert len(servis.hareket_gecmisi()) == 15
    assert len(servis.kritik_stok_kontrol()) == 2
    for urun in servis.urunleri_getir():
        hareketler = sorted(servis.hareket_gecmisi(urun_id=urun["id"]), key=lambda h: h["tarih"])
        if hareketler:
            assert hareketler[-1]["islem_sonrasi_stok"] == urun["stok_miktari"]


def test_demo_verisi_urun_varken_yuklenmez(servis, urun_id):
    assert not servis.demo_veri_yukle()[0]
    assert len(servis.urunleri_getir()) == 1


# ── Raporlama ────────────────────────────────────────────────────────────────

def test_csv_ciktilari(servis):
    assert servis.tum_urunler_csv_aktar() == ""
    servis.demo_veri_yukle()
    assert servis.tum_urunler_csv_aktar().startswith("Ürün Adı,")
    assert servis.dusuk_stok_csv_aktar().count("\n") == 3  # başlık + 2 kritik ürün
    assert servis.tum_hareketler_csv_aktar().count("\n") == 16
    assert "Elektronik" in servis.kategori_raporu_csv_aktar()


def test_dashboard_analizi(servis):
    servis.demo_veri_yukle()
    veri = servis.dashboard_verileri()
    assert veri["toplam_urun"] == 8 and veri["kritik_sayi"] == 2
    metinler = " ".join(m for _, m in servis.dashboard_analiz_yorumu(veri))
    assert "kritik stok" in metinler


# ── Saat dilimi ──────────────────────────────────────────────────────────────

@pytest.fixture
def utc_den_farkli_gunde_saat_dilimi(monkeypatch):
    """Yerel tarihin UTC tarihinden farklı olduğu bir saat dilimine geçer."""
    import time
    from datetime import datetime, timezone

    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset bu platformda yok")
    utc_gunu = datetime.now(timezone.utc).date()
    for tz in ("Etc/GMT-14", "Etc/GMT+12"):  # UTC+14 ve UTC−12
        monkeypatch.setenv("TZ", tz)
        time.tzset()
        if datetime.now().date() != utc_gunu:
            break
    yield
    monkeypatch.undo()
    time.tzset()


def test_son_7_gun_yerel_saate_gore_hesaplanir(servis, urun_id, utc_den_farkli_gunde_saat_dilimi):
    from datetime import date, timedelta

    bugun = date.today()
    for gun in (7, 8):  # 7 gün önce: dahil, 8 gün önce: hariç
        tarih = f"{bugun - timedelta(days=gun)} 12:00:00"
        db.stok_hareketi_uygula(urun_id, "giriş", 1, tarih=tarih)

    veri = servis.dashboard_verileri()
    # Fixture'daki başlangıç stoku hareketi de bugün, son 7 güne dahil.
    assert veri["son7_giris"] == 2


# ── Para hassasiyeti ─────────────────────────────────────────────────────────

def test_toplam_deger_kurus_hassasiyetinde(servis, kategori_id):
    for i in range(10):
        servis.urun_ekle(f"Ürün {i}", 0.1, 3, 0, kategori_id)
    assert servis.dashboard_verileri()["toplam_deger"] == 3.0
    assert db.kategori_dagilimi()[0]["toplam_deger"] == 3.0
    assert "0.30000000000000004" not in servis.tum_urunler_csv_aktar()


def test_fiyat_kurusa_yuvarlanarak_saklanir(servis, kategori_id):
    servis.urun_ekle("Vida", 1.005, 0, 0, kategori_id)
    assert servis.urunleri_getir()[0]["fiyat"] == 1.01
