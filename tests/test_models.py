import pytest

from models import Kategori, StokHareketi, Urun


def test_urun_adi_kirpilir():
    assert Urun(ad="  Kalem ", fiyat=1, stok_miktari=0, kritik_esik=0).ad == "Kalem"


@pytest.mark.parametrize(
    "alanlar",
    [
        {"ad": " ", "fiyat": 1, "stok_miktari": 0, "kritik_esik": 0},
        {"ad": "X", "fiyat": -1, "stok_miktari": 0, "kritik_esik": 0},
        {"ad": "X", "fiyat": 1, "stok_miktari": -1, "kritik_esik": 0},
        {"ad": "X", "fiyat": 1, "stok_miktari": 0, "kritik_esik": -1},
    ],
)
def test_gecersiz_urun_reddedilir(alanlar):
    with pytest.raises(ValueError):
        Urun(**alanlar)


def test_kritik_mi_ve_toplam_deger():
    u = Urun(ad="X", fiyat=2.5, stok_miktari=4, kritik_esik=4)
    assert u.kritik_mi
    assert u.toplam_deger == 10.0


def test_bos_kategori_reddedilir():
    with pytest.raises(ValueError):
        Kategori(ad="   ")


@pytest.mark.parametrize("tur, miktar", [("iade", 1), ("giriş", 0), ("çıkış", -3)])
def test_gecersiz_hareket_reddedilir(tur, miktar):
    with pytest.raises(ValueError):
        StokHareketi(urun_id=1, tur=tur, miktar=miktar, islem_sonrasi_stok=0)


@pytest.mark.parametrize(
    "metin, beklenen",
    [("IŞIK", "ışık"), ("İzmir", "izmir"), ("ISPARTA", "ısparta"), ("Çiğ Köfte", "çiğ köfte")],
)
def test_tr_kucuk(metin, beklenen):
    from models import tr_kucuk
    assert tr_kucuk(metin) == beklenen
