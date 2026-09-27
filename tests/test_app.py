"""Streamlit arayüzünün tüm sayfalarının hatasız açıldığını doğrulayan duman testleri."""
import pytest
from streamlit.testing.v1 import AppTest

SAYFALAR = ["📊 Dashboard", "🏷️ Kategoriler", "📦 Ürünler",
            "📋 Hareketler", "⚠️ Kritik Stok", "📈 Raporlama"]


@pytest.mark.parametrize("demo", [False, True], ids=["bos", "demo"])
@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfa_hatasiz_acilir(servis, sayfa, demo):
    if demo:
        servis.demo_veri_yukle()
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.sidebar.radio[0].set_value(sayfa).run()
    assert not at.exception


def _hareketler_sayfasi(servis):
    servis.demo_veri_yukle()
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.sidebar.radio[0].set_value("📋 Hareketler").run()
    return at


def test_urun_secimi_stok_bilgisini_hemen_gunceller(servis):
    at = _hareketler_sayfasi(servis)
    urunler = {u["ad"]: u for u in servis.urunleri_getir()}
    secim = at.selectbox(key="cikis_urun")
    for ad in ("Mekanik Klavye", "Tükenmez Kalem Seti"):
        secim.set_value(urunler[ad]["id"]).run()
        stok = urunler[ad]["stok_miktari"]
        assert any(f"Mevcut stok: **{stok} adet**  ·" in c.value for c in at.caption)


def test_basari_mesaji_yenilemeden_sonra_gorunur(servis):
    at = _hareketler_sayfasi(servis)
    urun = next(u for u in servis.urunleri_getir() if u["ad"] == "Mekanik Klavye")
    at.selectbox(key="giris_urun").set_value(urun["id"]).run()
    at.number_input[0].set_value(4)
    at.button[0].click().run()  # ilk form: Giriş Yap
    assert not at.exception
    assert [t.value for t in at.toast] == ["✅ 4 adet giriş yapıldı. Yeni stok: 16"]


def test_ters_tarih_araligi_hata_gosterir(servis):
    from datetime import date
    at = _hareketler_sayfasi(servis)
    at.date_input[0].set_value(date(2026, 5, 10))
    at.date_input[1].set_value(date(2026, 5, 1)).run()
    assert not at.exception
    assert [e.value for e in at.error] == ["Başlangıç tarihi bitiş tarihinden sonra olamaz."]
