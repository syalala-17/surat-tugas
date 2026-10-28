"""
Dashboard Surat Tugas & Beban Kerja Pegawai (versi Streamlit sederhana)

Cara jalan:
    pip install -r requirements.txt
    streamlit run app.py

Alur program:
    input surat tugas -> disimpan ke database SQLite -> dihitung beban kerja
    -> ditampilkan di dashboard -> surat bisa diunduh sebagai PDF
"""
import sqlite3
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

DB_FILE = "surat_tugas.db"          # file database akan dibuat otomatis
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
AMBANG_TINGGI = 4                   # >= 4 penugasan per bulan dianggap tinggi


# =====================================================================
# 1. DATABASE
# =====================================================================
def jalankan(sql, params=()):
    """Untuk perintah yang MENGUBAH data (INSERT / UPDATE / DELETE)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.execute(sql, params)
    conn.commit()
    baru_id = cur.lastrowid
    conn.close()
    return baru_id


def ambil(sql, params=()):
    """Untuk perintah yang MEMBACA data (SELECT). Hasilnya DataFrame pandas."""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def buat_tabel():
    """Dipanggil sekali di awal. Membuat tabel kalau belum ada."""
    jalankan("""CREATE TABLE IF NOT EXISTS pegawai (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL, nip TEXT, jabatan TEXT)""")
    jalankan("""CREATE TABLE IF NOT EXISTS surat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nomor TEXT NOT NULL, tgl_surat TEXT, mulai TEXT, selesai TEXT,
        lokasi TEXT, dasar TEXT, untuk TEXT)""")
    # tabel penghubung: satu surat bisa untuk banyak pegawai
    jalankan("""CREATE TABLE IF NOT EXISTS surat_pegawai (
        surat_id INTEGER, pegawai_id INTEGER)""")
    jalankan("""CREATE TABLE IF NOT EXISTS pengaturan (
        kunci TEXT PRIMARY KEY, nilai TEXT)""")


PENGATURAN_AWAL = {
    "instansi": "Nama Instansi Anda", "alamat": "Alamat instansi, kota, telepon",
    "kota": "Kota", "ttd_nama": "Nama Pejabat",
    "ttd_jabatan": "Kepala Bagian", "ttd_nip": "NIP. 000000000000000000",
}


def baca_pengaturan():
    df = ambil("SELECT kunci, nilai FROM pengaturan")
    hasil = dict(PENGATURAN_AWAL)
    hasil.update(dict(zip(df["kunci"], df["nilai"])))
    return hasil


# =====================================================================
# 2. HITUNG BEBAN KERJA
# =====================================================================
def hitung_beban(tahun):
    """
    Hasil: tabel pegawai x 12 bulan.
    - penugasan = berapa surat yang menyentuh bulan itu
    - hari      = berapa hari kerja penugasan jatuh di bulan itu
    """
    df = ambil("""SELECT p.nama, s.id AS surat_id, s.mulai, s.selesai
                  FROM surat_pegawai sp
                  JOIN pegawai p ON p.id = sp.pegawai_id
                  JOIN surat s ON s.id = sp.surat_id""")
    pegawai = ambil("SELECT nama FROM pegawai ORDER BY nama")["nama"].tolist()

    catatan = {}   # kunci: (nama, bulan) -> {"surat": set(), "hari": 0}
    for _, r in df.iterrows():
        tgl = date.fromisoformat(r["mulai"])
        akhir = date.fromisoformat(r["selesai"])
        while tgl <= akhir:                      # telusuri tiap hari
            if tgl.year == tahun:
                c = catatan.setdefault((r["nama"], tgl.month),
                                       {"surat": set(), "hari": 0})
                c["surat"].add(r["surat_id"])
                c["hari"] += 1
            tgl += timedelta(days=1)

    def tabel(kunci):
        data = pd.DataFrame(0, index=pegawai, columns=range(1, 13))
        for (nama, bln), c in catatan.items():
            if nama in data.index:
                data.loc[nama, bln] = len(c["surat"]) if kunci == "penugasan" else c["hari"]
        data.columns = BULAN
        return data

    return tabel("penugasan"), tabel("hari")


# =====================================================================
# 3. BUAT PDF
# =====================================================================
def tgl_indo(iso):
    d = date.fromisoformat(iso)
    nama = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
            "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{d.day} {nama[d.month - 1]} {d.year}"


def buat_pdf(surat_id):
    s = ambil("SELECT * FROM surat WHERE id = ?", (surat_id,)).iloc[0]
    orang = ambil("""SELECT p.* FROM pegawai p
                     JOIN surat_pegawai sp ON sp.pegawai_id = p.id
                     WHERE sp.surat_id = ?""", (surat_id,))
    cfg = baca_pengaturan()

    pdf = FPDF(format="A4")
    pdf.set_margins(22, 18, 22)
    pdf.add_page()

    # kop surat
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 7, cfg["instansi"].upper(), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, cfg["alamat"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.line(22, pdf.get_y() + 1, 188, pdf.get_y() + 1)
    pdf.ln(8)

    # judul
    pdf.set_font("Helvetica", "BU", 13)
    pdf.cell(0, 7, "SURAT TUGAS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Nomor: {s['nomor']}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    if s["dasar"]:
        pdf.multi_cell(0, 5.5, f"Dasar: {s['dasar']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.cell(0, 6, "Memberi tugas kepada:", new_x="LMARGIN", new_y="NEXT")
    for i, (_, p) in enumerate(orang.iterrows(), start=1):
        pdf.cell(8, 5.5, f"{i}.")
        pdf.cell(0, 5.5, f"Nama      : {p['nama']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(8, 5.5, "")
        pdf.cell(0, 5.5, f"NIP         : {p['nip']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(8, 5.5, "")
        pdf.cell(0, 5.5, f"Jabatan  : {p['jabatan']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.multi_cell(0, 5.5, f"Untuk: {s['untuk']}", new_x="LMARGIN", new_y="NEXT")
    waktu = tgl_indo(s["mulai"])
    if s["selesai"] != s["mulai"]:
        waktu += " s.d. " + tgl_indo(s["selesai"])
    pdf.cell(0, 5.5, f"Waktu: {waktu}", new_x="LMARGIN", new_y="NEXT")
    if s["lokasi"]:
        pdf.cell(0, 5.5, f"Tempat: {s['lokasi']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.multi_cell(0, 5.5, "Demikian surat tugas ini dibuat untuk dilaksanakan "
                   "dengan penuh tanggung jawab.", new_x="LMARGIN", new_y="NEXT")

    # tanda tangan (di kanan)
    pdf.ln(8)
    pdf.set_x(118)
    pdf.cell(0, 5.5, f"{cfg['kota']}, {tgl_indo(s['tgl_surat'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(118)
    pdf.cell(0, 5.5, cfg["ttd_jabatan"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_x(118)
    pdf.set_font("Helvetica", "BU", 11)
    pdf.cell(0, 5.5, cfg["ttd_nama"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_x(118)
    pdf.cell(0, 5.5, cfg["ttd_nip"])

    return bytes(pdf.output())


# =====================================================================
# 4. HALAMAN-HALAMAN
# =====================================================================
def halaman_dashboard():
    st.header("Dashboard Beban Kerja")
    tahun = st.selectbox("Tahun", range(date.today().year - 2, date.today().year + 2),
                         index=2)

    # panel "pegawai dengan beban baru" (muncul setelah menyimpan surat)
    if "terakhir" in st.session_state:
        t = st.session_state["terakhir"]
        st.success(f"Surat {t['nomor']} tersimpan. Pegawai dengan beban kerja baru:")
        for x in t["daftar"]:
            tanda = " ⚠️ tinggi" if x["sesudah"] >= AMBANG_TINGGI else ""
            st.write(f"- **{x['nama']}**: {x['sebelum']} → {x['sesudah']} "
                     f"penugasan di bulan {x['bulan']}{tanda}")

    penugasan, hari = hitung_beban(tahun)
    if penugasan.empty:
        st.info("Belum ada pegawai. Tambahkan dulu di menu Pegawai.")
        return

    ukuran = st.radio("Tampilkan", ["Jumlah penugasan", "Jumlah hari"], horizontal=True)
    data = penugasan if ukuran == "Jumlah penugasan" else hari

    k1, k2, k3 = st.columns(3)
    k1.metric("Pegawai", len(data))
    k2.metric("Total penugasan", int(penugasan.values.sum()))
    k3.metric("Total hari tugas", int(hari.values.sum()))

    st.subheader("Heatmap pegawai × bulan")
    st.plotly_chart(px.imshow(data, text_auto=True, aspect="auto",
                              color_continuous_scale="Blues"),
                    use_container_width=True)

    st.subheader("Total per bulan")
    st.plotly_chart(px.bar(x=BULAN, y=data.sum().values,
                           labels={"x": "Bulan", "y": ukuran}),
                    use_container_width=True)

    with st.expander("Lihat tabel lengkap"):
        data = data.copy()
        data["Total"] = data.sum(axis=1)
        st.dataframe(data, use_container_width=True)


def halaman_buat():
    st.header("Buat Surat Tugas")
    pegawai = ambil("SELECT * FROM pegawai ORDER BY nama")
    if pegawai.empty:
        st.warning("Tambahkan pegawai dulu di menu Pegawai.")
        return

    jml = ambil("SELECT COUNT(*) AS n FROM surat")["n"][0] + 1
    with st.form("form_surat"):
        nomor = st.text_input("Nomor surat", f"{jml:03d}/ST/{date.today().year}")
        c1, c2, c3 = st.columns(3)
        tgl_surat = c1.date_input("Tanggal surat", date.today())
        mulai = c2.date_input("Mulai tugas", date.today())
        selesai = c3.date_input("Selesai tugas", date.today())
        lokasi = st.text_input("Tempat / lokasi")
        dasar = st.text_area("Dasar penugasan (opsional)")
        untuk = st.text_area("Untuk (uraian tugas)")
        pilih = st.multiselect("Pegawai yang ditugaskan", pegawai["nama"].tolist())
        kirim = st.form_submit_button("Simpan", type="primary")

    if not kirim:
        return
    if not (nomor and untuk and pilih):
        st.error("Nomor, uraian tugas, dan minimal satu pegawai wajib diisi.")
        return
    if selesai < mulai:
        st.error("Tanggal selesai tidak boleh sebelum tanggal mulai.")
        return

    ids = pegawai[pegawai["nama"].isin(pilih)]["id"].tolist()
    sebelum, _ = hitung_beban(mulai.year)          # beban SEBELUM surat ini

    surat_id = jalankan(
        "INSERT INTO surat (nomor,tgl_surat,mulai,selesai,lokasi,dasar,untuk) "
        "VALUES (?,?,?,?,?,?,?)",
        (nomor, tgl_surat.isoformat(), mulai.isoformat(), selesai.isoformat(),
         lokasi, dasar, untuk))
    for pid in ids:
        jalankan("INSERT INTO surat_pegawai VALUES (?,?)", (surat_id, pid))

    sesudah, _ = hitung_beban(mulai.year)          # beban SESUDAH surat ini
    bln = BULAN[mulai.month - 1]
    st.session_state["terakhir"] = {
        "nomor": nomor,
        "daftar": [{"nama": n, "bulan": bln,
                    "sebelum": int(sebelum.loc[n, bln]),
                    "sesudah": int(sesudah.loc[n, bln])} for n in pilih]}
    st.success("Tersimpan! Buka menu Dashboard untuk melihat beban kerja baru.")


def halaman_daftar():
    st.header("Daftar Surat Tugas")
    surat = ambil("SELECT * FROM surat ORDER BY id DESC")
    if surat.empty:
        st.info("Belum ada surat tugas.")
        return
    for _, s in surat.iterrows():
        nama = ambil("""SELECT p.nama FROM pegawai p
                        JOIN surat_pegawai sp ON sp.pegawai_id = p.id
                        WHERE sp.surat_id = ?""", (int(s["id"]),))["nama"].tolist()
        with st.container(border=True):
            st.markdown(f"**{s['nomor']}** · {tgl_indo(s['mulai'])}")
            st.caption(f"{s['untuk']}  \nPegawai: {', '.join(nama)}")
            a, b, _ = st.columns([1, 1, 4])
            a.download_button("⬇ PDF", buat_pdf(int(s["id"])),
                              file_name=f"Surat-Tugas-{s['id']}.pdf",
                              mime="application/pdf", key=f"pdf{s['id']}")
            if b.button("Hapus", key=f"del{s['id']}"):
                jalankan("DELETE FROM surat_pegawai WHERE surat_id=?", (int(s["id"]),))
                jalankan("DELETE FROM surat WHERE id=?", (int(s["id"]),))
                st.session_state.pop("terakhir", None)
                st.rerun()


def halaman_pegawai():
    st.header("Pegawai & Pengaturan")
    with st.form("tambah_pegawai", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nama, nip, jab = c1.text_input("Nama"), c2.text_input("NIP"), c3.text_input("Jabatan")
        if st.form_submit_button("Tambah pegawai") and nama:
            jalankan("INSERT INTO pegawai (nama,nip,jabatan) VALUES (?,?,?)", (nama, nip, jab))
            st.rerun()

    pegawai = ambil("SELECT id, nama, nip, jabatan FROM pegawai ORDER BY nama")
    st.dataframe(pegawai, hide_index=True, use_container_width=True)
    if not pegawai.empty:
        hapus = st.selectbox("Hapus pegawai", pegawai["nama"])
        if st.button("Hapus"):
            pid = int(pegawai[pegawai["nama"] == hapus]["id"].iloc[0])
            jalankan("DELETE FROM surat_pegawai WHERE pegawai_id=?", (pid,))
            jalankan("DELETE FROM pegawai WHERE id=?", (pid,))
            st.rerun()

    st.subheader("Kop & penandatangan (dipakai di PDF)")
    cfg = baca_pengaturan()
    label = {"instansi": "Nama instansi", "alamat": "Alamat", "kota": "Kota",
             "ttd_nama": "Nama penandatangan", "ttd_jabatan": "Jabatan",
             "ttd_nip": "NIP"}
    with st.form("pengaturan"):
        baru = {k: st.text_input(v, cfg[k]) for k, v in label.items()}
        if st.form_submit_button("Simpan pengaturan"):
            for k, v in baru.items():
                jalankan("INSERT OR REPLACE INTO pengaturan VALUES (?,?)", (k, v))
            st.success("Pengaturan tersimpan.")


# =====================================================================
# 5. PROGRAM UTAMA
# =====================================================================
st.set_page_config(page_title="Surat Tugas", page_icon="📋", layout="wide")
buat_tabel()

menu = st.sidebar.radio("Menu", ["Dashboard", "Buat Surat Tugas",
                                 "Daftar Surat", "Pegawai"])
{"Dashboard": halaman_dashboard, "Buat Surat Tugas": halaman_buat,
 "Daftar Surat": halaman_daftar, "Pegawai": halaman_pegawai}[menu]()
