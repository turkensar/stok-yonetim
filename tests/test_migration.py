import sqlite3

import database as db

ESKI_SEMA = """
CREATE TABLE kategoriler (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL UNIQUE,
                          aciklama TEXT DEFAULT '');
CREATE TABLE urunler (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL, kategori_id INTEGER,
                      fiyat REAL NOT NULL DEFAULT 0, stok_miktari INTEGER NOT NULL DEFAULT 0,
                      kritik_esik INTEGER NOT NULL DEFAULT 5,
                      FOREIGN KEY (kategori_id) REFERENCES kategoriler(id));
CREATE TABLE stok_hareketleri (id INTEGER PRIMARY KEY AUTOINCREMENT, urun_id INTEGER NOT NULL,
                               tur TEXT NOT NULL, miktar INTEGER NOT NULL, tarih TEXT NOT NULL,
                               aciklama TEXT DEFAULT '', islem_sonrasi_stok INTEGER NOT NULL,
                               FOREIGN KEY (urun_id) REFERENCES urunler(id));
INSERT INTO kategoriler (ad) VALUES ('Eski');
INSERT INTO urunler (ad, kategori_id, fiyat, stok_miktari, kritik_esik) VALUES ('Vida', 1, 2, 5, 1);
INSERT INTO stok_hareketleri (urun_id, tur, miktar, tarih, islem_sonrasi_stok)
       VALUES (1, 'giriş', 5, '2026-01-01 10:00:00', 5);
"""


def test_eski_veritabani_veri_kaybetmeden_tasinir(db_yolu):
    with sqlite3.connect(db_yolu) as conn:
        conn.executescript(ESKI_SEMA)

    db.init_db()
    db.init_db()  # ikinci çağrı bir şey yapmamalı

    with sqlite3.connect(db_yolu) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SEMA_SURUMU
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        sema = conn.execute("SELECT sql FROM sqlite_master WHERE name='urunler'").fetchone()[0]
        assert "CHECK" in sema and "aktif" in sema

    urun = db.urun_getir(1)
    assert (urun["ad"], urun["stok_miktari"], urun["kategori_adi"]) == ("Vida", 5, "Eski")
    assert len(db.hareketleri_getir()) == 1
