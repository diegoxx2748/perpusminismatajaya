import os
import sqlite3
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from collections import Counter

# --- 1. KONFIGURASI APLIKASI ---

app = Flask(__name__)

# Konfigurasi Secret Key (PENTING untuk session)
app.secret_key = 'kunci_rahasia_super_aman_12345'

# Konfigurasi Database SQLite
BASEDIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASEDIR, 'inventori.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{0}'.format(DB_PATH)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PER_PAGE'] = 10  # Jumlah buku per halaman (Pagination)

# Konfigurasi Folder Upload
UPLOAD_FOLDER = os.path.join(BASEDIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Pastikan folder 'uploads' ada

# Inisialisasi SQLAlchemy
db = SQLAlchemy(app)

# User Admin Sederhana (Username dan Password)
ADMIN_USERNAME = 'adminperpus'
ADMIN_PASSWORD = 'passwordaman'

# --- 2. MODEL DATABASE (SQLAlchemy) ---

class Buku(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    judul = db.Column(db.String(100), nullable=False)
    penulis = db.Column(db.String(100), nullable=False)
    tahun = db.Column(db.Integer)
    sinopsis = db.Column(db.Text)
    cover_path = db.Column(db.String(200)) # Path ke file cover

    def __repr__(self):
        return '<Buku {0}>'.format(self.judul)

# --- 3. FUNGSI UTILITY ---

def clean_sinopsis(sinopsis):
    """Menghilangkan karakter newline dan carriage return dari string untuk atribut HTML."""
    if sinopsis:
        return sinopsis.replace('\n', ' ').replace('\r', ' ')
    return ''

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 4. RUTE BARU: HOME, INVENTORI (index.html), CONTACT, etc. ---

@app.route('/')
def home():
    """Rute untuk Halaman Beranda."""
    total_buku = db.session.query(Buku).count()
    return render_template('home.html', 
                           total_buku=total_buku,
                           logged_in=session.get('logged_in', False))

@app.route('/contact')
def contact():
    """Rute untuk Halaman Kontak/Hub."""
    return render_template('contact.html', 
                           logged_in=session.get('logged_in', False))

@app.route('/inventori', methods=['GET', 'POST'])
def index():
    """Rute untuk Inventori Buku (menggunakan index.html)."""
    # 1. Tentukan halaman, sorting, dan order
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'ASC')
    
    # Tentukan kolom untuk sorting
    if sort_by == 'judul':
        query_column = Buku.judul
    elif sort_by == 'penulis':
        query_column = Buku.penulis
    elif sort_by == 'tahun':
        query_column = Buku.tahun
    else:
        query_column = Buku.id

    # Tentukan arah sorting
    if sort_order == 'DESC':
        query_sort = query_column.desc()
    else:
        query_sort = query_column.asc()
    
    # Ambil data buku dengan sorting dan pagination
    query = db.session.query(Buku).order_by(query_sort)
    paginated_buku = query.paginate(page=page, per_page=app.config['PER_PAGE'], error_out=False)

    # 2. Pembersihan Sinopsis untuk Template 
    daftar_buku_bersih = []
    for buku in paginated_buku.items:
        buku_dict = {
            'id': buku.id,
            'judul': buku.judul,
            'penulis': buku.penulis,
            'tahun': buku.tahun,
            'cover_path': buku.cover_path,
            'sinopsis': clean_sinopsis(buku.sinopsis)
        }
        daftar_buku_bersih.append(buku_dict)

    # 3. Hitung Total Buku
    total_buku = db.session.query(Buku).count()

    # 4. Handle POST request (Tambah Buku)
    if request.method == 'POST' and session.get('logged_in'):
        judul = request.form['judul']
        penulis = request.form['penulis']
        tahun = request.form.get('tahun')
        sinopsis = request.form.get('sinopsis')

        # Cek dan simpan cover
        filename = None
        if 'cover' in request.files:
            file = request.files['cover']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Simpan file dengan ID buku yang unik
                filename_unique = str(Buku.query.count() + 1) + '_' + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename_unique))
                filename = filename_unique
        
        # Konversi Tahun
        try:
            tahun_int = int(tahun) if tahun else None
        except ValueError:
            flash('Tahun harus berupa angka.', 'danger')
            return redirect(url_for('index'))

        new_buku = Buku(
            judul=judul, 
            penulis=penulis, 
            tahun=tahun_int,
            sinopsis=sinopsis,
            cover_path=filename
        )
        db.session.add(new_buku)
        db.session.commit()
        flash('Buku baru berhasil ditambahkan!', 'success')
        # Redirect ke rute inventori, yang di handle oleh fungsi index()
        return redirect(url_for('index')) 

    # Render template index.html
    return render_template('index.html', 
                           daftar_buku=daftar_buku_bersih, 
                           page=page, 
                           total_pages=paginated_buku.pages, 
                           total_buku=total_buku,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           logged_in=session.get('logged_in', False))

@app.route('/<int:id>/edit', methods=['POST'])
def edit_buku(id):
    if not session.get('logged_in'):
        flash('Akses ditolak. Silakan login sebagai Admin.', 'danger')
        return redirect(url_for('index'))

    buku = Buku.query.get_or_404(id)

    judul = request.form['judul']
    penulis = request.form['penulis']
    tahun = request.form.get('tahun')
    sinopsis = request.form.get('sinopsis')
    
    try:
        tahun_int = int(tahun) if tahun else None
    except ValueError:
        flash('Tahun harus berupa angka.', 'danger')
        return redirect(url_for('index'))

    buku.judul = judul
    buku.penulis = penulis
    buku.tahun = tahun_int
    buku.sinopsis = sinopsis 
    
    # Handle cover update
    if 'cover' in request.files:
        file = request.files['cover']
        if file and allowed_file(file.filename):
            # Hapus cover lama jika ada
            if buku.cover_path and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], buku.cover_path)):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], buku.cover_path))

            filename = secure_filename(file.filename)
            # Simpan file baru
            filename_unique = str(id) + '_' + filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename_unique))
            buku.cover_path = filename_unique

    db.session.commit()
    flash('Buku "{0}" berhasil diubah!'.format(buku.judul), 'success')
    return redirect(url_for('index'))

@app.route('/<int:id>/hapus', methods=['POST'])
def hapus_buku(id):
    if not session.get('logged_in'):
        flash('Akses ditolak. Silakan login sebagai Admin.', 'danger')
        return redirect(url_for('index'))
        
    buku = Buku.query.get_or_404(id)
    judul_buku = buku.judul
    
    # Hapus file cover
    if buku.cover_path:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], buku.cover_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(buku)
    db.session.commit()
    flash('Buku "{0}" berhasil dihapus!'.format(judul_buku), 'danger')
    return redirect(url_for('index'))

# --- 5. RUTE LOGIN DAN FILE UPLOAD ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Login berhasil! Mode Admin diaktifkan.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau Password salah.', 'danger')
            return redirect(url_for('login'))
            
    if session.get('logged_in'):
         flash('Anda sudah login sebagai Admin.', 'info')
         return redirect(url_for('index'))

    return render_template('login_admin.html', logged_in=session.get('logged_in', False))


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logout berhasil. Mode Admin dinonaktifkan.', 'info')
    return redirect(url_for('home'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- 6. RUTE API STATISTIK ---

@app.route('/api/statistik_tahun')
def statistik_tahun():
    # Ambil semua tahun terbit yang tidak Null
    tahun_list = db.session.query(Buku.tahun).filter(Buku.tahun.isnot(None)).all()
    
    # Flat the list dan hitung frekuensi
    tahun_data = [t[0] for t in tahun_list]
    tahun_counts = Counter(tahun_data)
    
    # Siapkan data untuk Chart.js (diurutkan)
    sorted_tahun = sorted(tahun_counts.keys())
    labels = [str(tahun) for tahun in sorted_tahun]
    data = [tahun_counts[tahun] for tahun in sorted_tahun]
    
    return json.dumps({'labels': labels, 'data': data})

# --- INISIALISASI DATABASE ---

def init_db():
    """Membuat tabel database jika belum ada dan mengisi data awal."""
    with app.app_context():
        db.create_all()
        
        data_buku_awal = [
            Buku(judul='Filosofi Teras', penulis='Henry Manampiring', tahun=2018, 
                 sinopsis='Panduan praktis filosofi Stoa untuk mengatasi emosi negatif dan mencapai ketenangan batin.', cover_path=None),
            Buku(judul='Bumi Manusia', penulis='Pramoedya Ananta Toer', tahun=1980, 
                 sinopsis='Kisah Minke, pemuda Jawa yang berjuang melawan ketidakadilan di masa penjajahan Belanda. Bagian pertama Tetralogi Buru.', cover_path=None),
            Buku(judul='Laskar Pelangi', penulis='Andrea Hirata', tahun=2005, 
                 sinopsis='Inspirasi dari kehidupan 10 anak desa di Belitung yang berjuang mengejar mimpi dan pendidikan di tengah keterbatasan.', cover_path=None),
            Buku(judul='Dilan 1990', penulis='Pidi Baiq', tahun=2014, 
                 sinopsis='Novel romantis tentang kisah cinta Milea dan Dilan, panglima tempur sekaligus ketua geng motor di Bandung tahun 90-an.', cover_path=None),
            Buku(judul='Atomic Habits', penulis='James Clear', tahun=2018, 
                 sinopsis='Metode mudah & terbukti untuk membangun kebiasaan baik dan menghilangkan kebiasaan buruk dengan perubahan kecil.', cover_path=None),
            Buku(judul='Sapiens: Sejarah Singkat Umat Manusia', penulis='Yuval Noah Harari', tahun=2011, 
                 sinopsis='Eksplorasi mendalam tentang sejarah Homo Sapiens, dari evolusi awal hingga menjadi dominan di planet ini.', cover_path=None),
            Buku(judul='Negeri 5 Menara', penulis='Ahmad Fuadi', tahun=2009, 
                 sinopsis='Kisah Alif yang merantau ke Pondok Madani dan bersama lima sahabatnya menemukan kekuatan mimpi dan persahabatan.', cover_path=None),
            Buku(judul='Cantik Itu Luka', penulis='Eka Kurniawan', tahun=2002, 
                 sinopsis='Novel realisme magis yang menceritakan kisah Dewi Ayu dan keluarganya di sebuah kota fiksi di Indonesia.', cover_path=None),
            Buku(judul='Rich Dad Poor Dad', penulis='Robert Kiyosaki', tahun=1997, 
                 sinopsis='Pelajari perbedaan pola pikir tentang uang antara orang kaya (Ayah Kaya) dan orang miskin (Ayah Miskin).', cover_path=None),
            Buku(judul='The Art of War', penulis='Sun Tzu', tahun=None, 
                 sinopsis='Teks militer kuno Tiongkok yang menawarkan strategi dan taktik yang relevan untuk bisnis dan kehidupan modern.', cover_path=None),
            Buku(judul='Gadis Pantai', penulis='Pramoedya Ananta Toer', tahun=1987, 
                 sinopsis='Kisah seorang gadis dari desa nelayan yang dipaksa menikah dengan bangsawan dan berjuang melawan tradisi feodal.', cover_path=None),
            Buku(judul='Pulang', penulis='Leila S. Chudori', tahun=2012, 
                 sinopsis='Novel tentang eksil politik Indonesia yang terdampar di Paris setelah peristiwa 1965, dan perjuangan mereka untuk kembali.', cover_path=None),
            Buku(judul='Laut Bercerita', penulis='Leila S. Chudori', tahun=2017, 
                 sinopsis='Menceritakan kisah para aktivis yang diculik pada masa Orde Baru dari sudut pandang seorang penyintas dan keluarganya.', cover_path=None)
        ]

        if not Buku.query.first():
             for buku in data_buku_awal:
                db.session.add(buku)
             db.session.commit()
             print("Database berhasil diinisialisasi dengan 13 data contoh.")
        else:
             print("Database sudah berisi data. Tidak ada inisialisasi tambahan dilakukan.")


# --- 7. MAIN RUNNER ---

if __name__ == '__main__':
    with app.app_context():
        # Pastikan login_admin.html ada
        templates_dir = os.path.join(BASEDIR, 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        login_path = os.path.join(templates_dir, 'login_admin.html')
        
        if not os.path.exists(login_path):
            with open(login_path, 'w') as f:
                f.write('''
                    <!DOCTYPE html><html lang="id"><head><title>Admin Login</title>
                    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
                    <style>
                        body { font-family: sans-serif; background-color: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                        .login-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 300px; }
                        h2 { text-align: center; color: #2ecc71; }
                        input[type="text"], input[type="password"] { width: 100%; padding: 10px; margin: 8px 0 15px 0; display: inline-block; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
                        button { background-color: #2ecc71; color: white; padding: 14px 20px; margin: 8px 0; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
                        button:hover { background-color: #27ae60; }
                    </style></head>
                    <body>
                        <div class="login-container">
                            <h2><i class="fas fa-user-shield"></i> Admin Login</h2>
                            <form method="POST" action="{{ url_for('login') }}">
                                <label for="username">Username:</label>
                                <input type="text" id="username" name="username" required>
                                <label for="password">Password:</label>
                                <input type="password" id="password" name="password" required>
                                <button type="submit">Login</button>
                                <p style="text-align: center; margin-top: 15px;"><a href="{{ url_for('index') }}" style="color: #3498db;">&larr; Kembali</a></p>
                            </form>
                        </div>
                    </body></html>
                ''')
            print("Dummy 'login_admin.html' dibuat di folder templates.")

        init_db()
        
    app.run(debug=True)