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
