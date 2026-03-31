"""
Akıllı Stok Yönetim Sistemi — Streamlit Arayüzü
"""

import pandas as pd
import streamlit as st

import database as db
from services import StokServisi

# ─────────────────────────────────────────────────────────────────────────────
# Başlangıç
# ─────────────────────────────────────────────────────────────────────────────

db.init_db()
servis = StokServisi()

st.set_page_config(
    page_title="Stok Yönetim Sistemi",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .kart {
        background: rgba(128,128,128,0.08);
        border-radius: 8px; padding: 14px 18px; margin-bottom: 10px;
    }
    .kart-baslik { font-weight: 700; font-size: 0.95rem; margin-bottom: 4px; }
    .yorum-satir {
        background: rgba(128,128,128,0.06);
        border-left: 3px solid rgba(128,128,128,0.3);
        border-radius: 4px; padding: 8px 14px; margin-bottom: 7px;
        font-size: 0.9rem;
    }
    .rozet-kirmizi { background:#dc3545; color:white; padding:2px 9px;
                     border-radius:12px; font-size:0.75rem; font-weight:600; }
    .rozet-turuncu { background:#fd7e14; color:white; padding:2px 9px;
                     border-radius:12px; font-size:0.75rem; font-weight:600; }
    .rozet-yesil   { background:#28a745; color:white; padding:2px 9px;
                     border-radius:12px; font-size:0.75rem; font-weight:600; }
    section[data-testid="stSidebar"] { min-width: 230px !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Format Yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def para_formatla(deger: float) -> str:
    """₺1.234.567,89 formatında para birimi döner."""
    s = f"{abs(deger):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if deger < 0 else ''}₺{s}"


def sayi_formatla(deger: int) -> str:
    """1.234 formatında sayı döner."""
    return f"{deger:,}".replace(",", ".")


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _bildir(basari: bool, mesaj: str) -> None:
    st.success(mesaj) if basari else st.error(mesaj)


def _urun_secenekleri() -> dict[int, str]:
    return {u["id"]: u["ad"] for u in servis.urunleri_getir()}


def _kategori_secenekleri() -> dict[int, str]:
    return {k["id"]: k["ad"] for k in servis.kategorileri_getir()}


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📦 Stok Yönetimi")
    st.divider()
    sayfa = st.radio(
        "Menü",
        ["📊 Dashboard", "🏷️ Kategoriler", "📦 Ürünler",
         "📋 Hareketler", "⚠️ Kritik Stok", "📈 Raporlama"],
        label_visibility="collapsed",
    )
    st.divider()
    kritik_liste = servis.kritik_stok_kontrol()
    if kritik_liste:
        st.markdown(
            f'<span class="rozet-kirmizi">⚠️ {len(kritik_liste)} kritik ürün</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<span class="rozet-yesil">✅ Stok normal</span>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1 — Dashboard
# ─────────────────────────────────────────────────────────────────────────────

if sayfa == "📊 Dashboard":
    st.title("📊 Dashboard")

    veri = servis.dashboard_verileri()

    # ── KPI Satırı ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Toplam Ürün",         sayi_formatla(veri["toplam_urun"]))
    c2.metric("Toplam Stok",         f"{sayi_formatla(veri['toplam_stok'])} adet")
    c3.metric("Toplam Stok Değeri",  para_formatla(veri["toplam_deger"]))
    c4.metric(
        "Kritik Stok",
        f"{veri['kritik_sayi']} ürün  (%{veri['kritik_oran']})",
        delta=f"-{veri['kritik_sayi']}" if veri["kritik_sayi"] else None,
        delta_color="inverse",
    )
    c5.metric("Son 7 Gün",
              f"{veri['son7_giris']} giriş / {veri['son7_cikis']} çıkış")

    st.divider()

    col_ana, col_yan = st.columns([3, 2])

    # ── Analiz Özeti ─────────────────────────────────────────────────────────
    with col_ana:
        st.markdown("#### 🧠 Analiz Özeti")
        yorumlar = servis.dashboard_analiz_yorumu(veri)
        for ikon, metin in yorumlar:
            st.markdown(
                f'<div class="yorum-satir">{ikon} &nbsp; {metin}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("#### 📋 Son Hareketler")
        son = servis.son_hareketler(10)
        if son:
            df_son = pd.DataFrame(son)[
                ["tarih", "urun_adi", "tur", "miktar", "islem_sonrasi_stok"]
            ]
            df_son.columns = ["Tarih", "Ürün", "Tür", "Miktar", "Sonraki Stok"]
            def _tur_renk(row):
                c = "color:#28a745;font-weight:600" if row["Tür"] == "giriş" else "color:#dc3545;font-weight:600"
                return ["", "", c, "", ""]
            st.dataframe(
                df_son.style.apply(_tur_renk, axis=1),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Henüz hareket kaydı yok.")

    # ── Sağ Panel ─────────────────────────────────────────────────────────────
    with col_yan:
        # Kategori dağılımı
        dagilim = db.kategori_dagilimi()
        if dagilim:
            st.markdown("#### 🏷️ Kategori Bazlı Dağılım")
            df_d = pd.DataFrame(dagilim)
            df_d["toplam_deger"] = df_d["toplam_deger"].apply(para_formatla)
            df_d.columns = ["Kategori", "Ürün Sayısı", "Toplam Değer"]
            st.dataframe(df_d, use_container_width=True, hide_index=True)

        # Kritik stok özeti
        st.markdown("#### ⚠️ Kritik Stok")
        if kritik_liste:
            df_k = pd.DataFrame(kritik_liste)[["ad", "stok_miktari", "kritik_esik"]]
            df_k.columns = ["Ürün", "Stok", "Eşik"]
            st.dataframe(df_k, use_container_width=True, hide_index=True)
        else:
            st.success("Kritik stok yok.")


# ─────────────────────────────────────────────────────────────────────────────
# 2 — Kategori Yönetimi
# ─────────────────────────────────────────────────────────────────────────────

elif sayfa == "🏷️ Kategoriler":
    st.title("🏷️ Kategori Yönetimi")

    with st.expander("➕ Yeni Kategori Ekle", expanded=True):
        with st.form("kat_form", clear_on_submit=True):
            ad       = st.text_input("Kategori Adı *")
            aciklama = st.text_input("Açıklama")
            if st.form_submit_button("Ekle", use_container_width=True, type="primary"):
                basari, mesaj = servis.kategori_ekle(ad, aciklama)
                _bildir(basari, mesaj)
                if basari:
                    st.rerun()

    st.divider()
    st.markdown("#### Mevcut Kategoriler")
    kategoriler = db.kategorileri_urun_sayisiyla_getir()

    if kategoriler:
        # Tablo başlığı
        h1, h2, h3, h4 = st.columns([3, 4, 1, 1])
        h1.markdown("**Kategori Adı**")
        h2.markdown("**Açıklama**")
        h3.markdown("**Ürün**")
        h4.markdown("**İşlem**")
        st.markdown("---")

        for k in kategoriler:
            c1, c2, c3, c4 = st.columns([3, 4, 1, 1])
            c1.markdown(f"**{k['ad']}**")
            c2.caption(k["aciklama"] or "—")
            c3.markdown(f"`{k['urun_sayisi']}`")
            if c4.button("🗑️", key=f"ksil_{k['id']}", help="Kategoriyi sil"):
                basari, mesaj = servis.kategori_sil(k["id"])
                _bildir(basari, mesaj)
                if basari:
                    st.rerun()
    else:
        st.info("Henüz kategori eklenmedi.")


# ─────────────────────────────────────────────────────────────────────────────
# 3 — Ürün Yönetimi
# ─────────────────────────────────────────────────────────────────────────────

elif sayfa == "📦 Ürünler":
    st.title("📦 Ürün Yönetimi")

    tab_liste, tab_ekle, tab_duzenle = st.tabs(
        ["📋 Ürün Listesi", "➕ Yeni Ürün", "✏️ Düzenle / Sil"]
    )
    kat_map = _kategori_secenekleri()

    # ── Ürün Listesi ──────────────────────────────────────────────────────────
    with tab_liste:
        col_ara, col_kat = st.columns([3, 2])
        arama      = col_ara.text_input("🔍 Ürün Ara", placeholder="Ürün adına göre...")
        filtre_kat = col_kat.selectbox(
            "Kategori Filtresi",
            options=[0] + list(kat_map.keys()),
            format_func=lambda x: "Tüm Kategoriler" if x == 0 else kat_map[x],
        )

        urunler = servis.urunleri_getir(kategori_id=filtre_kat if filtre_kat else None)
        if arama:
            urunler = [u for u in urunler if arama.lower() in u["ad"].lower()]

        if urunler:
            df = pd.DataFrame(urunler)
            df["toplam_deger"] = df["fiyat"] * df["stok_miktari"]
            df["durum"] = df.apply(
                lambda r: "🔴 Kritik" if r["stok_miktari"] <= r["kritik_esik"] else "🟢 Normal",
                axis=1,
            )
            goster = df[["ad", "kategori_adi", "fiyat", "stok_miktari",
                         "kritik_esik", "toplam_deger", "durum"]].copy()
            goster["fiyat"]       = goster["fiyat"].apply(para_formatla)
            goster["toplam_deger"] = goster["toplam_deger"].apply(para_formatla)
            goster.columns = ["Ürün Adı", "Kategori", "Birim Fiyat",
                              "Stok", "Kritik Eşik", "Toplam Değer", "Durum"]
            st.dataframe(goster, use_container_width=True, hide_index=True)
            st.caption(f"{len(urunler)} ürün listeleniyor.")
        else:
            st.info("Ürün bulunamadı.")

    # ── Yeni Ürün ─────────────────────────────────────────────────────────────
    with tab_ekle:
        if not kat_map:
            st.warning("Önce en az bir kategori eklemelisiniz.")
        else:
            with st.form("urun_ekle_form", clear_on_submit=True):
                ad = st.text_input("Ürün Adı *")
                c1, c2 = st.columns(2)
                fiyat        = c1.number_input("Birim Fiyat (₺) *", min_value=0.0, step=0.01, format="%.2f")
                stok_miktari = c2.number_input("Başlangıç Stok *",  min_value=0, step=1)
                c3, c4 = st.columns(2)
                kritik_esik = c3.number_input("Kritik Eşik", min_value=0, step=1, value=5)
                kat_id      = c4.selectbox("Kategori *", list(kat_map.keys()),
                                           format_func=lambda x: kat_map[x])
                if st.form_submit_button("Ürün Ekle", use_container_width=True, type="primary"):
                    basari, mesaj = servis.urun_ekle(
                        ad, float(fiyat), int(stok_miktari), int(kritik_esik), int(kat_id)
                    )
                    _bildir(basari, mesaj)
                    if basari:
                        st.rerun()

    # ── Düzenle / Sil ─────────────────────────────────────────────────────────
    with tab_duzenle:
        urun_map = _urun_secenekleri()
        if not urun_map:
            st.info("Henüz ürün yok.")
        else:
            secili_id = st.selectbox(
                "Düzenlenecek Ürün",
                list(urun_map.keys()),
                format_func=lambda x: urun_map[x],
            )
            urun = db.urun_getir(secili_id)

            if urun:
                with st.form("urun_guncelle_form"):
                    ad = st.text_input("Ürün Adı", value=urun["ad"])
                    c1, c2 = st.columns(2)
                    fiyat        = c1.number_input("Fiyat (₺)", value=float(urun["fiyat"]),
                                                   min_value=0.0, step=0.01, format="%.2f")
                    stok_miktari = c2.number_input("Stok", value=int(urun["stok_miktari"]),
                                                   min_value=0, step=1)
                    c3, c4 = st.columns(2)
                    kritik_esik = c3.number_input("Kritik Eşik", value=int(urun["kritik_esik"]),
                                                  min_value=0, step=1)
                    kat_keys = list(kat_map.keys())
                    kat_idx  = kat_keys.index(urun["kategori_id"]) if urun["kategori_id"] in kat_keys else 0
                    kat_secim = c4.selectbox("Kategori", kat_keys,
                                             index=kat_idx, format_func=lambda x: kat_map[x])

                    col_g, col_s = st.columns(2)
                    guncelle = col_g.form_submit_button("💾 Güncelle", use_container_width=True, type="primary")
                    sil_btn  = col_s.form_submit_button("🗑️ Sil",      use_container_width=True)

                    if guncelle:
                        # Aynı isimli başka ürün var mı kontrol et
                        if db.urun_adi_var_mi(ad, exclude_id=secili_id):
                            st.error(f"'{ad}' adında başka bir ürün zaten mevcut.")
                        else:
                            basari, mesaj = servis.urun_guncelle(
                                secili_id, ad, float(fiyat), int(stok_miktari),
                                int(kritik_esik), int(kat_secim),
                            )
                            _bildir(basari, mesaj)
                            if basari:
                                st.rerun()

                    if sil_btn:
                        st.session_state["sil_onayi_id"] = secili_id

            # Onay adımı — formun dışında
            if st.session_state.get("sil_onayi_id") == secili_id:
                st.warning(f"**'{urun['ad']}'** silinecek. Bu işlem geri alınamaz!")
                col_evet, col_vazgec = st.columns(2)
                if col_evet.button("✅ Evet, Sil", type="primary", use_container_width=True):
                    basari, mesaj = servis.urun_sil(secili_id)
                    _bildir(basari, mesaj)
                    st.session_state.pop("sil_onayi_id", None)
                    if basari:
                        st.rerun()
                if col_vazgec.button("❌ Vazgeç", use_container_width=True):
                    st.session_state.pop("sil_onayi_id", None)
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# 4 — Stok Hareketleri
# ─────────────────────────────────────────────────────────────────────────────

elif sayfa == "📋 Hareketler":
    st.title("📋 Stok Hareketleri")

    tab_giris, tab_cikis, tab_gecmis = st.tabs(
        ["📥 Stok Girişi", "📤 Stok Çıkışı", "📜 Geçmiş"]
    )
    urun_map = _urun_secenekleri()

    with tab_giris:
        if not urun_map:
            st.info("Henüz ürün yok.")
        else:
            with st.form("giris_form", clear_on_submit=True):
                uid      = st.selectbox("Ürün", list(urun_map.keys()),
                                        format_func=lambda x: urun_map[x])
                miktar   = st.number_input("Giriş Miktarı (adet)", min_value=1, step=1)
                aciklama = st.text_input("Açıklama", placeholder="Tedarikçi adı, sipariş no...")
                bilgi    = db.urun_getir(uid)
                if bilgi:
                    st.caption(f"Mevcut stok: **{sayi_formatla(bilgi['stok_miktari'])} adet**")
                if st.form_submit_button("Giriş Yap", use_container_width=True, type="primary"):
                    basari, mesaj = servis.stok_girisi_yap(uid, int(miktar), aciklama)
                    _bildir(basari, mesaj)
                    if basari:
                        st.rerun()

    with tab_cikis:
        if not urun_map:
            st.info("Henüz ürün yok.")
        else:
            with st.form("cikis_form", clear_on_submit=True):
                uid      = st.selectbox("Ürün", list(urun_map.keys()),
                                        format_func=lambda x: urun_map[x])
                miktar   = st.number_input("Çıkış Miktarı (adet)", min_value=1, step=1)
                aciklama = st.text_input("Açıklama", placeholder="Satış, fire, iade...")
                bilgi    = db.urun_getir(uid)
                if bilgi:
                    st.caption(
                        f"Mevcut stok: **{sayi_formatla(bilgi['stok_miktari'])} adet**  ·  "
                        f"Kritik eşik: **{bilgi['kritik_esik']} adet**"
                    )
                if st.form_submit_button("Çıkış Yap", use_container_width=True, type="primary"):
                    basari, mesaj = servis.stok_cikisi_yap(uid, int(miktar), aciklama)
                    _bildir(basari, mesaj)
                    if basari:
                        st.rerun()

    with tab_gecmis:
        st.markdown("#### Filtreler")
        f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
        filtre_urun = f1.selectbox(
            "Ürün",
            [0] + list(urun_map.keys()),
            format_func=lambda x: "Tüm Ürünler" if x == 0 else urun_map[x],
        )
        filtre_tur = f2.selectbox("Tür", ["Tümü", "giriş", "çıkış"])
        baslangic  = f3.date_input("Başlangıç", value=None)
        bitis      = f4.date_input("Bitiş",     value=None)
        limit      = f5.selectbox("Kayıt Sayısı", [10, 20, 50, 100, 0],
                                   format_func=lambda x: "Tümü" if x == 0 else str(x))

        hareketler = servis.hareket_gecmisi(
            urun_id=filtre_urun if filtre_urun else None,
            baslangic=str(baslangic) if baslangic else None,
            bitis=str(bitis) if bitis else None,
            tur=filtre_tur if filtre_tur != "Tümü" else None,
            limit=limit if limit else None,
        )

        if hareketler:
            df_h = pd.DataFrame(hareketler)[[
                "tarih", "urun_adi", "tur", "miktar", "islem_sonrasi_stok", "aciklama"
            ]]
            df_h.columns = ["Tarih", "Ürün", "Tür", "Miktar", "Sonraki Stok", "Açıklama"]
            def _tur_r(row):
                c = "color:#28a745;font-weight:600" if row["Tür"] == "giriş" else "color:#dc3545;font-weight:600"
                return ["", "", c, "", "", ""]
            st.dataframe(
                df_h.style.apply(_tur_r, axis=1),
                use_container_width=True, hide_index=True,
            )
            st.caption(f"{len(hareketler)} hareket kaydı listeleniyor.")
        else:
            st.info("Seçili kriterlere uygun hareket bulunamadı.")


# ─────────────────────────────────────────────────────────────────────────────
# 5 — Kritik Stok
# ─────────────────────────────────────────────────────────────────────────────

elif sayfa == "⚠️ Kritik Stok":
    st.title("⚠️ Kritik Stok Durumu")

    kritik = servis.kritik_stok_kontrol()

    if not kritik:
        st.success("✅ Şu an kritik stok seviyesinde ürün yok.")
    else:
        # Özet
        toplam_eksik_adet = sum(
            max(0, u["kritik_esik"] - u["stok_miktari"]) for u in kritik
        )
        toplam_eksik_maliyet = sum(
            max(0, u["kritik_esik"] - u["stok_miktari"]) * u["fiyat"] for u in kritik
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Kritik Ürün Sayısı", len(kritik))
        c2.metric("Toplam Eksik Adet",  sayi_formatla(toplam_eksik_adet))
        c3.metric("Min. Tedarik Maliyeti", para_formatla(toplam_eksik_maliyet))

        st.warning(
            f"**{len(kritik)} ürün** kritik eşiğin altında. "
            f"Kritik eşiğe ulaşmak için toplam **{sayi_formatla(toplam_eksik_adet)} adet** "
            f"tedarik gerekiyor (tahmini {para_formatla(toplam_eksik_maliyet)})."
        )
        st.divider()

        for u in kritik:
            eksik  = max(0, u["kritik_esik"] - u["stok_miktari"])
            maliyet = eksik * u["fiyat"]
            if u["stok_miktari"] == 0:
                rozet = '<span class="rozet-kirmizi">Stok Tükendi</span>'
            else:
                rozet = '<span class="rozet-turuncu">Kritik Seviye</span>'

            st.markdown(
                f'<div class="kart">'
                f'<div class="kart-baslik">{u["ad"]} &nbsp; {rozet}</div>'
                f'<small>'
                f'Kategori: <b>{u["kategori_adi"] or "—"}</b> &nbsp;|&nbsp; '
                f'Mevcut: <b>{sayi_formatla(u["stok_miktari"])} adet</b> &nbsp;|&nbsp; '
                f'Kritik Eşik: <b>{u["kritik_esik"]} adet</b> &nbsp;|&nbsp; '
                f'Eksik: <b>{sayi_formatla(eksik)} adet</b> &nbsp;|&nbsp; '
                f'Birim Fiyat: <b>{para_formatla(u["fiyat"])}</b> &nbsp;|&nbsp; '
                f'Tedarik Maliyeti: <b>{para_formatla(maliyet)}</b>'
                f'</small></div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 6 — Raporlama
# ─────────────────────────────────────────────────────────────────────────────

elif sayfa == "📈 Raporlama":
    st.title("📈 Raporlama")

    tab_csv, tab_demo = st.tabs(["📥 CSV İndir", "🧪 Demo Veri"])

    with tab_csv:
        st.markdown("#### Dışa Aktarma Seçenekleri")

        col1, col2 = st.columns(2)

        # Tüm ürünler
        with col1:
            st.markdown("**📦 Tüm Ürünler**")
            csv = servis.tum_urunler_csv_aktar()
            st.download_button(
                "⬇️ Tüm Ürünleri İndir",
                data=csv.encode("utf-8-sig") if csv else b"",
                file_name="tum_urunler.csv", mime="text/csv",
                use_container_width=True, disabled=not csv,
            )

        # Kritik stok
        with col2:
            st.markdown("**⚠️ Kritik Stok Raporu**")
            csv_k = servis.dusuk_stok_csv_aktar()
            st.download_button(
                "⬇️ Kritik Stoku İndir",
                data=csv_k.encode("utf-8-sig") if csv_k else b"",
                file_name="kritik_stok.csv", mime="text/csv",
                use_container_width=True, disabled=not csv_k,
            )

        col3, col4 = st.columns(2)

        # Tüm hareketler
        with col3:
            st.markdown("**📋 Tüm Stok Hareketleri**")
            csv_h = servis.tum_hareketler_csv_aktar()
            st.download_button(
                "⬇️ Hareketleri İndir",
                data=csv_h.encode("utf-8-sig") if csv_h else b"",
                file_name="stok_hareketleri.csv", mime="text/csv",
                use_container_width=True, disabled=not csv_h,
            )

        # Kategori raporu
        with col4:
            st.markdown("**🏷️ Kategori Raporu**")
            csv_d = servis.kategori_raporu_csv_aktar()
            st.download_button(
                "⬇️ Kategori Raporunu İndir",
                data=csv_d.encode("utf-8-sig") if csv_d else b"",
                file_name="kategori_raporu.csv", mime="text/csv",
                use_container_width=True, disabled=not csv_d,
            )

        # Önizleme
        st.divider()
        st.markdown("#### Ürün Listesi Önizleme")
        urunler = servis.urunleri_getir()
        if urunler:
            df = pd.DataFrame(urunler)
            df["toplam_deger"] = (df["fiyat"] * df["stok_miktari"]).apply(para_formatla)
            df["fiyat"]        = df["fiyat"].apply(para_formatla)
            df["durum"]        = df.apply(
                lambda r: "🔴 Kritik" if r["stok_miktari"] <= r["kritik_esik"] else "🟢 Normal",
                axis=1,
            )
            goster = df[["ad", "kategori_adi", "fiyat", "stok_miktari", "toplam_deger", "durum"]]
            goster.columns = ["Ürün", "Kategori", "Birim Fiyat", "Stok", "Toplam Değer", "Durum"]
            st.dataframe(goster, use_container_width=True, hide_index=True)

    with tab_demo:
        st.markdown("#### Demo Veri Yükle")
        st.info(
            "Bu sekme, uygulamayı test etmek ve ekran görüntüsü almak için "
            "gerçekçi örnek veri ekler.\n\n"
            "**3 kategori · 8 ürün · 15 stok hareketi · 2 kritik ürün**"
        )
        if st.button("🧪 Demo Verisi Yükle", type="primary", use_container_width=True):
            basari, mesaj = servis.demo_veri_yukle()
            _bildir(basari, mesaj)
            if basari:
                st.rerun()
