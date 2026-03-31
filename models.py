"""
Veri modelleri — uygulamanın temel OOP yapısı.
Katmanlar arası veri taşıma için dataclass kullanılır.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
        if self.fiyat < 0:
            raise ValueError("Fiyat negatif olamaz.")
        if self.stok_miktari < 0:
            raise ValueError("Stok miktarı negatif olamaz.")
        if self.kritik_esik < 0:
            raise ValueError("Kritik eşik negatif olamaz.")

    @property
    def kritik_mi(self) -> bool:
        """Stok miktarı kritik eşiğin altındaysa True döner."""
        return self.stok_miktari <= self.kritik_esik

    @property
    def toplam_deger(self) -> float:
        """Ürünün toplam stok değeri (fiyat × miktar)."""
        return self.fiyat * self.stok_miktari


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
