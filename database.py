"""
Veritabanı katmanı — SQLite bağlantısı ve CRUD fonksiyonları.
İş kuralı içermez; ham veri alıp verir.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional

from models import Kategori, Urun, StokHareketi, kurusa_cevir, tr_kucuk

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stok.db")

# Şema her değiştiğinde artırılır; init_db eksik migration'ları sırayla uygular.
SEMA_SURUMU = 3


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
    # SQLite'ın LOWER() fonksiyonu yalnızca ASCII harfleri dönüştürür.
    conn.create_function("TR_LOWER", 1, tr_kucuk, deterministic=True)
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


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Yazma kilidini baştan alan (BEGIN IMMEDIATE) bir transaction açar."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        yield conn


@contextmanager
def _baglanti(conn: Optional[sqlite3.Connection]) -> Iterator[sqlite3.Connection]:
    """Verilen bağlantıyı kullanır; yoksa kendi bağlantısını açıp kapatır."""
    if conn is not None:
        yield conn
    else:
        with get_connection() as yeni:
            yield yeni


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


def _migration_2(conn: sqlite3.Connection) -> None:
    """Ürünler silinmek yerine pasife alınır; hareket geçmişi korunur."""
    conn.execute(
        "ALTER TABLE urunler ADD COLUMN "
        "aktif INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1))"
    )


def _migration_3(conn: sqlite3.Connection) -> None:
    """
    Fiyat, kayan nokta (REAL) yerine kuruş cinsinden tamsayı olarak saklanır.
    SQLite sütun tipi değiştiremediği için tablo yeniden kurulur. Önerilen sıra
    izlenir (yeni tablo → kopyala → eskiyi sil → yeniden adlandır); böylece
    stok_hareketleri'nin yabancı anahtarı 'urunler' adını göstermeye devam eder.
    """
    conn.execute("""
        CREATE TABLE urunler_yeni (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ad            TEXT    NOT NULL,
            kategori_id   INTEGER,
            fiyat_kurus   INTEGER NOT NULL DEFAULT 0 CHECK (fiyat_kurus >= 0),
            stok_miktari  INTEGER NOT NULL DEFAULT 0 CHECK (stok_miktari >= 0),
            kritik_esik   INTEGER NOT NULL DEFAULT 5 CHECK (kritik_esik >= 0),
            aktif         INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1)),
            FOREIGN KEY (kategori_id) REFERENCES kategoriler(id)
        )
    """)
    conn.create_function("KURUS", 1, kurusa_cevir, deterministic=True)
    conn.execute(
        """INSERT INTO urunler_yeni
           (id, ad, kategori_id, fiyat_kurus, stok_miktari, kritik_esik, aktif)
           SELECT id, ad, kategori_id, KURUS(fiyat),
                  stok_miktari, kritik_esik, aktif
           FROM urunler"""
    )
    conn.execute("DROP TABLE urunler")
    conn.execute("ALTER TABLE urunler_yeni RENAME TO urunler")


_MIGRATIONLAR = {1: _migration_1, 2: _migration_2, 3: _migration_3}

# Ürün sorgularında dönen sütunlar; fiyat arayüz için TL'ye çevrilir.
_URUN_SUTUNLARI = (
    "u.id, u.ad, u.kategori_id, u.fiyat_kurus / 100.0 AS fiyat, "
    "u.stok_miktari, u.kritik_esik, u.aktif"
)


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

def kategori_ekle(k: Kategori, conn: Optional[sqlite3.Connection] = None) -> int:
    with _baglanti(conn) as conn:
        cur = conn.execute(
            "INSERT INTO kategoriler (ad, aciklama) VALUES (?, ?)",
            (k.ad, k.aciklama),
        )
        return cur.lastrowid


def kategorileri_getir() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM kategoriler ORDER BY ad").fetchall()
    return [dict(r) for r in rows]


def kategori_adla_getir(
    ad: str, conn: Optional[sqlite3.Connection] = None
) -> Optional[dict]:
    with _baglanti(conn) as conn:
        row = conn.execute("SELECT * FROM kategoriler WHERE ad = ?", (ad,)).fetchone()
    return dict(row) if row else None


def kategori_adi_var_mi(ad: str) -> bool:
    """Aynı isimde (Türkçe büyük/küçük harf duyarsız) kategori var mı kontrol eder."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM kategoriler WHERE TR_LOWER(ad) = TR_LOWER(?)", (ad,)
        ).fetchone()
    return row is not None


def kategori_getir(kategori_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM kategoriler WHERE id = ?", (kategori_id,)
        ).fetchone()
    return dict(row) if row else None


def kategori_urun_sayisi(kategori_id: int) -> int:
    """Kategoriye bağlı aktif ürün sayısı."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE kategori_id = ? AND aktif = 1",
            (kategori_id,),
        ).fetchone()[0]


def kategori_sil(kategori_id: int) -> None:
    with get_connection() as conn:
        # Pasif (silinmiş) ürünlerin kategori bağı koparılır; geçmişleri kalır.
        conn.execute(
            "UPDATE urunler SET kategori_id = NULL WHERE kategori_id = ? AND aktif = 0",
            (kategori_id,),
        )
        conn.execute("DELETE FROM kategoriler WHERE id = ?", (kategori_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Ürünler
# ─────────────────────────────────────────────────────────────────────────────

def urun_ekle(u: Urun, conn: Optional[sqlite3.Connection] = None) -> int:
    with _baglanti(conn) as conn:
        cur = conn.execute(
            """INSERT INTO urunler (ad, kategori_id, fiyat_kurus, stok_miktari, kritik_esik)
               VALUES (?, ?, ?, ?, ?)""",
            (u.ad, u.kategori_id, u.fiyat_kurus, u.stok_miktari, u.kritik_esik),
        )
        return cur.lastrowid


def urunleri_getir(kategori_id: Optional[int] = None) -> list[dict]:
    with get_connection() as conn:
        if kategori_id:
            rows = conn.execute(
                f"""SELECT {_URUN_SUTUNLARI}, k.ad AS kategori_adi
                   FROM urunler u
                   LEFT JOIN kategoriler k ON u.kategori_id = k.id
                   WHERE u.aktif = 1 AND u.kategori_id = ?
                   ORDER BY u.ad""",
                (kategori_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT {_URUN_SUTUNLARI}, k.ad AS kategori_adi
                   FROM urunler u
                   LEFT JOIN kategoriler k ON u.kategori_id = k.id
                   WHERE u.aktif = 1
                   ORDER BY u.ad"""
            ).fetchall()
    return [dict(r) for r in rows]


def urun_getir(urun_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            f"""SELECT {_URUN_SUTUNLARI}, k.ad AS kategori_adi
               FROM urunler u
               LEFT JOIN kategoriler k ON u.kategori_id = k.id
               WHERE u.id = ? AND u.aktif = 1""",
            (urun_id,),
        ).fetchone()
    return dict(row) if row else None


def urun_guncelle(u: Urun) -> None:
    """Ürün bilgilerini günceller. Stok burada değişmez; yalnızca hareketlerle değişir."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE urunler
               SET ad=?, kategori_id=?, fiyat_kurus=?, kritik_esik=?
               WHERE id=? AND aktif=1""",
            (u.ad, u.kategori_id, u.fiyat_kurus, u.kritik_esik, u.id),
        )


def urun_sil(urun_id: int) -> None:
    """Ürünü pasife alır (soft delete); stok hareketleri denetim için saklanır."""
    with get_connection() as conn:
        conn.execute("UPDATE urunler SET aktif = 0 WHERE id = ?", (urun_id,))


def urun_sayisi(conn: Optional[sqlite3.Connection] = None) -> int:
    with _baglanti(conn) as conn:
        return conn.execute("SELECT COUNT(*) FROM urunler WHERE aktif = 1").fetchone()[0]


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

def stok_hareketi_uygula(
    urun_id: int,
    tur: str,
    miktar: int,
    aciklama: str = "",
    tarih: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """
    Stoğu günceller ve hareketi kaydeder — ikisi tek transaction içinde.
    Stok, okuma-yazma yarışına düşmemek için SQL tarafında atomik olarak değişir.
    Ürün yoksa LookupError, stok yetmezse YetersizStokHatasi fırlatır.
    `conn` verilirse çağıranın transaction'ı içinde çalışır.
    """
    delta = miktar if tur == "giriş" else -miktar
    with (_baglanti(conn) if conn is not None else transaction()) as conn:
        cur = conn.execute(
            """UPDATE urunler SET stok_miktari = stok_miktari + ?
               WHERE id = ? AND aktif = 1 AND stok_miktari + ? >= 0""",
            (delta, urun_id, delta),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT stok_miktari FROM urunler WHERE id = ? AND aktif = 1", (urun_id,)
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


# Silinmiş ürünlerin hareketleri geçmişte görünmeye devam eder, adları işaretlenir.
_URUN_ADI_SQL = "CASE WHEN u.aktif = 1 THEN u.ad ELSE u.ad || ' (silindi)' END"


def hareketleri_getir(
    urun_id: Optional[int] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    tur: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    query = f"""
        SELECT sh.*, {_URUN_ADI_SQL} AS urun_adi
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
            f"""SELECT sh.*, {_URUN_ADI_SQL} AS urun_adi
               FROM stok_hareketleri sh
               JOIN urunler u ON sh.urun_id = u.id
               ORDER BY sh.tarih DESC LIMIT ?""",
            (n,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Sorguları
# ─────────────────────────────────────────────────────────────────────────────

def urun_adi_var_mi(
    ad: str,
    exclude_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Aynı isimde başka bir (aktif) ürün var mı kontrol eder."""
    with _baglanti(conn) as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT id FROM urunler WHERE aktif = 1 AND TR_LOWER(ad) = TR_LOWER(?) AND id != ?",
                (ad, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM urunler WHERE aktif = 1 AND TR_LOWER(ad) = TR_LOWER(?)", (ad,)
            ).fetchone()
    return row is not None


def kategorileri_urun_sayisiyla_getir() -> list[dict]:
    """Her kategorinin ürün sayısıyla birlikte listesini döner."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT k.*, COUNT(u.id) AS urun_sayisi
               FROM kategoriler k
               LEFT JOIN urunler u ON u.kategori_id = k.id AND u.aktif = 1
               GROUP BY k.id
               ORDER BY k.ad"""
        ).fetchall()
    return [dict(r) for r in rows]


def en_yuksek_degerli_urun() -> Optional[dict]:
    """Toplam stok değeri (fiyat × stok) en yüksek ürünü döner."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT ad, fiyat_kurus / 100.0 AS fiyat, stok_miktari,
                      (fiyat_kurus * stok_miktari) / 100.0 AS toplam_deger
               FROM urunler
               WHERE aktif = 1
               ORDER BY toplam_deger DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def kategori_dagilimi() -> list[dict]:
    """Kategori bazında ürün sayısı ve toplam stok değerini döner."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT k.ad AS kategori,
                      COUNT(u.id) AS urun_sayisi,
                      COALESCE(SUM(u.fiyat_kurus * u.stok_miktari), 0) / 100.0 AS toplam_deger
               FROM kategoriler k
               LEFT JOIN urunler u ON u.kategori_id = k.id AND u.aktif = 1
               GROUP BY k.id
               ORDER BY toplam_deger DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def _gun_oncesi(gun: int) -> str:
    """
    Hareket tarihleri yerel saatle yazıldığı için kesim tarihi de yerel saatle
    hesaplanır (SQLite'ın date('now') değeri UTC'dir).
    """
    return (datetime.now() - timedelta(days=gun)).strftime("%Y-%m-%d")


def dashboard_verisi_getir() -> dict:
    with get_connection() as conn:
        toplam_urun = conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE aktif = 1"
        ).fetchone()[0]
        toplam_stok = conn.execute(
            "SELECT SUM(stok_miktari) FROM urunler WHERE aktif = 1"
        ).fetchone()[0] or 0
        toplam_deger = conn.execute(
            "SELECT SUM(fiyat_kurus * stok_miktari) / 100.0 FROM urunler WHERE aktif = 1"
        ).fetchone()[0] or 0.0
        kritik_sayi = conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE aktif = 1 AND stok_miktari <= kritik_esik"
        ).fetchone()[0]

        # Kritik stok oranı için toplam ürün sayısı zaten var
        kritik_oran = round(kritik_sayi / toplam_urun * 100, 1) if toplam_urun else 0

        # En çok hareket gören ürün (son 30 gün)
        en_aktif = conn.execute(
            """SELECT u.ad, COUNT(sh.id) AS hareket_sayisi
               FROM stok_hareketleri sh
               JOIN urunler u ON sh.urun_id = u.id
               WHERE u.aktif = 1 AND sh.tarih >= ?
               GROUP BY sh.urun_id
               ORDER BY hareket_sayisi DESC LIMIT 1""",
            (_gun_oncesi(30),),
        ).fetchone()

        # Son 7 günde giriş/çıkış sayısı
        son7 = conn.execute(
            """SELECT tur, COUNT(*) AS sayi
               FROM stok_hareketleri
               WHERE tarih >= ?
               GROUP BY tur""",
            (_gun_oncesi(7),),
        ).fetchall()

        # Stoku tamamen biten ürün sayısı
        stok_biten = conn.execute(
            "SELECT COUNT(*) FROM urunler WHERE aktif = 1 AND stok_miktari = 0"
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
