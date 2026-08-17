import ast
import os
import random
import re
import sqlite3
import subprocess
import tempfile
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# WAJIB ADA: Secret Key untuk enkripsi token keamanan
app.config['SECRET_KEY'] = '7701d856f8d350f1ce581d95aba1f1029c8ed0cc76d1399b795ef84ac8106ab3'

# Mengaktifkan proteksi CSRF secara global ke seluruh aplikasi
csrf = CSRFProtect(app)

DB_PATH = "rumah_koding.db"


# ==========================================
# 1. INISIALISASI DATABASE & TABEL AWAL
# ==========================================
def init_db():
    """Membuat tabel database SQLite jika belum ada dan membuat akun admin default."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabel Pengguna (Users)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'student'
        )
    """)

    # Tabel Materi Belajar (Materi Reguler)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bahasa TEXT NOT NULL,
            modul_ke INTEGER NOT NULL,
            judul TEXT NOT NULL,
            penjelasan TEXT NOT NULL,
            instruksi TEXT NOT NULL,
            kode_awal TEXT NOT NULL,
            jawaban_benar TEXT NOT NULL,
            next_id INTEGER
        )
    """)

    # Tabel Progres Belajar Pengguna (User Progress)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            materi_id INTEGER NOT NULL,
            status TEXT DEFAULT 'sedang_belajar',
            UNIQUE(user_id, materi_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(materi_id) REFERENCES materi(id)
        )
    """)

    # Cek apakah akun admin sudah ada, jika belum buat otomatis
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash("admin123")
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", hashed_password, "admin"),
        )

    conn.commit()
    conn.close()


# Jalankan inisialisasi database saat aplikasi pertama kali dijalankan
init_db()


# ==========================================
# 2. ROUTE UTAMA & AUTENTIKASI (AUTH)
# ==========================================
@app.route("/")
def index():
    """Halaman Beranda (Landing Page)."""
    return render_template("index.html")


@app.route("/profil")
def profil():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    cursor.execute("SELECT DISTINCT LOWER(bahasa) as bahasa FROM materi")
    langs = [row["bahasa"] for row in cursor.fetchall()]

    progress_data = {}
    for lang in langs:
        cursor.execute("SELECT COUNT(*) FROM materi WHERE LOWER(bahasa) = ?", (lang,))
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT m.id) FROM user_progress up
            JOIN materi m ON up.materi_id = m.id
            WHERE up.user_id = ? AND LOWER(m.bahasa) = ? AND up.status = 'selesai'
        """,
            (user_id, lang),
        )
        completed = cursor.fetchone()[0]

        pct = int((completed / total * 100) if total > 0 else 0)
        progress_data[lang] = pct

    conn.close()
    return render_template("profile.html", user=user, progress_data=progress_data)


@app.route("/profil/update", methods=["POST"])
def update_profil():
    """Logika untuk memperbarui username atau password pengguna."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    new_username = request.form.get("username")
    new_password = request.form.get("password")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        if new_password:
            hashed_pw = generate_password_hash(new_password)
            cursor.execute(
                "UPDATE users SET username = ?, password = ? WHERE id = ?",
                (new_username, hashed_pw, user_id),
            )
        else:
            cursor.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (new_username, user_id),
            )

        conn.commit()
        session["username"] = new_username
        flash("Profil berhasil diperbarui!", "success")
    except sqlite3.IntegrityError:
        flash("Username tersebut sudah digunakan oleh akun lain!", "error")
    finally:
        conn.close()

    return redirect(url_for("profil"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        raw_password = request.form.get("password")

        with sqlite3.connect("rumah_koding.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            user = cursor.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

        if user and check_password_hash(user["password"], raw_password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            flash("Berhasil masuk ke akun!", "success")
            return redirect(url_for("index"))
        else:
            flash("Username atau password salah!", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Halaman Registrasi Akun Siswa Baru dengan Math CAPTCHA."""
    if request.method == "POST":
        username = request.form.get("username")
        raw_password = request.form.get("password")
        user_captcha = request.form.get("captcha")

        expected_captcha = session.get("captcha_answer")
        if not user_captcha or int(user_captcha) != expected_captcha:
            flash("Verifikasi CAPTCHA salah! Silakan coba lagi.", "error")
            return redirect(url_for("register"))

        session.pop("captcha_answer", None)

        if not username or not raw_password:
            flash("Username dan password wajib diisi!", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(raw_password)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hashed_password, "student"),
            )
            conn.commit()
            flash("Registrasi berhasil! Silakan masuk.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username tersebut sudah digunakan oleh akun lain!", "error")
        finally:
            conn.close()

    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    session["captcha_answer"] = num1 + num2
    captcha_question = f"{num1} + {num2}"

    return render_template("register.html", captcha_question=captcha_question)


@app.route("/logout")
def logout():
    """Keluar dari sesi (Logout)."""
    session.clear()
    return redirect(url_for("index"))


# ==========================================
# 3. MODUL BELAJAR & KATALOG (REGULER & AUTOMATION)
# ==========================================
@app.route("/belajar")
def pilih_bahasa():
    """Halaman Katalog Kursus Tunggal (Reguler & Web Automation Terpadu)."""
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    progress_data = {}

    # 1. Ambil Progres Bahasa Pemrograman Reguler
    cursor.execute("SELECT DISTINCT LOWER(bahasa) as bahasa FROM materi ORDER BY bahasa ASC")
    langs = [row["bahasa"] for row in cursor.fetchall()]

    for lang in langs:
        cursor.execute("SELECT COUNT(*) FROM materi WHERE LOWER(bahasa) = ?", (lang,))
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT m.id) FROM user_progress up
            JOIN materi m ON up.materi_id = m.id
            WHERE up.user_id = ? AND LOWER(m.bahasa) = ? AND up.status = 'selesai'
        """,
            (user_id, lang),
        )
        completed = cursor.fetchone()[0]

        pct = int((completed / total * 100) if total > 0 else 0)

        # Mencari modul pertama yang belum selesai untuk rute tombol 'Lanjutkan'
        cursor.execute(
            """
            SELECT m.modul_ke FROM materi m
            LEFT JOIN user_progress up ON m.id = up.materi_id AND up.user_id = ?
            WHERE LOWER(m.bahasa) = ? AND (up.status IS NULL OR up.status != 'selesai')
            ORDER BY m.modul_ke ASC LIMIT 1
        """,
            (user_id, lang),
        )
        modul_target = cursor.fetchone()
        modul_ke = modul_target["modul_ke"] if modul_target else 1

        progress_data[lang] = {
            "total": total,
            "completed": completed,
            "pct": pct,
            "url": url_for("tampilkan_materi", bahasa=lang, modul_ke=modul_ke),
        }

    # 2. Ambil Progres Jalur Web Automation
    cursor.execute("SELECT COUNT(*) FROM automation_materi")
    total_auto = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(DISTINCT m.id) FROM automation_progress up
        JOIN automation_materi m ON up.materi_id = m.id
        WHERE up.user_id = ? AND up.status = 'selesai'
    """,
        (user_id,),
    )
    completed_auto = cursor.fetchone()[0]

    pct_auto = int((completed_auto / total_auto * 100) if total_auto > 0 else 0)
    progress_data["web automation"] = {
        "total": total_auto,
        "completed": completed_auto,
        "pct": pct_auto,
        "url": url_for("automation_lanjut"),
    }

    conn.close()
    return render_template("catalog.html", progress_data=progress_data)


@app.route("/automation/lanjut")
def automation_lanjut():
    """Mengarahkan siswa ke modul otomasi pertama yang belum selesai."""
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT m.modul_ke 
        FROM automation_materi m
        LEFT JOIN automation_progress up ON m.id = up.materi_id AND up.user_id = ?
        WHERE up.status IS NULL OR up.status != 'selesai'
        ORDER BY m.modul_ke ASC
        LIMIT 1
    """,
        (user_id,),
    )
    modul = cursor.fetchone()

    if not modul:
        cursor.execute("SELECT modul_ke FROM automation_materi ORDER BY modul_ke DESC LIMIT 1")
        modul = cursor.fetchone()

    conn.close()

    if modul:
        return redirect(url_for("automation_lesson", modul_ke=modul["modul_ke"]))
    else:
        return redirect(url_for("pilih_bahasa"))


@app.route("/belajar/<bahasa>/<int:modul_ke>")
def tampilkan_materi(bahasa, modul_ke):
    """Menampilkan halaman ruang belajar reguler berdasarkan bahasa dan nomor modul."""
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM materi WHERE LOWER(bahasa) = LOWER(?) AND modul_ke = ?",
        (bahasa, modul_ke),
    )
    materi = cursor.fetchone()

    if not materi:
        conn.close()
        return "Materi tidak ditemukan!", 404

    materi_id = materi["id"]

    cursor.execute(
        "SELECT id FROM user_progress WHERE user_id = ? AND materi_id = ?",
        (user_id, materi_id),
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user_progress (user_id, materi_id, status) VALUES (?, ?, 'sedang_belajar')",
            (user_id, materi_id),
        )
        conn.commit()

    cursor.execute(
        """
        SELECT m.id, m.judul, m.modul_ke, 
               COALESCE(up.status, 'belum') as status
        FROM materi m
        LEFT JOIN user_progress up ON m.id = up.materi_id AND up.user_id = ?
        WHERE LOWER(m.bahasa) = LOWER(?)
        ORDER BY m.modul_ke ASC
    """,
        (user_id, bahasa),
    )
    daftar_materi = cursor.fetchall()

    cursor.execute(
        """
        SELECT modul_ke FROM materi 
        WHERE LOWER(bahasa) = LOWER(?) AND CAST(modul_ke AS INTEGER) > ? 
        ORDER BY CAST(modul_ke AS INTEGER) ASC LIMIT 1
    """,
        (bahasa, modul_ke),
    )
    next_materi = cursor.fetchone()
    next_modul_ke = next_materi["modul_ke"] if next_materi else None

    conn.close()

    return render_template(
        "lesson.html",
        materi=materi,
        bahasa=bahasa,
        modul_ke=modul_ke,
        daftar_materi=daftar_materi,
        next_modul_ke=next_modul_ke,
    )


@app.route("/belajar/jalankan", methods=["POST"])
def jalankan_kode():
    """Endpoint AJAX untuk mengeksekusi kode Python atau JavaScript siswa."""
    if "user_id" not in session:
        return jsonify({"status": "error", "pesan": "Unauthorized"})

    user_id = session["user_id"]
    data = request.get_json()
    kode_user = data.get("kode", "")
    materi_id = data.get("materi_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT bahasa, jawaban_benar FROM materi WHERE id = ?", (materi_id,))
    materi = cursor.fetchone()

    if not materi:
        conn.close()
        return jsonify({"status": "error", "pesan": "Modul tidak valid!"})

    bahasa = materi["bahasa"].lower()
    jawaban_benar = materi["jawaban_benar"].strip() if materi["jawaban_benar"] else ""

    # Validasi AST Keamanan Python
    if bahasa == "python":
        try:
            tree = ast.parse(kode_user)
            dangerous_modules = {
                "os",
                "sys",
                "subprocess",
                "shutil",
                "socket",
                "ctypes",
                "multiprocessing",
            }
            dangerous_funcs = {"eval", "exec", "__import__", "globals", "locals"}

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod_name = alias.name.split(".")[0]
                        if mod_name in dangerous_modules:
                            conn.close()
                            return jsonify({
                                "status": "error",
                                "pesan": f"⚠️ Keamanan Ditolak: Modul '{mod_name}' dilarang demi keselamatan server.",
                            })
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        mod_name = node.module.split(".")[0]
                        if mod_name in dangerous_modules:
                            conn.close()
                            return jsonify({
                                "status": "error",
                                "pesan": f"⚠️ Keamanan Ditolak: Modul '{mod_name}' dilarang demi keselamatan server.",
                            })
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in dangerous_funcs:
                        conn.close()
                        return jsonify({
                            "status": "error",
                            "pesan": f"⚠️ Keamanan Ditolak: Pemanggilan fungsi '{node.func.id}' tidak diizinkan.",
                        })
        except SyntaxError:
            pass

    elif bahasa == "javascript":
        dangerous_js = ["require('fs')", 'require("fs")', "child_process", "process.exit"]
        for d in dangerous_js:
            if d in kode_user:
                conn.close()
                return jsonify({
                    "status": "error",
                    "pesan": "⚠️ Keamanan Ditolak: Penggunaan fungsi/modul sistem tersebut dilarang.",
                })

    output_console = ""
    output_error = ""

    if bahasa == "python":
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
            temp_file.write(kode_user.encode("utf-8"))
            nama_file_temp = temp_file.name

        try:
            hasil = subprocess.run(
                ["python", nama_file_temp], capture_output=True, text=True, timeout=3
            )
            output_console = hasil.stdout
            output_error = hasil.stderr
        except subprocess.TimeoutExpired:
            output_error = "Timeout: Eksekusi kode terlalu lama (maksimal 3 detik)."
        finally:
            if os.path.exists(nama_file_temp):
                os.remove(nama_file_temp)

    elif bahasa == "javascript":
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as temp_file:
            temp_file.write(kode_user.encode("utf-8"))
            nama_file_temp = temp_file.name

        try:
            hasil = subprocess.run(
                ["node", nama_file_temp], capture_output=True, text=True, timeout=3
            )
            output_console = hasil.stdout
            output_error = hasil.stderr
        except subprocess.TimeoutExpired:
            output_error = "Timeout: Eksekusi kode terlalu lama (maksimal 3 detik)."
        finally:
            if os.path.exists(nama_file_temp):
                os.remove(nama_file_temp)
    else:
        output_error = f"Eksekusi otomatis untuk bahasa '{bahasa}' belum aktif."

    if output_error:
        conn.close()
        return jsonify({"status": "error", "pesan": output_error})

    def normalize_text(text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    normalized_output = normalize_text(output_console)
    normalized_jawaban = normalize_text(jawaban_benar)

    is_correct = normalized_output == normalized_jawaban

    if is_correct:
        cursor.execute(
            """
            INSERT INTO user_progress (user_id, materi_id, status) 
            VALUES (?, ?, 'selesai')
            ON CONFLICT(user_id, materi_id) DO UPDATE SET status = 'selesai'
        """,
            (user_id, materi_id),
        )
        conn.commit()

    conn.close()
    return jsonify({"status": "sukses", "pesan": output_console, "benar": is_correct})


# ==========================================
# 4. DASHBOARD ADMIN (STUDIO ADMIN)
# ==========================================
@app.route("/admin", defaults={"materi_id": None}, methods=["GET", "POST"])
@app.route("/admin/<int:materi_id>", methods=["GET", "POST"])
def admin_dashboard(materi_id):
    """Panel Studio Admin untuk mengelola modul materi."""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        bahasa = request.form.get("bahasa").lower()
        modul_ke = request.form.get("modul_ke")
        judul = request.form.get("judul")
        penjelasan = request.form.get("penjelasan")
        instruksi = request.form.get("instruksi")
        kode_awal = request.form.get("kode_awal")
        jawaban_benar = request.form.get("jawaban_benar")
        next_id = request.form.get("next_id") or None

        form_id = request.form.get("materi_id")

        if form_id:
            cursor.execute(
                """
                UPDATE materi 
                SET bahasa=?, modul_ke=?, judul=?, penjelasan=?, instruksi=?, kode_awal=?, jawaban_benar=?, next_id=?
                WHERE id=?
            """,
                (
                    bahasa,
                    modul_ke,
                    judul,
                    penjelasan,
                    instruksi,
                    kode_awal,
                    jawaban_benar,
                    next_id,
                    form_id,
                ),
            )
            materi_id = form_id
        else:
            cursor.execute(
                """
                INSERT INTO materi (bahasa, modul_ke, judul, penjelasan, instruksi, kode_awal, jawaban_benar, next_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    bahasa,
                    modul_ke,
                    judul,
                    penjelasan,
                    instruksi,
                    kode_awal,
                    jawaban_benar,
                    next_id,
                ),
            )
            conn.commit()
            cursor.execute("SELECT last_insert_rowid()")
            materi_id = cursor.fetchone()[0]

        conn.commit()
        conn.close()
        return redirect(url_for("admin_dashboard", materi_id=materi_id))

    cursor.execute("SELECT * FROM materi ORDER BY bahasa, modul_ke")
    daftar_materi = cursor.fetchall()

    materi = None
    if materi_id:
        cursor.execute("SELECT * FROM materi WHERE id = ?", (materi_id,))
        materi = cursor.fetchone()

    conn.close()
    return render_template("admin_studio.html", daftar_materi=daftar_materi, materi=materi)


@app.route("/admin/hapus/<int:materi_id>", methods=["GET", "POST"])
def admin_hapus_materi(materi_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM materi WHERE id = ?", (materi_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users")
def admin_users():
    """Halaman daftar siswa dengan fitur CRUD dan rekap progres (Reguler + Automation)."""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.username, 
               (
                   (SELECT COUNT(*) FROM user_progress up JOIN materi m ON up.materi_id = m.id WHERE up.user_id = u.id AND up.status = 'selesai')
                   + 
                   (SELECT COUNT(*) FROM automation_progress up_auto JOIN automation_materi m_auto ON up_auto.materi_id = m_auto.id WHERE up_auto.user_id = u.id AND up_auto.status = 'selesai')
               ) as modul_selesai,
               (
                   (SELECT COUNT(*) FROM materi) 
                   + 
                   (SELECT COUNT(*) FROM automation_materi)
               ) as total_modul
        FROM users u
        WHERE u.role = 'student'
        ORDER BY u.username ASC
    """)
    daftar_siswa = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", daftar_siswa=daftar_siswa)


@app.route("/admin/users/tambah", methods=["GET", "POST"])
def admin_tambah_siswa():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username")
        password = generate_password_hash(request.form.get("password"))

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, 'student')",
                    (username, password),
                )
                conn.commit()
            flash("Siswa berhasil ditambahkan!", "success")
        except sqlite3.IntegrityError:
            flash("Gagal menambah siswa! Username sudah digunakan.", "error")

        return redirect(url_for("admin_users"))
    return render_template("admin_user_edit.html", action="Tambah", user=None)


@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
def admin_edit_siswa(user_id):
    """Halaman edit data siswa dan kontrol progres modul mereka (Reguler + Automation)."""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        action_type = request.form.get("action_type")

        if action_type == "update_user":
            username = request.form.get("username")
            password = request.form.get("password")
            if password:
                cursor.execute(
                    "UPDATE users SET username=?, password=? WHERE id=?",
                    (username, generate_password_hash(password), user_id),
                )
            else:
                cursor.execute(
                    "UPDATE users SET username=? WHERE id=?",
                    (username, user_id),
                )
            conn.commit()
            flash("Data akun siswa berhasil diperbarui!", "success")

        elif action_type == "update_progress":
            materi_id = request.form.get("materi_id")
            new_status = request.form.get("status")

            cursor.execute("SELECT id FROM automation_materi WHERE id = ?", (materi_id,))
            is_automation = cursor.fetchone()

            if is_automation:
                progress_table = "automation_progress"
            else:
                progress_table = "user_progress"

            if new_status == "hapus":
                cursor.execute(
                    f"DELETE FROM {progress_table} WHERE user_id = ? AND materi_id = ?",
                    (user_id, materi_id),
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {progress_table} (user_id, materi_id, status) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, materi_id) DO UPDATE SET status = ?
                """,
                    (user_id, materi_id, new_status, new_status),
                )
            conn.commit()
            flash("Status modul siswa berhasil diubah!", "success")

        return redirect(url_for("admin_edit_siswa", user_id=user_id))

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    cursor.execute(
        """
        SELECT m.id, m.bahasa, m.modul_ke, m.judul,
               COALESCE(up.status, 'belum') as status
        FROM materi m
        LEFT JOIN user_progress up ON m.id = up.materi_id AND up.user_id = ?
        
        UNION ALL
        
        SELECT am.id, 'web automation' as bahasa, am.modul_ke, am.judul,
               COALESCE(up_auto.status, 'belum') as status
        FROM automation_materi am
        LEFT JOIN automation_progress up_auto ON am.id = up_auto.materi_id AND up_auto.user_id = ?
        
        ORDER BY bahasa, modul_ke ASC
    """,
        (user_id, user_id),
    )
    progres_modul = cursor.fetchall()

    conn.close()
    return render_template(
        "admin_user_edit.html", action="Edit", user=user, progres_modul=progres_modul
    )


@app.route("/admin/users/hapus/<int:user_id>")
def admin_hapus_siswa(user_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    cursor.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_users"))


# ==========================================
# 5. DASHBOARD SISWA & LEADERBOARD
# ==========================================
@app.route("/dashboard")
def student_dashboard():
    """Halaman Dashboard Siswa (Fokus pada Statistik & Ringkasan)."""
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM materi")
    total_reguler = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM automation_materi")
    total_auto = cursor.fetchone()[0]
    total_modul = total_reguler + total_auto

    cursor.execute(
        "SELECT COUNT(*) FROM user_progress WHERE user_id = ? AND status = 'selesai'",
        (user_id,),
    )
    selesai_reguler = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM automation_progress WHERE user_id = ? AND status = 'selesai'",
        (user_id,),
    )
    selesai_auto = cursor.fetchone()[0]
    total_selesai = selesai_reguler + selesai_auto

    overall_pct = int((total_selesai / total_modul * 100) if total_modul > 0 else 0)

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        total_modul=total_modul,
        total_selesai=total_selesai,
        overall_pct=overall_pct,
    )


@app.route("/leaderboard")
def leaderboard():
    """Halaman Papan Peringkat siswa."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.username, 
               COUNT(up.materi_id) as total_selesai
        FROM users u
        LEFT JOIN user_progress up ON u.id = up.user_id AND up.status = 'selesai'
        WHERE u.role = 'student'
        GROUP BY u.id, u.username
        ORDER BY total_selesai DESC
        LIMIT 10
    """)
    leaderboard_data = cursor.fetchall()
    conn.close()

    return render_template("leaderboard.html", leaderboard_data=leaderboard_data)


# ==========================================
# 6. INISIALISASI DATABASE & ROUTE WEB AUTOMATION (LAB)
# ==========================================
def init_automation_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_materi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modul_ke INTEGER NOT NULL,
            judul TEXT NOT NULL,
            penjelasan TEXT NOT NULL,
            instruksi TEXT NOT NULL,
            kode_awal TEXT NOT NULL,
            target_url TEXT NOT NULL,
            jawaban_benar TEXT NOT NULL,
            next_id INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            materi_id INTEGER NOT NULL,
            status TEXT DEFAULT 'sedang_belajar',
            UNIQUE(user_id, materi_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(materi_id) REFERENCES automation_materi(id)
        )
    """)

    conn.commit()
    conn.close()


init_automation_db()


@app.route("/automation/<int:modul_ke>")
def automation_lesson(modul_ke):
    """Ruang kerja (Workspace) interaktif untuk modul Web Automation."""
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM automation_materi WHERE modul_ke = ?", (modul_ke,))
    materi = cursor.fetchone()

    if not materi:
        conn.close()
        return "Modul Otomasi tidak ditemukan!", 404

    cursor.execute(
        "SELECT id, status FROM automation_progress WHERE user_id = ? AND materi_id = ?",
        (user_id, materi["id"]),
    )
    prog = cursor.fetchone()
    if not prog:
        cursor.execute(
            "INSERT INTO automation_progress (user_id, materi_id, status) VALUES (?, ?, 'sedang_belajar')",
            (user_id, materi["id"]),
        )
        conn.commit()
        current_status = "sedang_belajar"
    else:
        current_status = prog["status"]

    cursor.execute(
        """
        SELECT m.id, m.judul, m.modul_ke, 
               COALESCE(up.status, 'belum') as status
        FROM automation_materi m
        LEFT JOIN automation_progress up ON m.id = up.materi_id AND up.user_id = ?
        ORDER BY m.modul_ke ASC
    """,
        (user_id,),
    )
    daftar_materi = cursor.fetchall()

    cursor.execute(
        """
        SELECT modul_ke FROM automation_materi 
        WHERE CAST(modul_ke AS INTEGER) > ? 
        ORDER BY CAST(modul_ke AS INTEGER) ASC LIMIT 1
    """,
        (modul_ke,),
    )
    next_materi = cursor.fetchone()
    next_modul_ke = next_materi["modul_ke"] if next_materi else None

    conn.close()
    return render_template(
        "automation_lesson.html",
        materi=materi,
        daftar_materi=daftar_materi,
        next_modul_ke=next_modul_ke,
        modul_ke=modul_ke,
        current_status=current_status,
    )


@app.route("/sandbox/form-latihan")
def sandbox_form_latihan():
    """Halaman web lokal target yang akan dimuat di dalam iframe siswa."""
    return render_template("sandbox/form_latihan.html")


@app.route("/sandbox/form-lanjutan")
def sandbox_form_lanjutan():
    """Halaman web lokal target kedua untuk latihan dropdown & checkbox."""
    return render_template("sandbox/form_lanjutan.html")


@app.route("/automation/jalankan", methods=["POST"])
def automation_jalankan():
    """Endpoint untuk mengeksekusi script Playwright siswa dan memvalidasi elemen."""
    if "user_id" not in session:
        return jsonify({"status": "error", "pesan": "Unauthorized"})

    user_id = session["user_id"]
    data = request.get_json()
    kode_siswa = data.get("kode", "")
    materi_id = data.get("materi_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM automation_materi WHERE id = ?", (materi_id,))
    materi = cursor.fetchone()
    conn.close()

    if not materi:
        return jsonify({"status": "error", "pesan": "Modul otomasi tidak valid!"})

    target_url = request.host_url.rstrip("/") + materi["target_url"]

    indented_code = "\n".join([
        "            " + line if line.strip() else line for line in kode_siswa.splitlines()
    ])

    # Tentukan logika validasi dinamis berdasarkan Modul Ke atau Target URL
    if int(materi["modul_ke"]) == 0:
        # Modul 0: Selalu lulus (Passed) untuk tujuan eksplorasi / pengenalan dasar
        test_validation_logic = """
            print("TEST_PASSED: Modul pengenalan selesai! Silakan lanjut ke modul berikutnya.")
        """
    elif "form-latihan" in materi["target_url"]:
        # Modul 1: Mengecek apakah input form terisi dengan benar
        test_validation_logic = """
            user_val = page.locator("#username-input").input_value()
            pass_val = page.locator("#password-input").input_value()
            if user_val != "" and pass_val != "":
                print("TEST_PASSED: Otomasi berhasil mengisi form dan elemen terverifikasi!")
            else:
                print("TEST_FAILED: Input form belum terisi dengan benar.")
        """
    else:
        # Modul 2 dan seterusnya: Mengecek kemunculan elemen pesan sukses (#welcome-message)
        test_validation_logic = """
            success_elem = page.locator("#welcome-message")
            if success_elem.is_visible():
                print("TEST_PASSED: Otomasi berhasil dan elemen terverifikasi!")
            else:
                print("TEST_FAILED: Elemen target sukses belum muncul atau aksi belum lengkap.")
        """

    wrapped_code = f"""
import asyncio
from playwright.sync_api import sync_playwright

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("{target_url}")
        
        try:
            # --- KODE YANG DITULIS OLEH SISWA ---
{indented_code}
            # ------------------------------------
            
            # --- TEST WRAPPER PENGUJIAN OTOMATIS ---
{test_validation_logic}
                
        except Exception as e:
            print(f"TEST_FAILED: Terjadi kesalahan runtime -> {{str(e)}}")
        finally:
            browser.close()

if __name__ == "__main__":
    run_test()
"""

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
        temp_file.write(wrapped_code.encode("utf-8"))
        nama_file_temp = temp_file.name

    output_console = ""
    output_error = ""

    try:
        hasil = subprocess.run(
            ["python", nama_file_temp], capture_output=True, text=True, timeout=10
        )
        output_console = hasil.stdout
        output_error = hasil.stderr
    except subprocess.TimeoutExpired:
        output_error = "Timeout: Eksekusi script otomasi terlalu lama (maksimal 10 detik)."
    finally:
        if os.path.exists(nama_file_temp):
            os.remove(nama_file_temp)

    if output_error:
        return jsonify({"status": "error", "pesan": output_error})

    is_success = "TEST_PASSED" in output_console

    if is_success:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO automation_progress (user_id, materi_id, status) 
            VALUES (?, ?, 'selesai')
            ON CONFLICT(user_id, materi_id) DO UPDATE SET status = 'selesai'
        """,
            (user_id, materi_id),
        )
        conn.commit()
        conn.close()

    return jsonify(
        {"status": "sukses", "pesan": output_console, "berhasil": is_success}
    )


@app.route("/admin/automation", defaults={"materi_id": None}, methods=["GET", "POST"])
@app.route("/admin/automation/<int:materi_id>", methods=["GET", "POST"])
def admin_automation_dashboard(materi_id):
    """Panel Admin khusus untuk membuat, mengedit, atau menghapus modul Web Automation."""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        modul_ke = request.form.get("modul_ke")
        judul = request.form.get("judul")
        penjelasan = request.form.get("penjelasan")
        instruksi = request.form.get("instruksi")
        kode_awal = request.form.get("kode_awal")
        target_url = request.form.get("target_url")
        jawaban_benar = request.form.get("jawaban_benar", "TEST_PASSED")

        form_id = request.form.get("materi_id")

        if form_id:
            cursor.execute(
                """
                UPDATE automation_materi 
                SET modul_ke=?, judul=?, penjelasan=?, instruksi=?, kode_awal=?, target_url=?, jawaban_benar=?
                WHERE id=?
            """,
                (
                    modul_ke,
                    judul,
                    penjelasan,
                    instruksi,
                    kode_awal,
                    target_url,
                    jawaban_benar,
                    form_id,
                ),
            )
            materi_id = form_id
        else:
            cursor.execute(
                """
                INSERT INTO automation_materi (modul_ke, judul, penjelasan, instruksi, kode_awal, target_url, jawaban_benar)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    modul_ke,
                    judul,
                    penjelasan,
                    instruksi,
                    kode_awal,
                    target_url,
                    jawaban_benar,
                ),
            )
            conn.commit()
            cursor.execute("SELECT last_insert_rowid()")
            materi_id = cursor.fetchone()[0]

        conn.commit()
        conn.close()
        return redirect(url_for("admin_automation_dashboard", materi_id=materi_id))

    cursor.execute("SELECT * FROM automation_materi ORDER BY modul_ke ASC")
    daftar_materi = cursor.fetchall()

    materi = None
    if materi_id:
        cursor.execute("SELECT * FROM automation_materi WHERE id = ?", (materi_id,))
        materi = cursor.fetchone()

    conn.close()
    return render_template(
        "admin_automation_studio.html", daftar_materi=daftar_materi, materi=materi
    )


@app.route("/admin/automation/hapus/<int:materi_id>", methods=["GET", "POST"])
def admin_hapus_automation(materi_id):
    """Fungsi untuk menghapus modul Web Automation tertentu oleh admin."""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM automation_materi WHERE id = ?", (materi_id,))
    cursor.execute("DELETE FROM automation_progress WHERE materi_id = ?", (materi_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_automation_dashboard"))


# ==========================================
# ERROR HANDLER & MAIN
# ==========================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template("error_404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)