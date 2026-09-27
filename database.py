"""
Veritabanı katmanı — SQLite bağlantısı ve CRUD fonksiyonları.
İş kuralı içermez; ham veri alıp verir.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from models import Kategori, Urun, StokHareketi

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stok.db")

# Şema her değiştiğinde artırılır; init_db eksik migration'ları sırayla uygular.
SEMA_SURUMU = 1


class YetersizStokHatasi(Exception):
    """Çıkış miktarı mevcut stoğu aştığında fırlatılır."""

    def __init__(self, mevcut: int, talep: int):
        super().__init__(f"Yetersiz stok: mevcut {mevcut}, talep {talep}")
        self.mevcut = mevcut
        self.talep = talep


# ─────────────────────────────────────────────────────────────────────────────
# Bağlantı
# ─────────────────────────────────────────────────────────────────────────────

def _baglan() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Başarıda commit, hatada rollback yapar ve bağlantıyı her durumda kapatır."""
    conn = _baglan()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_KATEGORILER_SEMA = """
    CREATE TABLE IF NOT EXISTS kategoriler (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ad       TEXT    NOT NULL UNIQUE,
        aciklama TEXT    DEFAULT ''
    )
"""

_URUNLER_SEMA = """
    CREATE TABLE IF NOT EXISTS urunler (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ad            TEXT    NOT NULL,
        kategori_id   INTEGER,
        fiyat         REAL    NOT NULL DEFAULT 0 CHECK (fiyat >= 0),
        stok_miktari  INTEGER NOT NULL DEFAULT 0 CHECK (stok_miktari >= 0),
        kritik_esik   INTEGER NOT NULL DEFAULT 5 CHECK (kritik_esik >= 0),
        FOREIGN KEY (kategori_id) REFERENCES kategoriler(id)
    )
"""

_HAREKETLER_SEMA = """
    CREATE TABLE IF NOT EXISTS stok_hareketleri (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        urun_id             INTEGER NOT NULL,
        tur                 TEXT    NOT NULL CHECK (tur IN ('giriş', 'çıkış')),
        miktar              INTEGER NOT NULL CHECK (miktar > 0),
        tarih               TEXT    NOT NULL,
        aciklama            TEXT    DEFAULT '',
        islem_sonrasi_stok  INTEGER NOT NULL CHECK (islem_sonrasi_stok >= 0),
        FOREIGN KEY (urun_id) REFERENCES urunler(id)
    )
"""


def _tablo_var_mi(conn: sqlite3.Connection, ad: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (ad,)
    ).fetchone() is not None


def _migration_1(conn: sqlite3.Connection) -> None:
    """CHECK kısıtları ve indeksler. Eski şemalı tablolar yeniden kurulur."""
    eski_urunler = _tablo_var_mi(conn, "urunler")
    eski_hareketler = _tablo_var_mi(conn, "stok_hareketleri")
    if eski_urunler:
        conn.execute("ALTER TABLE urunler RENAME TO _urunler_eski")
    if eski_hareketler:
        conn.execute("ALTER TABLE stok_hareketleri RENAME TO _hareketler_eski")

    conn.execute(_KATEGORILER_SEMA)
    conn.execute(_URUNLER_SEMA)
    conn.execute(_HAREKETLER_SEMA)

    if eski_urunler:
        conn.execute(
            """INSERT INTO urunler (id, ad, kategori_id, fiyat, stok_miktari, kritik_esik)
               SELECT id, ad, kategori_id, MAX(fiyat, 0), MAX(stok_miktari, 0),
                      MAX(kritik_esik, 0)
               FROM _urunler_eski"""
        )
        conn.execute("DROP TABLE _urunler_eski")
    if eski_hareketler:
        conn.execute(
            """INSERT INTO stok_hareketleri
               (id, urun_id, tur, miktar, tarih, aciklama, islem_sonrasi_stok)
               SELECT id, urun_id, tur, miktar, tarih, aciklama,
                      MAX(islem_sonrasi_stok, 0)
               FROM _hareketler_eski"""
        )
        conn.execute("DROP TABLE _hareketler_eski")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hareket_urun_tarih "
        "ON stok_hareketleri (urun_id, tarih)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hareket_tarih ON stok_hareketleri (tarih)"
    )


_MIGRATIONLAR = {1: _migration_1}


def init_db() -> None:
    """Tabloları oluşturur ve bekleyen şema migration'larını uygular."""
    conn = _baglan()
    conn.isolation_level = None  # transaction'ları elle yönetiyoruz
    try:
        # Tablo yeniden kurulurken FK kontrolü kapalı olmalı (transaction dışında ayarlanır).
        conn.execute("PRAGMA foreign_keys = OFF")
        surum = conn.execute("PRAGMA user_version").fetchone()[0]
        for hedef in range(surum + 1, SEMA_SURUMU + 1):
            conn.execute("BEGIN IMMEDIATE")
            try:
                _MIGRATIONLAR[hedef](conn)
                conn.execute(f"PRAGMA user_version = {hedef}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Kategoriler
# ─────────────────────────────────────────────────────────────────────────────

def kategori_ekle(k: Kategori) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO kategoriler (ad, aciklama) VALUES (?, ?)",
            (k.ad, k.aciklama),
        )
        return cur.lastrowid


def kategorileri_getir() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM kategoriler ORDER BY ad").fetchall()
    return [dict(r) for r in rows]


def kategori_getir(kategori_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM kategoriler WHERE id = ?", (kategori_id,)
        ).fetchone()
    return dict(row) if row else None


def kategori_sil(kategori_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM kategoriler WHERE id = ?", (kategori_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Ürünler
# ─────────────────────────────────────────────────────────────────────────────

def urun_ekle(u: Urun) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO urunler (ad, kategori_id, fiyat, stok_miktari, kritik_esik)
               VALUES (?, ?, ?, ?, ?)""",
            (u.ad, u.kategori_id, u.fiyat, u.stok_miktari, u.kritik_esik),
        )
        return cur.lastrowid


def urunleri_getir(kategori_id: Optional[int] = None) -> list[dict]:
    with get_connection() as conn:
        if kategori_id:
            rows = conn.execute(
                """SELECT u.*, k.ad AS kategori_adi
                   FROM urunler u
                   LEFT JOIN kategoriler k ON u.kategori_id = k.id
                   WHERE u.kategori_id = ?
                   ORDER BY u.ad""",
                (kategori_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT u.*, k.ad AS kategori_adi
                   FROM urunler u
                   LEFT JOIN kategoriler k ON u.kategori_id = k.id
                   ORDER BY u.ad"""
            ).fetchall()
    return [dict(r) for r in rows]


def urun_getir(urun_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.*, k.ad AS kategori_adi
               FROM urunler u
               LEFT JOIN kategoriler k ON u.kategori_id = k.id
               WHERE u.id = ?""",
            (urun_id,),
        ).fetchone()
    return dict(row) if row else None


def urun_guncelle(u: Urun) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE urunler
               SET ad=?, kategori_id=?, fiyat=?, stok_miktari=?, kritik_esik=?
               WHERE id=?""",
            (u.ad, u.kategori_id, u.fiyat, u.stok_miktari, u.kritik_esik, u.id),
        )


def urun_sil(urun_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM stok_hareketleri WHERE urun_id = ?", (urun_id,))
        conn.execute("DELETE FROM urunler WHERE id = ?", (urun_id,))


def urun_hareket_sayisi(urun_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS sayi FROM stok_hareketleri WHERE urun_id = ?",
            (urun_id,),
        ).fetchone()
    return row["sayi"]


# ─────────────────────────────────────────────────────────────────────────────
# Stok Hareketleri
# ─────────────────────────────────────────────────────────────────────────────

def hareket_ekle(h: StokHareketi) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO stok_hareketleri
               (urun_id, tur, miktar, tarih, aciklama, islem_sonrasi_stok)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (h.urun_id, h.tur, h.miktar, h.tarih, h.aciklama, h.islem_sonrasi_stok),
        )
        return cur.lastrowid


def stok_hareketi_uygula(
    urun_id: int,
    tur: str,
    miktar: int,
    aciklama: str = "",
    tarih: Optional[str] = None,
) -> dict:
    """
    Stoğu günceller ve hareketi kaydeder — ikisi tek transaction içinde.
    Stok, okuma-yazma yarışına düşmemek için SQL tarafında atomik olarak değişir.
    Ürün yoksa LookupError, stok yetmezse YetersizStokHatasi fırlatır.
    """
    delta = miktar if tur == "giriş" else -miktar
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """UPDATE urunler SET stok_miktari = stok_miktari + ?
               WHERE id = ? AND stok_miktari + ? >= 0""",
            (delta, urun_id, delta),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT stok_miktari FROM urunler WHERE id = ?", (urun_id,)
            ).fetchone()
            if row is None:
                raise LookupError("Ürün bulunamadı.")
            raise YetersizStokHatasi(row["stok_miktari"], miktar)

        urun = conn.execute(
            "SELECT stok_miktari, kritik_esik FROM urunler WHERE id = ?", (urun_id,)
        ).fetchone()
        h = StokHareketi(
            urun_id=urun_id,
            tur=tur,
            miktar=miktar,
            islem_sonrasi_stok=urun["stok_miktari"],
            aciklama=aciklama,
        )
        if tarih:
            h.tarih = tarih
        conn.execute(
            """INSERT INTO stok_hareketleri
               (urun_id, tur, miktar, tarih, aciklama, islem_sonrasi_stok)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (h.urun_id, h.tur, h.miktar, h.tarih, h.aciklama, h.islem_sonrasi_stok),
        )
    return {"yeni_stok": urun["stok_miktari"], "kritik_esik": urun["kritik_esik"]}


def hareketleri_getir(
    urun_id: Optional[int] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    tur: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    query = """
        SELECT sh.*, u.ad AS urun_adi
        FROM stok_hareketleri sh
        JOIN urunler u ON sh.urun_id = u.id
        WHERE 1=1
    """
    params: list = []
    if urun_id:
        query += " AND sh.urun_id = ?"
        params.append(urun_id)
    if baslangic:
        query += " AND sh.tarih >= ?"
        params.append(baslangic)
    if bitis:
        query += " AND sh.tarih <= ?"
        params.append(bitis + " 23:59:59")
    if tur:
        query += " AND sh.tur = ?"
        params.append(tur)
    query += " ORDER BY sh.tarih DESC"
    if limit:
        query += f" LIMIT {int(limit)}"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def son_hareketleri_getir(n: int = 10) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT sh.*, u.ad AS urun_adi
               FROM stok_hareketleri sh
               JOIN urunler u ON sh.urun_id = u.id
               ORDER BY sh.tarih DESC LIMIT ?""",
            (n,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Sorguları
# ─────────────────────────────────────────────────────────────────────────────

def urun_adi_var_mi(ad: str, exclude_id: Optional[int] = None) -> bool:
    """Aynı isimde başka bir ürün var mı kontrol eder."""
    with get_connection() as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT id FROM urunler WHERE LOWER(ad) = LOWER(?) AND id != ?",
                (ad, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM urunler WHERE LOWER(ad) = LOWER(?)", (ad,)
            ).fetchone()
    return row is not None


def kategorileri_urun_sayisiyla_getir() -> list[dict]:
    """Her kategorinin ürün sayısıyla birlikte listesini döner."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT k.*, COUNT(u.id) AS urun_sayisi
               FROM kategoriler k
               LEFT JOIN urunler u ON u.kategori_id = k.id
               GROUP BY k.id
               ORDER BY k.ad"""
        ).fetchall()
    return [dict(r) for r in rows]


def en_yuksek_degerli_urun() -> Optional[dict]:
    """Toplam stok değeri (fiyat × stok) en yüksek ürünü döner."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT ad, fiyat, stok_miktari,
                      (fiyat * stok_miktari) AS toplam_deger
               FROM urunler
               ORDER BY toplam_deger DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def kategori_dagilimi() -> list[dict]:
    """Kategori bazında ürün sayısı ve toplam stok değerini döner."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT k.ad AS kategori,
                      COUNT(u.id) AS urun_sayisi,
                      COALESCE(SUM(u.fiyat * u.stok_miktari), 0) AS toplam_deger
               FROM kategoriler k
               LEFT JOIN urunler u ON u.kategori_id = k.id
               GROUP BY k.id
               ORDER BY toplam_deger DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def dashboard_verisi_getir() -> dict:
    with get_connection() as conn:
        toplam_urun = conn.execute("SELECT COUNT(*) FROM urunler").fetchone()[0]
        toplam_stok = conn.execute("SELECT SUM(stok_miktari) FROM urunler").fetchone()[0] or 0
        toplam_deger = conn.execute(
            "SELECT SUM(fiyat * stok_miktari) FROM urunler"
        ).fetchone()[0] or 0.0
        kritik_sayi = conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE stok_miktari <= kritik_esik"
        ).fetchone()[0]

        # Kritik stok oranı için toplam ürün sayısı zaten var
        kritik_oran = round(kritik_sayi / toplam_urun * 100, 1) if toplam_urun else 0

        # En çok hareket gören ürün (son 30 gün)
        en_aktif = conn.execute(
            """SELECT u.ad, COUNT(sh.id) AS hareket_sayisi
               FROM stok_hareketleri sh
               JOIN urunler u ON sh.urun_id = u.id
               WHERE sh.tarih >= date('now', '-30 days')
               GROUP BY sh.urun_id
               ORDER BY hareket_sayisi DESC LIMIT 1"""
        ).fetchone()

        # Son 7 günde giriş/çıkış sayısı
        son7 = conn.execute(
            """SELECT tur, COUNT(*) AS sayi
               FROM stok_hareketleri
               WHERE tarih >= date('now', '-7 days')
               GROUP BY tur"""
        ).fetchall()

        # Stoku tamamen biten ürün sayısı
        stok_biten = conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE stok_miktari = 0"
        ).fetchone()[0]

    son7_dict = {r["tur"]: r["sayi"] for r in son7}
    return {
        "toplam_urun": toplam_urun,
        "toplam_stok": int(toplam_stok),
        "toplam_deger": round(toplam_deger, 2),
        "kritik_sayi": kritik_sayi,
        "kritik_oran": kritik_oran,
        "stok_biten": stok_biten,
        "en_aktif_urun": dict(en_aktif) if en_aktif else None,
        "son7_giris": son7_dict.get("giriş", 0),
        "son7_cikis": son7_dict.get("çıkış", 0),
    }
