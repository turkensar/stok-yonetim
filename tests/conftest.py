import pytest

import database as db
from services import StokServisi


@pytest.fixture
def db_yolu(tmp_path, monkeypatch):
    """Her test için boş, geçici bir SQLite veritabanı."""
    yol = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", yol)
    return yol


@pytest.fixture
def servis(db_yolu):
    db.init_db()
    return StokServisi()


@pytest.fixture
def kategori_id(servis):
    servis.kategori_ekle("Kırtasiye")
    return servis.kategorileri_getir()[0]["id"]


@pytest.fixture
def urun_id(servis, kategori_id):
    """Stoğu 10, kritik eşiği 3 olan bir ürün."""
    basari, _ = servis.urun_ekle("Kalem", 10.0, 10, 3, kategori_id)
    assert basari
    return servis.urunleri_getir()[0]["id"]
