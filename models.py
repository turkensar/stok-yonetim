"""
Veri modelleri — uygulamanın temel OOP yapısı.
Katmanlar arası veri taşıma için dataclass kullanılır.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional


def tr_kucuk(metin: str) -> str:
    """
    Türkçe kurallarıyla küçük harfe çevirir: 'I' → 'ı', 'İ' → 'i'.
    str.lower() ve SQLite LOWER() bu harfleri doğru dönüştürmez.
    """
    return metin.replace("I", "ı").replace("İ", "i").lower()


def kurusa_cevir(tutar: float) -> int:
    """
    TL tutarını kuruş cinsinden tamsayıya çevirir (yarımlar yukarı yuvarlanır).
    Float çarpımı yerine Decimal kullanılır: 1.005 * 100 = 100.49999… hatasını önler.
    """
    try:
        d = Decimal(str(tutar))
    except InvalidOperation:
        raise ValueError("Geçersiz tutar.") from None
    if not d.is_finite():
        raise ValueError("Geçersiz tutar.")
    return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class Kategori:
    ad: str
    aciklama: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        self.ad = self.ad.strip()
        if not self.ad:
            raise ValueError("Kategori adı boş olamaz.")


@dataclass
class Urun:
    ad: str
    fiyat: float
    stok_miktari: int
    kritik_esik: int
    kategori_id: Optional[int] = None
    id: Optional[int] = None

    def __post_init__(self):
        self.ad = self.ad.strip()
        if not self.ad:
            raise ValueError("Ürün adı boş olamaz.")
        if kurusa_cevir(self.fiyat) < 0:
            raise ValueError("Fiyat negatif olamaz.")
        if self.stok_miktari < 0:
            raise ValueError("Stok miktarı negatif olamaz.")
        if self.kritik_esik < 0:
            raise ValueError("Kritik eşik negatif olamaz.")

    @property
    def kritik_mi(self) -> bool:
        """Stok miktarı kritik eşiğinde veya altındaysa True döner."""
        return self.stok_miktari <= self.kritik_esik

    @property
    def fiyat_kurus(self) -> int:
        """Birim fiyatın kuruş cinsinden tam değeri (veritabanında böyle saklanır)."""
        return kurusa_cevir(self.fiyat)

    @property
    def toplam_deger(self) -> float:
        """Ürünün toplam stok değeri (fiyat × miktar), kuruş hassasiyetinde."""
        return self.fiyat_kurus * self.stok_miktari / 100


@dataclass
class StokHareketi:
    urun_id: int
    tur: str                # "giriş" veya "çıkış"
    miktar: int
    islem_sonrasi_stok: int
    aciklama: str = ""
    tarih: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    id: Optional[int] = None

    def __post_init__(self):
        if self.tur not in ("giriş", "çıkış"):
            raise ValueError("Hareket türü 'giriş' veya 'çıkış' olmalıdır.")
        if self.miktar <= 0:
            raise ValueError("Hareket miktarı sıfırdan büyük olmalıdır.")
