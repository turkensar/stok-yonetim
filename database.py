"""
Veritabanı katmanı — SQLite bağlantısı ve CRUD fonksiyonları.
İş kuralı içermez; ham veri alıp verir.
"""

import os
import sqlite3
from typing import Optional

from models import Kategori, Urun, StokHareketi

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stok.db")


# ─────────────────────────────────────────────────────────────────────────────
# Bağlantı
# ─────────────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Tablolar yoksa oluşturur. Uygulama ilk açılışında çağrılır."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kategoriler (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ad       TEXT    NOT NULL UNIQUE,
                aciklama TEXT    DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urunler (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ad            TEXT    NOT NULL,
                kategori_id   INTEGER,
                fiyat         REAL    NOT NULL DEFAULT 0,
                stok_miktari  INTEGER NOT NULL DEFAULT 0,
                kritik_esik   INTEGER NOT NULL DEFAULT 5,
                FOREIGN KEY (kategori_id) REFERENCES kategoriler(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stok_hareketleri (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                urun_id             INTEGER NOT NULL,
                tur                 TEXT    NOT NULL,
                miktar              INTEGER NOT NULL,
                tarih               TEXT    NOT NULL,
                aciklama            TEXT    DEFAULT '',
                islem_sonrasi_stok  INTEGER NOT NULL,
                FOREIGN KEY (urun_id) REFERENCES urunler(id)
            )
        """)


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


def urun_stok_guncelle(urun_id: int, yeni_stok: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE urunler SET stok_miktari = ? WHERE id = ?",
            (yeni_stok, urun_id),
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
