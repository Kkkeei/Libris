import os, sys, sqlite3, socket, threading, webbrowser, csv, shutil, re, unicodedata
from pathlib import Path
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from importador import parse_document, SUPPORTED_EXTENSIONS, FIELD_LABELS
try:
    import qrcode
    from PIL import Image, ImageTk
except ImportError:
    qrcode = ImageTk = None
try:
    from flask import Flask, request, jsonify, render_template_string
    from waitress import serve
except ImportError:
    Flask = None

PORT = 8765
def data_dir():
    p = (Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Libris") if sys.platform == "win32" else Path(os.getenv("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "libris"
    p.mkdir(parents=True, exist_ok=True)
    return p
DB = data_dir() / "libris.db"
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS books(
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT DEFAULT '',
            isbn TEXT, category TEXT DEFAULT '', column_code TEXT DEFAULT '',
            shelf_row INTEGER, accession_code TEXT UNIQUE, condition_status TEXT DEFAULT 'Bom',
            last_inventory_at TEXT
        );
        CREATE TABLE IF NOT EXISTS readers(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, registration TEXT UNIQUE,
            phone TEXT DEFAULT '', class_name TEXT DEFAULT '', reading_goal INTEGER DEFAULT 12
        );
        CREATE TABLE IF NOT EXISTS loans(
            id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
            reader_id INTEGER NOT NULL REFERENCES readers(id), loan_date TEXT NOT NULL,
            due_date TEXT NOT NULL, returned_at TEXT, renewals INTEGER DEFAULT 0, notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reservations(
            id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
            reader_id INTEGER NOT NULL REFERENCES readers(id), request_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Na fila', notified_at TEXT
        );
        CREATE TABLE IF NOT EXISTS inventory_scans(
            id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
            scanned_at TEXT NOT NULL, condition_status TEXT NOT NULL DEFAULT 'Bom'
        );
        CREATE TABLE IF NOT EXISTS activity_log(
            id INTEGER PRIMARY KEY, action TEXT NOT NULL, entity_type TEXT NOT NULL,
            entity_id INTEGER, description TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
    migrate_schema()

def migrate_schema():
    # Remove a antiga restrição UNIQUE do ISBN para permitir vários exemplares da mesma edição.
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("PRAGMA legacy_alter_table=ON")
    cols={row["name"] for row in c.execute("PRAGMA table_info(books)").fetchall()}
    unique_isbn=False
    for idx in c.execute("PRAGMA index_list(books)").fetchall():
        if idx["unique"]:
            idxcols=[r["name"] for r in c.execute("PRAGMA index_info('%s')" % idx["name"].replace("'","''")).fetchall()]
            if idxcols==["isbn"]:
                unique_isbn=True
                break
    if unique_isbn:
        c.execute("BEGIN IMMEDIATE")
        c.execute("ALTER TABLE books RENAME TO books_legacy_migration")
        c.execute("""CREATE TABLE books(
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT DEFAULT '',
            isbn TEXT, category TEXT DEFAULT '', column_code TEXT DEFAULT '',
            shelf_row INTEGER, accession_code TEXT UNIQUE, condition_status TEXT DEFAULT 'Bom',
            last_inventory_at TEXT
        )""")
        oldcols={row["name"] for row in c.execute("PRAGMA table_info(books_legacy_migration)").fetchall()}
        fields=["id","title","author","isbn","category","column_code","shelf_row","accession_code","condition_status","last_inventory_at"]
        common=[name for name in fields if name in oldcols]
        names=",".join(common)
        c.execute("INSERT INTO books (%s) SELECT %s FROM books_legacy_migration" % (names,names))
        c.execute("DROP TABLE books_legacy_migration")
        c.commit()
    c.execute("BEGIN IMMEDIATE")
    migrations={
        "books":{"column_code":"TEXT DEFAULT ''","shelf_row":"INTEGER","accession_code":"TEXT","condition_status":"TEXT DEFAULT 'Bom'","last_inventory_at":"TEXT"},
        "readers":{"class_name":"TEXT DEFAULT ''","reading_goal":"INTEGER DEFAULT 12"},
        "loans":{"renewals":"INTEGER DEFAULT 0","notes":"TEXT DEFAULT ''"},
    }
    for table, additions in migrations.items():
        existing={row["name"] for row in c.execute("PRAGMA table_info(%s)" % table).fetchall()}
        for name, definition in additions.items():
            if name not in existing:
                c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table,name,definition))
    c.execute("UPDATE books SET condition_status='Bom' WHERE condition_status IS NULL OR trim(condition_status)=''")
    c.execute("UPDATE books SET accession_code='LIB-' || printf('%06d',id) WHERE accession_code IS NULL OR trim(accession_code)=''")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_books_accession_code ON books(accession_code) WHERE accession_code IS NOT NULL")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('loan_days','14')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('max_renewals','2')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('max_active_loans','5')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('school_name','Biblioteca Escolar')")
    c.commit()
    c.execute("PRAGMA foreign_keys=ON")
    errors=c.execute("PRAGMA foreign_key_check").fetchall()
    c.close()
    if errors:
        raise RuntimeError("Migração do banco encontrou referências inconsistentes; faça um backup antes de continuar.")

def get_setting_int(key, default):
    try:
        with connect() as c:
            row=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        return int(row[0]) if row else default
    except (ValueError, sqlite3.Error):
        return default

def find_available_copy(c, identifier, reader_id=None):
    identifier=(identifier or "").strip()
    if not identifier:
        return None
    return c.execute("""SELECT b.* FROM books b
        WHERE (b.accession_code=? OR b.isbn=?)
          AND COALESCE(b.condition_status,'Bom')='Bom'
          AND NOT EXISTS(SELECT 1 FROM loans l WHERE l.book_id=b.id AND l.returned_at IS NULL)
          AND NOT EXISTS(SELECT 1 FROM reservations q WHERE q.book_id=b.id
              AND q.status='Disponível para retirada' AND (? IS NULL OR q.reader_id!=?))
        ORDER BY CASE WHEN EXISTS(SELECT 1 FROM reservations own WHERE own.book_id=b.id
                     AND own.reader_id=? AND own.status='Disponível para retirada') THEN 0 ELSE 1 END,
                 CASE WHEN b.accession_code=? THEN 0 ELSE 1 END,b.id LIMIT 1""",
        (identifier,identifier,reader_id,reader_id,reader_id,identifier)).fetchone()

def log_action(action, entity_type, entity_id, description):
    with connect() as c:
        c.execute("INSERT INTO activity_log(action,entity_type,entity_id,description,created_at) VALUES(?,?,?,?,?)",
                  (action,entity_type,entity_id,description,datetime.now().isoformat(timespec="seconds")))
def ip_address():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try: s.connect(("8.8.8.8",80)); return s.getsockname()[0]
    except OSError: return "127.0.0.1"
    finally: s.close()

def make_web():
    if Flask is None: return None
    web=Flask("libris_mobile")
    page="""<!doctype html><html lang=pt-br><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Libris Mobile</title>
    <style>body{font:16px system-ui;background:#f2f5fa;color:#172033;margin:0}.wrap{max-width:540px;margin:auto;padding:20px}.card{background:white;border-radius:16px;padding:20px;margin:14px 0}input,button{font:inherit;box-sizing:border-box;width:100%;padding:12px;margin:6px 0;border-radius:9px;border:1px solid #ccd3df}button{background:#2449a5;color:white;border:0;font-weight:bold}.ok{color:green}.err{color:#b42318}</style>
    <div class=wrap><h1>📚 Libris</h1><p>Empréstimo pelo celular na mesma rede Wi-Fi.</p><div class=card><h3>Novo empréstimo</h3><form id=f><label>ISBN ou tombo do exemplar</label><input id=isbn required><label>Matrícula do leitor</label><input id=reg required><label>Devolução prevista</label><input id=due type=date required><button>Registrar empréstimo</button></form><p id=msg></p></div><div class=card><h3>Pesquisar livro</h3><input id=q placeholder="Título, autor ou ISBN"><button onclick=searchBook()>Pesquisar</button><div id=results></div></div></div>
    <script>document.getElementById('due').value=new Date(Date.now()+12096e5).toISOString().slice(0,10);document.getElementById('f').onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/mobile-loan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({isbn:document.getElementById('isbn').value.trim(),registration:document.getElementById('reg').value.trim(),due:document.getElementById('due').value})});let j=await r.json();let m=document.getElementById('msg');m.className=j.ok?'ok':'err';m.textContent=j.message};async function searchBook(){let r=await fetch('/api/book?q='+encodeURIComponent(document.getElementById('q').value));let j=await r.json();document.getElementById('results').innerHTML=j.books.length?j.books.map(b=>'<p><b>'+b.title+'</b><br>'+b.author+' · '+(b.category||'Sem gênero')+' · Tombo '+(b.accession_code||'—')+' · Coluna '+(b.column_code||'—')+' / Fileira '+(b.shelf_row||'—')+' · '+(b.condition_status||'Bom')+'</p>').join(''):'Nenhum livro encontrado.'}</script></html>"""
    loan_days=get_setting_int("loan_days",14)
    page=page.replace("12096e5",str(loan_days*86400000))
    @web.get("/mobile")
    def mobile(): return render_template_string(page)
    @web.get("/api/book")
    def books_search():
        q=request.args.get("q","")
        with connect() as c:
            rows=c.execute("""SELECT title,author,isbn,accession_code,column_code,shelf_row,category,condition_status
                FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR accession_code LIKE ?
                ORDER BY title LIMIT 30""",("%"+q+"%","%"+q+"%","%"+q+"%","%"+q+"%")).fetchall()
        return jsonify(books=[dict(r) for r in rows])
    @web.post("/api/mobile-loan")
    def mobile_loan():
        d=request.get_json(silent=True) or {}; isbn=(d.get("isbn") or "").strip(); reg=(d.get("registration") or "").strip()
        try:
            due=date.fromisoformat(d.get("due",""))
            if due<date.today(): raise ValueError()
        except ValueError: return jsonify(ok=False,message="Informe uma data de devolução válida."),400
        with connect() as c:
            r=c.execute("SELECT * FROM readers WHERE registration=?",(reg,)).fetchone()
            if not r: return jsonify(ok=False,message="Matrícula não encontrada."),404
            b=find_available_copy(c,isbn,r["id"])
            if not b:
                exists=c.execute("SELECT 1 FROM books WHERE isbn=? OR accession_code=?",(isbn,isbn)).fetchone()
                if not exists: return jsonify(ok=False,message="ISBN ou tombo não encontrado."),404
                return jsonify(ok=False,message="Nenhum exemplar disponível em boas condições."),409
            active=c.execute("SELECT COUNT(*) FROM loans WHERE reader_id=? AND returned_at IS NULL",(r["id"],)).fetchone()[0]
            limit_row=c.execute("SELECT value FROM settings WHERE key='max_active_loans'").fetchone()
            maximum=int(limit_row[0]) if limit_row else 5
            if active>=maximum: return jsonify(ok=False,message="O leitor atingiu o limite de empréstimos ativos."),409
            c.execute("INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)",(b["id"],r["id"],date.today().isoformat(),due.isoformat()))
            c.execute("UPDATE reservations SET status='Atendida' WHERE book_id=? AND reader_id=? AND status='Disponível para retirada'",(b["id"],r["id"]))
        log_action("EMPRESTIMO","livro",b["id"],"Empréstimo mobile para "+r["name"]+"; tombo "+(b["accession_code"] or ""))
        return jsonify(ok=True,message="Empréstimo registrado para "+r["name"]+" · tombo "+(b["accession_code"] or "")+".")
    return web

class Libris(ctk.CTk):
    BG = "#F4F6FB"
    CARD = "#FFFFFF"
    INK = "#172033"
    MUTED = "#748097"
    NAV = "#111A2E"
    BLUE = "#4568F5"
    GREEN = "#159A72"
    RED = "#D94C5C"

    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("Libris | Gestão de Biblioteca")
        self.geometry("1280x800")
        self.minsize(1050, 680)
        self.configure(fg_color=self.BG)
        init_db()
        self.web=make_web()
        if self.web:
            threading.Thread(target=lambda:serve(self.web,host="0.0.0.0",port=PORT,threads=4),daemon=True).start()
        self.pages={}
        self.nav_buttons={}
        self.build_shell()
        self.show_page("Visão geral")
        self.refresh()

    def build_shell(self):
        self.sidebar=ctk.CTkFrame(self,width=230,corner_radius=0,fg_color=self.NAV)
        self.sidebar.pack(side="left",fill="y")
        self.sidebar.pack_propagate(False)
        brand=ctk.CTkFrame(self.sidebar,fg_color="transparent")
        brand.pack(fill="x",padx=22,pady=(28,34))
        ctk.CTkLabel(brand,text="L",width=42,height=42,corner_radius=13,fg_color=self.BLUE,text_color="white",font=("Arial",24,"bold")).pack(side="left")
        words=ctk.CTkFrame(brand,fg_color="transparent")
        words.pack(side="left",padx=11)
        ctk.CTkLabel(words,text="libris",text_color="#FFFFFF",font=("Arial",23,"bold")).pack(anchor="w")
        ctk.CTkLabel(words,text="BIBLIOTECA DIGITAL",text_color="#9CA8C0",font=("Arial",9,"bold")).pack(anchor="w")
        ctk.CTkLabel(self.sidebar,text="MENU PRINCIPAL",text_color="#7D8AA4",font=("Arial",10,"bold")).pack(anchor="w",padx=24,pady=(0,10))
        navs=[("Visão geral","⌂"),("Livros","▤"),("Leitores","♙"),("Empréstimos","⇄"),("Reservas","◷"),("Importar arquivos","⇧"),("Leitura & ranking","✦"),("Relatórios","▦")]
        for label,ico in navs:
            btn=ctk.CTkButton(self.sidebar,text=f"  {ico}     {label}",anchor="w",height=45,corner_radius=11,
                fg_color="transparent",hover_color="#26334D",text_color="#D8DFEC",font=("Arial",13),
                command=lambda name=label:self.show_page(name))
            btn.pack(fill="x",padx=13,pady=3)
            self.nav_buttons[label]=btn
        ctk.CTkFrame(self.sidebar,fg_color="#2B3850",height=1).pack(fill="x",padx=20,pady=(25,15))
        ctk.CTkLabel(self.sidebar,text="SEU ESPAÇO DE LEITURA",text_color="#7D8AA4",font=("Arial",9,"bold")).pack(anchor="w",padx=23)
        ctk.CTkLabel(self.sidebar,text="Organize. Empreste.\nInspire novas histórias.",justify="left",text_color="#B5C0D3",font=("Arial",12),).pack(anchor="w",padx=23,pady=10)
        self.side_bottom=ctk.CTkLabel(self.sidebar,text="LIBRIS DESKTOP  •  2026",text_color="#73809A",font=("Arial",9))
        self.side_bottom.pack(side="bottom",anchor="w",padx=22,pady=22)

        self.main=ctk.CTkFrame(self,fg_color=self.BG,corner_radius=0)
        self.main.pack(side="left",fill="both",expand=True)
        self.topbar=ctk.CTkFrame(self.main,fg_color=self.CARD,corner_radius=0,height=76)
        self.topbar.pack(fill="x")
        self.topbar.pack_propagate(False)
        self.page_title=ctk.CTkLabel(self.topbar,text="Visão geral",text_color=self.INK,font=("Arial",21,"bold"))
        self.page_title.pack(side="left",padx=30)
        self.top_right=ctk.CTkFrame(self.topbar,fg_color="transparent")
        self.top_right.pack(side="right",padx=28)
        ctk.CTkLabel(self.top_right,text="●",text_color=self.GREEN,font=("Arial",12)).pack(side="left",padx=(0,7))
        ctk.CTkLabel(self.top_right,text="Sistema local ativo",text_color=self.MUTED,font=("Arial",11)).pack(side="left")
        self.content=ctk.CTkFrame(self.main,fg_color=self.BG,corner_radius=0)
        self.content.pack(fill="both",expand=True,padx=26,pady=24)
        self.create_pages()

    def create_pages(self):
        self.pages["Visão geral"]=ctk.CTkScrollableFrame(self.content,fg_color="transparent",corner_radius=0)
        self.dashboard_ui(self.pages["Visão geral"])
        self.pages["Livros"]=ctk.CTkFrame(self.content,fg_color="transparent")
        self.book_ui(self.pages["Livros"])
        self.pages["Leitores"]=ctk.CTkFrame(self.content,fg_color="transparent")
        self.reader_ui(self.pages["Leitores"])
        self.pages["Empréstimos"]=ctk.CTkFrame(self.content,fg_color="transparent")
        self.loan_ui(self.pages["Empréstimos"])
        self.pages["Reservas"]=ctk.CTkFrame(self.content,fg_color="transparent")
        self.reservation_ui(self.pages["Reservas"])
        self.pages["Importar arquivos"]=ctk.CTkScrollableFrame(self.content,fg_color="transparent",corner_radius=0)
        self.import_documents_ui(self.pages["Importar arquivos"])
        self.pages["Leitura & ranking"]=ctk.CTkScrollableFrame(self.content,fg_color="transparent",corner_radius=0)
        self.rank_ui(self.pages["Leitura & ranking"])
        self.pages["Relatórios"]=ctk.CTkScrollableFrame(self.content,fg_color="transparent",corner_radius=0)
        self.reports_ui(self.pages["Relatórios"])

    def show_page(self,name):
        if not hasattr(self,"pages"): return
        for p in self.pages.values(): p.pack_forget()
        self.pages[name].pack(fill="both",expand=True)
        self.page_title.configure(text=name)
        for label,btn in self.nav_buttons.items():
            btn.configure(fg_color="#2A3B61" if label==name else "transparent",
                          text_color="#FFFFFF" if label==name else "#D8DFEC")

    def section_title(self,parent,title,subtitle=None):
        ctk.CTkLabel(parent,text=title,text_color=self.INK,font=("Arial",23,"bold")).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(parent,text=subtitle,text_color=self.MUTED,font=("Arial",12)).pack(anchor="w",pady=(5,17))

    def panel(self,parent):
        p=ctk.CTkFrame(parent,fg_color=self.CARD,corner_radius=16,border_width=1,border_color="#E8ECF4")
        return p

    def metric(self,parent,title,value,detail,accent):
        p=self.panel(parent)
        p.pack(side="left",fill="both",expand=True,padx=(0,12))
        ctk.CTkFrame(p,fg_color=accent,width=4,corner_radius=3).pack(side="left",fill="y",padx=(0,14),pady=17)
        inside=ctk.CTkFrame(p,fg_color="transparent")
        inside.pack(side="left",fill="both",expand=True,pady=15)
        ctk.CTkLabel(inside,text=title,text_color=self.MUTED,font=("Arial",11,"bold")).pack(anchor="w")
        val=ctk.CTkLabel(inside,text=str(value),text_color=self.INK,font=("Arial",27,"bold"))
        val.pack(anchor="w",pady=(3,0))
        ctk.CTkLabel(inside,text=detail,text_color=self.MUTED,font=("Arial",10)).pack(anchor="w",pady=(2,0))
        return val

    def dashboard_ui(self,parent):
        self.section_title(parent,"Bom ter você por aqui 👋","Acompanhe a biblioteca e gerencie tudo em um só lugar.")
        self.metrics=ctk.CTkFrame(parent,fg_color="transparent")
        self.metrics.pack(fill="x",pady=(0,20))
        self.m_books=self.metric(self.metrics,"LIVROS NO ACERVO","0","Títulos cadastrados","#4568F5")
        self.m_readers=self.metric(self.metrics,"LEITORES","0","Pessoas cadastradas","#159A72")
        self.m_loans=self.metric(self.metrics,"EMPRÉSTIMOS ATIVOS","0","Livros fora do acervo","#E7A23B")
        self.m_late=self.metric(self.metrics,"DEVOLUÇÕES ATRASADAS","0","Precisam de atenção","#D94C5C")
        lower=ctk.CTkFrame(parent,fg_color="transparent")
        lower.pack(fill="both",expand=True)
        recent=self.panel(lower); recent.pack(side="left",fill="both",expand=True,padx=(0,10))
        ctk.CTkLabel(recent,text="Empréstimos recentes",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,3))
        ctk.CTkLabel(recent,text="Acompanhe o movimento da biblioteca.",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=20,pady=(0,10))
        self.recent_table=self.table(recent,("Livro","Leitor","Devolução","Status"),height=8)
        self.recent_table.pack(fill="both",expand=True,padx=14,pady=(0,16))
        quick=self.panel(lower); quick.pack(side="left",fill="y",padx=(10,0))
        ctk.CTkLabel(quick,text="Acesso rápido",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(quick,text="O que você precisa fazer?",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=20,pady=(0,14))
        for label,desc,action in [
            ("＋  Cadastrar livro","Adicione um título ao acervo",lambda:self.show_page("Livros")),
            ("♙  Cadastrar leitor","Registre um novo leitor",lambda:self.show_page("Leitores")),
            ("⇄  Novo empréstimo","Registre uma retirada",lambda:self.show_page("Empréstimos")),
            ("▦  Acesso pelo celular","Veja o QR Code da biblioteca",self.open_mobile_info)]:
            ctk.CTkButton(quick,text=label,anchor="w",height=43,corner_radius=10,fg_color="#F2F5FC",hover_color="#E5EBFA",text_color=self.INK,font=("Arial",12,"bold"),command=action).pack(fill="x",padx=16,pady=5)
        self.qr_url="http://"+ip_address()+":"+str(PORT)+"/mobile"

    def table(self,parent,cols,height=12):
        wrap=ctk.CTkFrame(parent,fg_color=self.CARD,corner_radius=12)
        style=ttk.Style()
        style.theme_use("clam")
        style.configure("Libris.Treeview",background="#FFFFFF",foreground="#253149",fieldbackground="#FFFFFF",rowheight=34,borderwidth=0,font=("Arial",10))
        style.configure("Libris.Treeview.Heading",background="#F1F4FA",foreground="#66738B",font=("Arial",9,"bold"),relief="flat",padding=9)
        style.map("Libris.Treeview",background=[("selected","#E2E9FF")],foreground=[("selected","#172033")])
        t=ttk.Treeview(wrap,columns=cols,show="headings",height=height,style="Libris.Treeview")
        sy=ttk.Scrollbar(wrap,orient="vertical",command=t.yview)
        sx=ttk.Scrollbar(wrap,orient="horizontal",command=t.xview)
        t.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        sy.pack(side="right",fill="y")
        sx.pack(side="bottom",fill="x")
        t.pack(side="left",fill="both",expand=True)
        for col in cols:
            t.heading(col,text=col)
            t.column(col,width=125,minwidth=80,anchor="w")
        return t

    def form_card(self,parent,fields,button,cmd):
        card=self.panel(parent); card.pack(fill="x",pady=(0,16))
        inner=ctk.CTkFrame(card,fg_color="transparent"); inner.pack(fill="x",padx=18,pady=18)
        self._form_vars=[]
        for label,var in fields:
            cell=ctk.CTkFrame(inner,fg_color="transparent")
            cell.pack(side="left",fill="x",expand=True,padx=(0,10))
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",10,"bold")).pack(anchor="w",pady=(0,5))
            ctk.CTkEntry(cell,textvariable=var,height=39,corner_radius=9,border_color="#DDE3EE",fg_color="#FBFCFE",text_color=self.INK).pack(fill="x")
        self.last_form_button=ctk.CTkButton(inner,text=button,height=39,corner_radius=9,fg_color=self.BLUE,hover_color="#3453D5",font=("Arial",11,"bold"),command=cmd,width=150)
        self.last_form_button.pack(side="left",pady=(22,0))
        return card

    def book_ui(self,parent):
        self.section_title(parent,"Acervo e localização","Cada exemplar recebe um tombo próprio; várias cópias podem compartilhar o mesmo ISBN.")
        self.bv=[tk.StringVar() for _ in range(7)]
        card=self.panel(parent); card.pack(fill="x",pady=(0,12))
        inner=ctk.CTkFrame(card,fg_color="transparent"); inner.pack(fill="x",padx=16,pady=13)
        row1=ctk.CTkFrame(inner,fg_color="transparent"); row1.pack(fill="x",pady=(0,8))
        for label,var in [("TÍTULO",self.bv[0]),("AUTOR",self.bv[1]),("ISBN",self.bv[2]),("TOMBO / CÓDIGO DE BARRAS (opcional)",self.bv[3])]:
            cell=ctk.CTkFrame(row1,fg_color="transparent"); cell.pack(side="left",fill="x",expand=True,padx=(0,8))
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",9,"bold")).pack(anchor="w",pady=(0,4))
            ctk.CTkEntry(cell,textvariable=var,height=36,corner_radius=8,border_color="#DDE3EE",fg_color="#FBFCFE",text_color=self.INK).pack(fill="x")
        row2=ctk.CTkFrame(inner,fg_color="transparent"); row2.pack(fill="x")
        for label,var,placeholder in [("COLUNA (LETRA)",self.bv[4],"A"),("FILEIRA (NÚMERO)",self.bv[5],"3"),("GÊNERO",self.bv[6],"Romance")]:
            cell=ctk.CTkFrame(row2,fg_color="transparent"); cell.pack(side="left",fill="x",expand=True,padx=(0,8))
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",9,"bold")).pack(anchor="w",pady=(0,4))
            ctk.CTkEntry(cell,textvariable=var,placeholder_text=placeholder,height=36,corner_radius=8,border_color="#DDE3EE",fg_color="#FBFCFE",text_color=self.INK).pack(fill="x")
        self.editing_book_id=None
        self.book_submit_btn=ctk.CTkButton(row2,text="＋  Cadastrar exemplar",height=36,corner_radius=8,fg_color=self.BLUE,hover_color="#3453D5",font=("Arial",10,"bold"),command=self.add_book,width=160)
        self.book_submit_btn.pack(side="left",pady=(20,0))
        searchbar=ctk.CTkFrame(parent,fg_color="transparent"); searchbar.pack(fill="x",pady=(0,8))
        self.book_search_var=tk.StringVar()
        search_entry=ctk.CTkEntry(searchbar,textvariable=self.book_search_var,placeholder_text="Pesquisar por título, autor, ISBN, tombo, gênero ou localização…",height=36)
        search_entry.pack(side="left",fill="x",expand=True,padx=(0,8))
        search_entry.bind("<KeyRelease>",lambda event:self.refresh())
        ctk.CTkButton(searchbar,text="Limpar busca",height=36,width=105,command=lambda:(self.book_search_var.set(""),self.refresh())).pack(side="right")
        self.btable=self.table(parent,("ID","Tombo","Título","Autor","ISBN","Coluna","Fileira","Gênero","Situação","Última conferência"),height=9)
        self.btable.pack(fill="both",expand=True)
        actions=ctk.CTkFrame(parent,fg_color="transparent"); actions.pack(fill="x",pady=(8,0))
        ctk.CTkLabel(actions,text="Selecione um exemplar para editar ou atualizar a condição:",text_color=self.MUTED,font=("Arial",10)).pack(side="left")
        ctk.CTkButton(actions,text="Editar cadastro",width=110,height=32,command=self.load_book_for_edit).pack(side="right",padx=4)
        ctk.CTkButton(actions,text="Em manutenção",width=120,height=32,command=lambda:self.set_book_condition("Em manutenção"),fg_color="#FFF0D9",hover_color="#FBE1B5",text_color="#8A5B13").pack(side="right",padx=4)
        ctk.CTkButton(actions,text="Extraviado",width=100,height=32,command=lambda:self.set_book_condition("Extraviado"),fg_color="#FCE8EA",hover_color="#F7D1D5",text_color="#A52C3D").pack(side="right",padx=4)
        ctk.CTkButton(actions,text="Marcar como bom",width=120,height=32,command=lambda:self.set_book_condition("Bom"),fg_color="#E2F5EC",hover_color="#C8EBDD",text_color="#117452").pack(side="right",padx=4)

    def reader_ui(self,parent):
        self.section_title(parent,"Leitores e turmas","Organize os cadastros por turma e acompanhe uma meta anual de leitura.")
        self.rv=[tk.StringVar() for _ in range(5)]
        self.editing_reader_id=None
        self.form_card(parent,[("NOME COMPLETO",self.rv[0]),("MATRÍCULA",self.rv[1]),("TURMA / ANO",self.rv[2]),("TELEFONE",self.rv[3]),("META ANUAL (livros)",self.rv[4])],"＋  Cadastrar leitor",self.add_reader)
        self.reader_submit_btn=self.last_form_button
        self.rtable=self.table(parent,("ID","Nome","Matrícula","Turma","Telefone","Meta anual"),height=12)
        self.rtable.pack(fill="both",expand=True)
        ctk.CTkButton(parent,text="Editar leitor selecionado",command=self.load_reader_for_edit,height=34,fg_color="#E8EEFF",hover_color="#D9E2FF",text_color="#324CC1").pack(anchor="e",pady=(8,0))

    def loan_ui(self,parent):
        self.section_title(parent,"Circulação de exemplares","Digite ou use um leitor de código de barras para informar o tombo ou ISBN.")
        self.lv=[tk.StringVar(),tk.StringVar(),tk.StringVar(value=(date.today()+timedelta(days=get_setting_int("loan_days",14))).isoformat())]
        self.form_card(parent,[("ISBN OU TOMBO DO EXEMPLAR",self.lv[0]),("MATRÍCULA DO LEITOR",self.lv[1]),("DEVOLUÇÃO (AAAA-MM-DD)",self.lv[2])],"＋  Registrar empréstimo",self.add_loan)
        actions=ctk.CTkFrame(parent,fg_color="transparent"); actions.pack(fill="x",pady=(0,10))
        ctk.CTkLabel(actions,text="Histórico e situação dos empréstimos",text_color=self.INK,font=("Arial",14,"bold")).pack(side="left")
        ctk.CTkButton(actions,text="↻ Renovar +14 dias",height=33,corner_radius=9,fg_color="#E8EEFF",hover_color="#D9E2FF",text_color="#324CC1",command=self.renew_loan).pack(side="right",padx=(5,0))
        ctk.CTkButton(actions,text="✓ Marcar devolução",height=33,corner_radius=9,fg_color="#E3F5EE",hover_color="#C8EBDD",text_color="#117452",command=self.return_loan).pack(side="right")
        self.ltable=self.table(parent,("ID","Livro","Leitor","Empréstimo","Devolução prevista","Renovações","Status"),height=10)
        self.ltable.pack(fill="both",expand=True)

    def rank_ui(self,parent):
        self.section_title(parent,"Leitura e ranking","Use os dados da biblioteca para reconhecer a participação na leitura — sem expor histórico individual no painel.")
        grid=ctk.CTkFrame(parent,fg_color="transparent"); grid.pack(fill="x",pady=(0,14))
        left=self.panel(grid); left.pack(side="left",fill="both",expand=True,padx=(0,10))
        right=self.panel(grid); right.pack(side="left",fill="both",expand=True,padx=(10,0))
        ctk.CTkLabel(left,text="🏆  Progresso anual dos leitores",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=18,pady=(18,3))
        ctk.CTkLabel(left,text="Livros devolvidos este ano / meta individual",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=18,pady=(0,12))
        ctk.CTkLabel(right,text="📚  Livros em destaque",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=18,pady=(18,3))
        ctk.CTkLabel(right,text="Total de empréstimos registrados",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=18,pady=(0,12))
        self.rr=self.table(left,("Posição","Leitor","Progresso (meta)"),height=14); self.rr.pack(fill="both",expand=True,padx=12,pady=(0,14))
        self.rb=self.table(right,("Posição","Livro","Empréstimos"),height=14); self.rb.pack(fill="both",expand=True,padx=12,pady=(0,14))
        suggest=self.panel(parent); suggest.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(suggest,text="✨  Sugestões inteligentes de leitura",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=18,pady=(16,3))
        ctk.CTkLabel(suggest,text="Informe a matrícula: o Libris usa gêneros já lidos, popularidade e disponibilidade para sugerir exemplares ainda não emprestados àquele leitor.",text_color=self.MUTED,font=("Arial",11),wraplength=850,justify="left").pack(anchor="w",padx=18,pady=(0,8))
        sr=ctk.CTkFrame(suggest,fg_color="transparent"); sr.pack(fill="x",padx=14,pady=(0,8))
        self.suggest_var=tk.StringVar()
        ctk.CTkEntry(sr,textvariable=self.suggest_var,placeholder_text="Matrícula do leitor",height=36,width=230).pack(side="left",padx=(0,8))
        ctk.CTkButton(sr,text="Gerar recomendações",height=36,command=self.suggest_books).pack(side="left")
        self.suggestion_table=self.table(suggest,("Gênero","Livro recomendado","Autor","Localização"),height=5)
        self.suggestion_table.pack(fill="both",expand=True,padx=12,pady=(0,12))

    def suggest_books(self):
        registration=self.suggest_var.get().strip()
        if not registration:
            messagebox.showwarning("Sugestões","Informe a matrícula do leitor.")
            return
        with connect() as c:
            reader=c.execute("SELECT id,name FROM readers WHERE registration=?",(registration,)).fetchone()
            if not reader:
                messagebox.showerror("Sugestões","Matrícula não encontrada.")
                return
            genre_row=c.execute("""SELECT b.category,COUNT(*) n FROM loans l JOIN books b ON b.id=l.book_id
                WHERE l.reader_id=? AND l.returned_at IS NOT NULL AND trim(COALESCE(b.category,''))!=''
                GROUP BY lower(b.category) ORDER BY n DESC,b.category LIMIT 1""",(reader["id"],)).fetchone()
            if not genre_row:
                genre_row=c.execute("""SELECT b.category,COUNT(*) n FROM loans l JOIN books b ON b.id=l.book_id
                    WHERE trim(COALESCE(b.category,''))!='' GROUP BY lower(b.category) ORDER BY n DESC,b.category LIMIT 1""").fetchone()
            if not genre_row:
                genre_row=c.execute("SELECT category,1 n FROM books WHERE trim(COALESCE(category,''))!='' GROUP BY lower(category) ORDER BY category LIMIT 1").fetchone()
            if not genre_row:
                messagebox.showinfo("Sugestões","Cadastre gêneros nos livros para habilitar as recomendações.")
                self.fill(self.suggestion_table,[])
                return
            genre=genre_row["category"]
            rows=c.execute("""SELECT b.category,b.title,b.author,
                COALESCE(NULLIF(b.column_code,''),'—') || ' / ' || COALESCE(CAST(b.shelf_row AS TEXT),'—')
                FROM books b WHERE lower(COALESCE(b.category,''))=lower(?)
                AND COALESCE(b.condition_status,'Bom')='Bom'
                AND NOT EXISTS(SELECT 1 FROM loans a WHERE a.book_id=b.id AND a.returned_at IS NULL)
                AND NOT EXISTS(SELECT 1 FROM loans old WHERE old.reader_id=? AND old.book_id=b.id)
                ORDER BY (SELECT COUNT(*) FROM loans popular WHERE popular.book_id=b.id) DESC,b.title LIMIT 10""",
                (genre,reader["id"])).fetchall()
            if not rows:
                rows=c.execute("""SELECT b.category,b.title,b.author,
                    COALESCE(NULLIF(b.column_code,''),'—') || ' / ' || COALESCE(CAST(b.shelf_row AS TEXT),'—')
                    FROM books b WHERE COALESCE(b.condition_status,'Bom')='Bom'
                    AND NOT EXISTS(SELECT 1 FROM loans a WHERE a.book_id=b.id AND a.returned_at IS NULL)
                    AND NOT EXISTS(SELECT 1 FROM loans old WHERE old.reader_id=? AND old.book_id=b.id)
                    ORDER BY (SELECT COUNT(*) FROM loans h JOIN books hb ON hb.id=h.book_id
                        WHERE h.reader_id=? AND h.returned_at IS NOT NULL AND lower(COALESCE(hb.category,''))=lower(COALESCE(b.category,''))) DESC,
                        (SELECT COUNT(*) FROM loans popular WHERE popular.book_id=b.id) DESC,b.title LIMIT 10""",
                    (reader["id"],reader["id"])).fetchall()
        self.fill(self.suggestion_table,rows)
        if not rows:
            messagebox.showinfo("Sugestões","Não há exemplares disponíveis e ainda não lidos no gênero "+str(genre)+" para este leitor.")

    def open_mobile_info(self):
        url="http://"+ip_address()+":"+str(PORT)+"/mobile"
        win=ctk.CTkToplevel(self); win.title("Acesso pelo celular"); win.geometry("440x500"); win.configure(fg_color=self.BG); win.transient(self)
        ctk.CTkLabel(win,text="Acesse pelo celular",font=("Arial",22,"bold"),text_color=self.INK).pack(pady=(24,8))
        ctk.CTkLabel(win,text="Conecte os dois dispositivos à mesma rede Wi-Fi.",text_color=self.MUTED,wraplength=360).pack(pady=4)
        if qrcode and Image:
            im=qrcode.make(url).resize((220,220))
            self.mobile_qr=ctk.CTkImage(light_image=im,dark_image=im,size=(220,220))
            ctk.CTkLabel(win,text="",image=self.mobile_qr).pack(pady=12)
        ctk.CTkLabel(win,text=url,text_color=self.BLUE,font=("Arial",12,"bold")).pack(pady=4)
        ctk.CTkButton(win,text="Abrir neste computador",command=lambda:webbrowser.open("http://127.0.0.1:"+str(PORT)+"/mobile")).pack(pady=10)

    def add_book(self):
        vals=[v.get().strip() for v in self.bv]
        if not vals[0]:
            messagebox.showwarning("Cadastro","Informe o título do livro.")
            return
        column=vals[4].upper()
        if column and (len(column)>3 or not column.isalpha()):
            messagebox.showwarning("Localização inválida","A coluna deve conter letras, por exemplo A ou AB.")
            return
        try:
            shelf_row=int(vals[5]) if vals[5] else None
            if shelf_row is not None and shelf_row<1: raise ValueError()
        except ValueError:
            messagebox.showwarning("Localização inválida","A fileira deve ser um número inteiro positivo.")
            return
        accession=vals[3].upper() if vals[3] else ""
        try:
            with connect() as c:
                if self.editing_book_id:
                    if not accession:
                        current=c.execute("SELECT accession_code FROM books WHERE id=?",(self.editing_book_id,)).fetchone()
                        accession=current[0] if current else ""
                    c.execute("""UPDATE books SET title=?,author=?,isbn=?,category=?,column_code=?,shelf_row=?,accession_code=?
                        WHERE id=?""",(vals[0],vals[1],vals[2] or None,vals[6],column,shelf_row,accession,self.editing_book_id))
                    book_id=self.editing_book_id
                    action="EDICAO"
                else:
                    if not accession:
                        accession="LIB-%06d" % c.execute("SELECT COALESCE(MAX(id),0)+1 FROM books").fetchone()[0]
                    c.execute("""INSERT INTO books(title,author,isbn,category,column_code,shelf_row,accession_code,condition_status)
                        VALUES(?,?,?,?,?,?,?,'Bom')""",(vals[0],vals[1],vals[2] or None,vals[6],column,shelf_row,accession))
                    book_id=c.execute("SELECT id FROM books WHERE accession_code=?",(accession,)).fetchone()[0]
                    action="CADASTRO"
            log_action(action,"livro",book_id,"Exemplar salvo: "+vals[0]+" · tombo "+accession)
        except sqlite3.IntegrityError:
            messagebox.showerror("Cadastro","Esse tombo já existe. Use outro código de exemplar.")
            return
        [v.set("") for v in self.bv]
        self.editing_book_id=None
        self.book_submit_btn.configure(text="＋  Cadastrar exemplar")
        self.refresh()

    def load_book_for_edit(self):
        sel=self.btable.selection()
        if not sel:
            messagebox.showwarning("Editar exemplar","Selecione um exemplar no catálogo.")
            return
        row=self.btable.item(sel[0])["values"]
        self.editing_book_id=row[0]
        values=[row[2],row[3],row[4],row[1],row[5],row[6],row[7]]
        for var,value in zip(self.bv,values):
            var.set("" if value is None else str(value))
        self.book_submit_btn.configure(text="Salvar alterações")
        messagebox.showinfo("Editar exemplar","Os dados foram carregados no formulário. Altere os campos e clique em Salvar alterações.")

    def add_reader(self):
        vals=[v.get().strip() for v in self.rv]
        if not vals[0] or not vals[1]:
            messagebox.showwarning("Cadastro","Informe nome e matrícula.")
            return
        try:
            goal=int(vals[4] or "12")
            if goal<1 or goal>500: raise ValueError()
        except ValueError:
            messagebox.showwarning("Meta de leitura","Informe uma meta anual entre 1 e 500 livros.")
            return
        try:
            with connect() as c:
                if self.editing_reader_id:
                    reader_id=self.editing_reader_id
                    c.execute("UPDATE readers SET name=?,registration=?,class_name=?,phone=?,reading_goal=? WHERE id=?",
                              (vals[0],vals[1],vals[2],vals[3],goal,reader_id))
                    action="EDICAO"
                else:
                    c.execute("INSERT INTO readers(name,registration,class_name,phone,reading_goal) VALUES(?,?,?,?,?)",
                              (vals[0],vals[1],vals[2],vals[3],goal))
                    reader_id=c.execute("SELECT id FROM readers WHERE registration=?",(vals[1],)).fetchone()[0]
                    action="CADASTRO"
            log_action(action,"leitor",reader_id,"Leitor salvo: "+vals[0]+" · turma "+(vals[2] or "não informada"))
        except sqlite3.IntegrityError:
            messagebox.showerror("Cadastro","Matrícula já cadastrada.")
            return
        [v.set("") for v in self.rv]
        self.rv[4].set("12")
        self.editing_reader_id=None
        self.reader_submit_btn.configure(text="＋  Cadastrar leitor")
        self.refresh()

    def load_reader_for_edit(self):
        sel=self.rtable.selection()
        if not sel:
            messagebox.showwarning("Editar leitor","Selecione um leitor na tabela.")
            return
        row=self.rtable.item(sel[0])["values"]
        self.editing_reader_id=row[0]
        for var,value in zip(self.rv,[row[1],row[2],row[3],row[4],row[5]]):
            var.set("" if value is None else str(value))
        self.reader_submit_btn.configure(text="Salvar alterações")
        messagebox.showinfo("Editar leitor","Os dados foram carregados no formulário. Altere os campos e clique em Salvar alterações.")

    def add_loan(self):
        identifier,reg,due_s=[v.get().strip() for v in self.lv]
        try:
            due=date.fromisoformat(due_s)
            if due<date.today(): raise ValueError()
        except ValueError:
            messagebox.showwarning("Data inválida","Informe a data no formato AAAA-MM-DD.")
            return
        with connect() as c:
            r=c.execute("SELECT * FROM readers WHERE registration=?",(reg,)).fetchone()
            if not r:
                messagebox.showerror("Empréstimo","Matrícula não encontrada.")
                return
            b=find_available_copy(c,identifier,r["id"])
            if not b:
                exists=c.execute("SELECT 1 FROM books WHERE isbn=? OR accession_code=?",(identifier,identifier)).fetchone()
                messagebox.showerror("Empréstimo","Nenhum exemplar disponível em boas condições." if exists else "ISBN ou tombo não encontrado.")
                return
            active=c.execute("SELECT COUNT(*) FROM loans WHERE reader_id=? AND returned_at IS NULL",(r["id"],)).fetchone()[0]
            max_row=c.execute("SELECT value FROM settings WHERE key='max_active_loans'").fetchone()
            maximum=int(max_row[0]) if max_row else 5
            if active>=maximum:
                messagebox.showwarning("Limite de empréstimos","Este leitor já tem %d empréstimos ativos." % maximum)
                return
            c.execute("INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)",
                      (b["id"],r["id"],date.today().isoformat(),due.isoformat()))
            c.execute("UPDATE reservations SET status='Atendida' WHERE book_id=? AND reader_id=? AND status='Disponível para retirada'",(b["id"],r["id"]))
        log_action("EMPRESTIMO","livro",b["id"],"Tombo "+(b["accession_code"] or "")+" emprestado para "+r["name"])
        self.lv[0].set("")
        self.refresh()
        messagebox.showinfo("Libris","Empréstimo registrado para %s. Tombo: %s" % (r["name"],b["accession_code"] or "—"))

    def return_loan(self):
        sel=self.ltable.selection()
        if not sel:
            messagebox.showwarning("Devolução","Selecione um empréstimo.")
            return
        lid=self.ltable.item(sel[0])["values"][0]
        with connect() as c:
            loan=c.execute("SELECT book_id,reader_id,returned_at FROM loans WHERE id=?",(lid,)).fetchone()
            if not loan or loan["returned_at"]:
                messagebox.showinfo("Devolução","Este empréstimo já foi encerrado.")
                return
            c.execute("UPDATE loans SET returned_at=? WHERE id=?",(date.today().isoformat(),lid))
            reservation=c.execute("""SELECT q.id,q.reader_id FROM reservations q JOIN books b ON b.id=q.book_id
                WHERE q.book_id=? AND q.status='Na fila' AND b.condition_status='Bom'
                ORDER BY q.request_date,q.id LIMIT 1""",(loan["book_id"],)).fetchone()
            reservation_message=""
            if reservation:
                c.execute("UPDATE reservations SET status='Disponível para retirada',notified_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),reservation["id"]))
                reader=c.execute("SELECT name FROM readers WHERE id=?",(reservation["reader_id"],)).fetchone()
                reservation_message=" Reserva #%s de %s está pronta para retirada." % (reservation["id"],reader["name"] if reader else "leitor")
            title=c.execute("SELECT title FROM books WHERE id=?",(loan["book_id"],)).fetchone()
        log_action("DEVOLUCAO","emprestimo",lid,"Devolução registrada do livro "+(title["title"] if title else ""))
        self.refresh()
        messagebox.showinfo("Devolução","Devolução registrada com sucesso."+reservation_message)

    def renew_loan(self):
        sel=self.ltable.selection()
        if not sel:
            messagebox.showwarning("Renovação","Selecione um empréstimo ativo.")
            return
        lid=self.ltable.item(sel[0])["values"][0]
        with connect() as c:
            loan=c.execute("SELECT book_id,due_date,returned_at,renewals FROM loans WHERE id=?",(lid,)).fetchone()
            if not loan or loan["returned_at"]:
                messagebox.showwarning("Renovação","Só é possível renovar empréstimos ativos.")
                return
            row=c.execute("SELECT value FROM settings WHERE key='max_renewals'").fetchone()
            maximum=int(row[0]) if row else 2
            if loan["renewals"]>=maximum:
                messagebox.showwarning("Renovação","Este empréstimo atingiu o limite de %d renovação(ões)." % maximum)
                return
            waiting=c.execute("SELECT 1 FROM reservations WHERE book_id=? AND status='Na fila' LIMIT 1",(loan["book_id"],)).fetchone()
            if waiting:
                messagebox.showwarning("Renovação","Há uma reserva aguardando este exemplar; ele deve ser devolvido para atender a fila.")
                return
            new_due=max(date.fromisoformat(loan["due_date"]),date.today())+timedelta(days=get_setting_int("loan_days",14))
            c.execute("UPDATE loans SET due_date=?,renewals=renewals+1 WHERE id=?",(new_due.isoformat(),lid))
        log_action("RENOVACAO","emprestimo",lid,"Empréstimo renovado até "+new_due.isoformat())
        self.refresh()
        messagebox.showinfo("Renovação","Nova data de devolução: "+new_due.strftime("%d/%m/%Y"))

    def set_book_condition(self,status):
        sel=self.btable.selection()
        if not sel:
            messagebox.showwarning("Inventário","Selecione um exemplar no catálogo.")
            return
        book_id=self.btable.item(sel[0])["values"][0]
        with connect() as c:
            active=c.execute("SELECT 1 FROM loans WHERE book_id=? AND returned_at IS NULL",(book_id,)).fetchone()
            if active and status=="Bom":
                messagebox.showwarning("Inventário","Registre a devolução antes de marcar o exemplar como disponível.")
                return
            c.execute("UPDATE books SET condition_status=? WHERE id=?",(status,book_id))
            released=None
            if status=="Bom":
                released=c.execute("SELECT id,reader_id FROM reservations WHERE book_id=? AND status='Na fila' ORDER BY request_date,id LIMIT 1",(book_id,)).fetchone()
                if released:
                    c.execute("UPDATE reservations SET status='Disponível para retirada',notified_at=? WHERE id=?",
                              (datetime.now().isoformat(timespec="seconds"),released["id"]))
            if released:
                r=c.execute("SELECT name FROM readers WHERE id=?",(released["reader_id"],)).fetchone()
                released_name=r["name"] if r else "leitor"
            else:
                released_name=""
        log_action("INVENTARIO","livro",book_id,"Condição do exemplar alterada para "+status)
        self.refresh()
        if released_name:
            messagebox.showinfo("Reserva liberada","O exemplar está disponível para retirada por "+released_name+".")

    def reservation_ui(self,parent):
        self.section_title(parent,"Reservas","Na devolução, o primeiro leitor da fila passa a ter prioridade para retirar o exemplar.")
        self.qv=[tk.StringVar(),tk.StringVar()]
        self.form_card(parent,[("ISBN OU TOMBO",self.qv[0]),("MATRÍCULA DO LEITOR",self.qv[1])],"＋  Criar reserva",self.add_reservation)
        actions=ctk.CTkFrame(parent,fg_color="transparent"); actions.pack(fill="x",pady=(0,8))
        ctk.CTkLabel(actions,text="Fila de reservas",text_color=self.INK,font=("Arial",14,"bold")).pack(side="left")
        ctk.CTkButton(actions,text="Cancelar reserva selecionada",height=32,command=self.cancel_reservation,fg_color="#FCE8EA",hover_color="#F7D1D5",text_color="#A52C3D").pack(side="right")
        self.qtable=self.table(parent,("ID","Tombo","Livro","Leitor","Matrícula","Solicitada em","Status"),height=13)
        self.qtable.pack(fill="both",expand=True)

    def add_reservation(self):
        identifier,reg=[v.get().strip() for v in self.qv]
        if not identifier or not reg:
            messagebox.showwarning("Reserva","Informe o ISBN/tombo e a matrícula.")
            return
        with connect() as c:
            book=c.execute("SELECT * FROM books WHERE accession_code=? OR isbn=? ORDER BY id LIMIT 1",(identifier,identifier)).fetchone()
            reader=c.execute("SELECT * FROM readers WHERE registration=?",(reg,)).fetchone()
            if not book:
                messagebox.showerror("Reserva","ISBN ou tombo não encontrado.")
                return
            if not reader:
                messagebox.showerror("Reserva","Matrícula não encontrada.")
                return
            duplicate=c.execute("SELECT 1 FROM reservations WHERE book_id=? AND reader_id=? AND status IN ('Na fila','Disponível para retirada')",(book["id"],reader["id"])).fetchone()
            if duplicate:
                messagebox.showinfo("Reserva","Este leitor já tem uma reserva ativa para esse exemplar.")
                return
            active=c.execute("SELECT 1 FROM loans WHERE book_id=? AND returned_at IS NULL",(book["id"],)).fetchone()
            status="Disponível para retirada" if book["condition_status"]=="Bom" and not active else "Na fila"
            c.execute("INSERT INTO reservations(book_id,reader_id,request_date,status,notified_at) VALUES(?,?,?,?,?)",
                      (book["id"],reader["id"],date.today().isoformat(),status,datetime.now().isoformat(timespec="seconds") if status=="Disponível para retirada" else None))
            rid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
        log_action("RESERVA","reserva",rid,"Reserva criada para "+reader["name"]+" · "+book["title"])
        [v.set("") for v in self.qv]
        self.refresh()
        messagebox.showinfo("Reserva","Reserva registrada: "+status+".")

    def cancel_reservation(self):
        sel=self.qtable.selection()
        if not sel:
            messagebox.showwarning("Reserva","Selecione uma reserva.")
            return
        rid=self.qtable.item(sel[0])["values"][0]
        with connect() as c:
            c.execute("UPDATE reservations SET status='Cancelada' WHERE id=? AND status IN ('Na fila','Disponível para retirada')",(rid,))
        log_action("RESERVA_CANCELADA","reserva",rid,"Reserva cancelada pela equipe da biblioteca")
        self.refresh()

    def reports_ui(self,parent):
        self.section_title(parent,"Relatórios, exportações e segurança","Exporte dados para a coordenação e mantenha uma cópia de segurança do banco.")
        card=self.panel(parent); card.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(card,text="Exportar dados em CSV",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(card,text="Arquivos compatíveis com Excel e LibreOffice.",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=20,pady=(0,12))
        row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x",padx=16,pady=(0,16))
        for label,kind in [("Acervo completo","books"),("Leitores e turmas","readers"),("Empréstimos e atrasos","loans"),("Fila de reservas","reservations"),("Histórico de ações","activity"),("Inventário físico","inventory")]:
            ctk.CTkButton(row,text=label,command=lambda k=kind:self.export_report(k),height=38,corner_radius=9).pack(side="left",fill="x",expand=True,padx=4)
        imp=self.panel(parent); imp.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(imp,text="Importação de cadastros",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(imp,text="Para importar PDF, Word, planilhas, CSV ou vários arquivos de uma vez, use a área de importação com prévia e confirmação.",text_color=self.MUTED,font=("Arial",11),wraplength=900,justify="left").pack(anchor="w",padx=20,pady=(0,12))
        ctk.CTkButton(imp,text="Abrir importação de documentos",command=lambda:self.show_page("Importar arquivos"),height=38,width=250).pack(anchor="w",padx=18,pady=(0,16))
        backup=self.panel(parent); backup.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(backup,text="Backup do banco de dados",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(backup,text="Inclui cadastros, histórico de empréstimos e reservas.",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=20,pady=(0,12))
        ctk.CTkButton(backup,text="⤓  Criar backup agora",command=self.backup_database,height=40,width=210).pack(anchor="w",padx=18,pady=(0,18))
        inventory=self.panel(parent); inventory.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(inventory,text="▦  Inventário físico por tombo",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(inventory,text="Passe pela estante e leia cada código de barras com um leitor USB. Cada leitura registra data/hora e condição do exemplar.",text_color=self.MUTED,font=("Arial",11),wraplength=900,justify="left").pack(anchor="w",padx=20,pady=(0,10))
        scanrow=ctk.CTkFrame(inventory,fg_color="transparent"); scanrow.pack(fill="x",padx=16,pady=(0,6))
        self.inventory_scan_var=tk.StringVar()
        self.inventory_scan_entry=ctk.CTkEntry(scanrow,textvariable=self.inventory_scan_var,placeholder_text="Escaneie ou digite o TOMBO (ex.: LIB-000123)",height=38)
        self.inventory_scan_entry.pack(side="left",fill="x",expand=True,padx=(0,8))
        self.inventory_scan_entry.bind("<Return>",lambda event:self.check_inventory_code())
        ctk.CTkButton(scanrow,text="Conferir exemplar",command=self.check_inventory_code,height=38,width=160).pack(side="right")
        self.inventory_count=ctk.CTkLabel(inventory,text="Exemplares conferidos hoje: 0",text_color=self.GREEN,font=("Arial",11,"bold"))
        self.inventory_count.pack(anchor="w",padx=20,pady=(0,6))
        self.inventory_status=ctk.CTkLabel(inventory,text="A conferência física não altera automaticamente a condição do livro.",text_color=self.MUTED,font=("Arial",10))
        self.inventory_status.pack(anchor="w",padx=20,pady=(0,8))
        self.inventory_table=self.table(inventory,("Tombo","Título","Conferido em","Condição"),height=5)
        self.inventory_table.pack(fill="both",expand=True,padx=12,pady=(0,12))
        self.report_status=ctk.CTkLabel(parent,text="Os relatórios são gerados neste computador.",text_color=self.MUTED,font=("Arial",11))
        self.report_status.pack(anchor="w",pady=8)
        policy=self.panel(parent); policy.pack(fill="x",pady=(10,18))
        ctk.CTkLabel(policy,text="Política de circulação",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=20,pady=(18,4))
        ctk.CTkLabel(policy,text="Defina prazos e limites conforme o regulamento da escola.",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=20,pady=(0,12))
        self.policy_vars={key:tk.StringVar(value=str(get_setting_int(key,default))) for key,default in [("loan_days",14),("max_active_loans",5),("max_renewals",2)]}
        fields=ctk.CTkFrame(policy,fg_color="transparent"); fields.pack(fill="x",padx=16,pady=(0,8))
        for label,key in [("DIAS POR EMPRÉSTIMO","loan_days"),("LIMITE DE LIVROS POR LEITOR","max_active_loans"),("MÁXIMO DE RENOVAÇÕES","max_renewals")]:
            cell=ctk.CTkFrame(fields,fg_color="transparent"); cell.pack(side="left",fill="x",expand=True,padx=4)
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",9,"bold")).pack(anchor="w",pady=(0,5))
            ctk.CTkEntry(cell,textvariable=self.policy_vars[key],height=36).pack(fill="x")
        ctk.CTkButton(policy,text="Salvar política",command=self.save_policies,height=38,width=170).pack(anchor="w",padx=20,pady=(0,16))

    def check_inventory_code(self):
        code=self.inventory_scan_var.get().strip().upper()
        if not code:
            return
        with connect() as c:
            book=c.execute("SELECT id,title,accession_code,condition_status FROM books WHERE accession_code=?",(code,)).fetchone()
            if not book:
                self.inventory_status.configure(text="Tombo não localizado: "+code, text_color=self.RED)
                self.inventory_scan_var.set("")
                self.inventory_scan_entry.focus_set()
                return
            stamp=datetime.now().isoformat(timespec="seconds")
            c.execute("UPDATE books SET last_inventory_at=? WHERE id=?",(stamp,book["id"]))
            c.execute("INSERT INTO inventory_scans(book_id,scanned_at,condition_status) VALUES(?,?,?)",
                      (book["id"],stamp,book["condition_status"] or "Bom"))
        log_action("CONFERENCIA_INVENTARIO","livro",book["id"],"Tombo "+code+" conferido fisicamente")
        self.inventory_scan_var.set("")
        self.inventory_status.configure(text="Conferido: "+book["title"]+" · "+code, text_color=self.GREEN)
        self.refresh()
        self.inventory_scan_entry.focus_set()
        if book["condition_status"]=="Extraviado":
            messagebox.showwarning("Condição do exemplar","O tombo foi encontrado fisicamente, mas ainda está marcado como Extraviado. Atualize a condição no catálogo após inspeção.")

    def save_policies(self):
        try:
            days=int(self.policy_vars["loan_days"].get())
            maximum=int(self.policy_vars["max_active_loans"].get())
            renewals=int(self.policy_vars["max_renewals"].get())
            if not 1<=days<=90 or not 1<=maximum<=20 or not 0<=renewals<=5:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Política inválida","Use dias entre 1 e 90, limite entre 1 e 20 livros e renovações entre 0 e 5.")
            return
        with connect() as c:
            c.executemany("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          [("loan_days",str(days)),("max_active_loans",str(maximum)),("max_renewals",str(renewals))])
        log_action("CONFIGURACAO","sistema",None,"Política de circulação atualizada")
        self.report_status.configure(text="Política salva. Novos empréstimos e renovações usarão o novo prazo.",text_color=self.GREEN)
        messagebox.showinfo("Política de circulação","Configurações salvas.")

    def export_report(self,kind):
        reports={
            "books":("acervo.csv","SELECT accession_code AS Tombo,title AS Titulo,author AS Autor,isbn AS ISBN,column_code AS Coluna,shelf_row AS Fileira,category AS Genero,condition_status AS Condicao,last_inventory_at AS Ultima_Conferencia FROM books ORDER BY title,accession_code"),
            "readers":("leitores_turmas.csv","SELECT name AS Nome,registration AS Matricula,class_name AS Turma,phone AS Telefone,reading_goal AS Meta_Anual FROM readers ORDER BY class_name,name"),
            "loans":("emprestimos_atrasos.csv","SELECT l.id AS ID,b.accession_code AS Tombo,b.title AS Livro,r.name AS Leitor,r.registration AS Matricula,r.class_name AS Turma,l.loan_date AS Emprestimo,l.due_date AS Devolucao_Prevista,l.returned_at AS Devolvido,l.renewals AS Renovacoes,CASE WHEN l.returned_at IS NOT NULL THEN 'Devolvido' WHEN l.due_date<? THEN 'ATRASADO' ELSE 'Em aberto' END AS Status FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.returned_at IS NULL DESC,l.due_date"),
            "reservations":("reservas.csv","SELECT q.id AS ID,b.accession_code AS Tombo,b.title AS Livro,r.name AS Leitor,r.registration AS Matricula,q.request_date AS Solicitada,q.status AS Status FROM reservations q JOIN books b ON b.id=q.book_id JOIN readers r ON r.id=q.reader_id ORDER BY q.request_date,q.id"),
            "activity":("historico_acoes.csv","SELECT action AS Acao,entity_type AS Tipo,entity_id AS Registro,description AS Descricao,created_at AS Data_Hora FROM activity_log ORDER BY id DESC"),
            "inventory":("inventario_fisico.csv","SELECT b.accession_code AS Tombo,b.title AS Titulo,b.author AS Autor,b.column_code AS Coluna,b.shelf_row AS Fileira,b.category AS Genero,b.condition_status AS Condicao,b.last_inventory_at AS Ultima_Conferencia FROM books b ORDER BY b.title,b.accession_code"),
        }
        default,query=reports[kind]
        path=filedialog.asksaveasfilename(title="Exportar relatório",defaultextension=".csv",initialfile=default,filetypes=[("CSV","*.csv")])
        if not path: return
        with connect() as c:
            cursor=c.execute(query,(date.today().isoformat(),)) if kind=="loans" else c.execute(query)
            rows=cursor.fetchall(); headers=[d[0] for d in cursor.description]
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            writer=csv.writer(f,delimiter=";"); writer.writerow(headers)
            writer.writerows([tuple(row) for row in rows])
        self.report_status.configure(text="Relatório exportado: "+path,text_color=self.GREEN)

    def import_documents_ui(self,parent):
        self.section_title(parent,"Importação inteligente de documentos","Cadastre livros ou alunos a partir de listas que a escola já tem. Primeiro leia e confira a prévia; só depois grave os registros.")
        intro=self.panel(parent); intro.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(intro,text="1. Escolha o tipo de cadastro",text_color=self.INK,font=("Arial",15,"bold")).pack(anchor="w",padx=18,pady=(16,4))
        controls=ctk.CTkFrame(intro,fg_color="transparent"); controls.pack(fill="x",padx=14,pady=(4,12))
        self.doc_import_kind=tk.StringVar(value="Livros")
        ctk.CTkOptionMenu(controls,values=["Livros","Alunos / leitores"],variable=self.doc_import_kind,width=200,height=38).pack(side="left",padx=4)
        ctk.CTkButton(controls,text="Selecionar arquivos…",command=self.choose_document_files,height=38,width=180).pack(side="left",padx=4)
        ctk.CTkButton(controls,text="Ler e montar prévia",command=self.analyze_document_files,height=38,width=180,fg_color=self.BLUE,hover_color="#3453D5").pack(side="left",padx=4)
        self.doc_import_files_label=ctk.CTkLabel(intro,text="Nenhum arquivo selecionado.",text_color=self.MUTED,font=("Arial",11),wraplength=950,justify="left")
        self.doc_import_files_label.pack(anchor="w",padx=18,pady=(0,14))
        formats=self.panel(parent); formats.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(formats,text="Formatos aceitos",text_color=self.INK,font=("Arial",14,"bold")).pack(anchor="w",padx=18,pady=(14,4))
        ctk.CTkLabel(formats,text="PDF com texto/tabelas · Word DOCX · Word DOC (com LibreOffice instalado) · Excel XLSX/XLS/ODS · OpenDocument ODT · CSV · TSV · TXT · JSON",text_color=self.MUTED,font=("Arial",11),wraplength=950,justify="left").pack(anchor="w",padx=18,pady=(0,8))
        ctk.CTkLabel(formats,text="Dica: cabeçalhos como Título, Autor, ISBN, Tombo, Gênero, Nome, Matrícula e Turma ajudam o Libris a identificar os campos automaticamente. PDFs digitalizados como imagem precisam de OCR antes da importação.",text_color=self.MUTED,font=("Arial",11),wraplength=950,justify="left").pack(anchor="w",padx=18,pady=(0,14))
        preview=self.panel(parent); preview.pack(fill="both",expand=True,pady=(0,12))
        ctk.CTkLabel(preview,text="2. Confira os dados antes de importar",text_color=self.INK,font=("Arial",15,"bold")).pack(anchor="w",padx=18,pady=(16,4))
        self.doc_import_summary=ctk.CTkLabel(preview,text="A prévia aparecerá aqui após a leitura dos arquivos.",text_color=self.MUTED,font=("Arial",11),wraplength=950,justify="left")
        self.doc_import_summary.pack(anchor="w",padx=18,pady=(0,10))
        self.doc_import_table=self.table(preview,("Arquivo","Resultado","Título / Nome","Autor","ISBN","Matrícula","Turma","Gênero","Coluna / Fileira","Tombo"),height=10)
        self.doc_import_table.pack(fill="both",expand=True,padx=12,pady=(0,12))
        actions=ctk.CTkFrame(parent,fg_color="transparent"); actions.pack(fill="x",pady=(0,12))
        ctk.CTkButton(actions,text="Importar registros válidos",command=self.commit_document_import,height=42,width=230,fg_color=self.GREEN,hover_color="#107B5A").pack(side="right")
        ctk.CTkButton(actions,text="Limpar prévia",command=self.clear_document_import,height=42,width=135,fg_color="#E8ECF4",hover_color="#DCE2ED",text_color=self.INK).pack(side="right",padx=8)
        self._document_paths=[]
        self._document_records=[]

    def choose_document_files(self):
        filetypes=[
            ("Todos os formatos aceitos","*.pdf *.docx *.doc *.csv *.tsv *.txt *.xlsx *.xls *.ods *.odt *.json"),
            ("PDF","*.pdf"),("Word","*.docx *.doc"),("Excel e planilhas","*.xlsx *.xls *.ods"),
            ("CSV e texto","*.csv *.tsv *.txt"),("JSON","*.json"),("Todos os arquivos","*.*")
        ]
        chosen=filedialog.askopenfilenames(title="Selecionar listas de livros ou alunos",filetypes=filetypes)
        if chosen:
            self._document_paths=list(chosen)
            self.doc_import_files_label.configure(text="Arquivos selecionados (%d): %s" % (len(chosen), " · ".join(Path(p).name for p in chosen)),text_color=self.INK)

    def _document_duplicate_status(self,record,kind,seen):
        with connect() as c:
            if kind=="books":
                accession=(record.get("accession_code") or "").strip().upper()
                if accession:
                    token=("tombo",accession)
                    if token in seen or c.execute("SELECT 1 FROM books WHERE accession_code=?",(accession,)).fetchone():
                        return "Duplicado"
                    seen.add(token)
                return "Pronto" if accession else "Pronto · tombo automático"
            registration=(record.get("registration") or "").strip()
            if registration:
                token=("matricula",registration.casefold())
                if token in seen or c.execute("SELECT 1 FROM readers WHERE registration=?",(registration,)).fetchone():
                    return "Duplicado"
                seen.add(token)
                return "Pronto"
            return "Pronto · matrícula automática"

    def analyze_document_files(self):
        if not self._document_paths:
            messagebox.showwarning("Importação","Selecione um ou mais arquivos antes de montar a prévia.")
            return
        kind="books" if self.doc_import_kind.get()=="Livros" else "readers"
        new_records=[]; warnings=[]; errors=[]
        seen=set()
        for path in self._document_paths:
            try:
                records,notes=parse_document(path,kind)
                warnings.extend([Path(path).name+": "+note for note in notes])
                for record in records:
                    item=dict(record)
                    item["_source"]=Path(path).name
                    item["_kind"]=kind
                    item["_status"]=self._document_duplicate_status(item,kind,seen)
                    new_records.append(item)
            except Exception as exc:
                errors.append(Path(path).name+": "+str(exc))
        self._document_records=new_records
        self._refresh_document_preview()
        ready=sum(1 for item in new_records if not item["_status"].startswith("Duplicado"))
        duplicate=len(new_records)-ready
        summary="Tipo: %s · reconhecidos: %d · prontos para importar: %d · duplicados: %d." % (
            "Livros" if kind=="books" else "Alunos / leitores",len(new_records),ready,duplicate)
        details=(warnings+errors)[:12]
        if details:
            summary+="\n\nObservações:\n"+"\n".join("• "+msg for msg in details)
            if len(warnings)+len(errors)>12:
                summary+="\n… e mais %d observação(ões)." % (len(warnings)+len(errors)-12)
        self.doc_import_summary.configure(text=summary,text_color=self.RED if errors else self.MUTED)
        if not new_records:
            messagebox.showwarning("Importação","Nenhum registro foi reconhecido. Confira se o documento contém tabelas/texto legível e se os cabeçalhos identificam os campos.")

    def _refresh_document_preview(self):
        if not hasattr(self,"doc_import_table"):
            return
        kind="books" if self.doc_import_kind.get()=="Livros" else "readers"
        rows=[]
        for item in self._document_records[:500]:
            if kind=="books":
                rows.append((item.get("_source",""),item.get("_status",""),item.get("title",""),item.get("author",""),item.get("isbn",""),"", "",item.get("category",""),"%s / %s"%(item.get("column_code","") or "—",item.get("shelf_row","") or "—"),item.get("accession_code","") or "Automático"))
            else:
                rows.append((item.get("_source",""),item.get("_status",""),item.get("name",""),"","",item.get("registration","") or "Automática",item.get("class_name",""),"", "", ""))
        self.fill(self.doc_import_table,rows)
        if len(self._document_records)>500:
            self.doc_import_summary.configure(text=self.doc_import_summary.cget("text")+"\nA tabela mostra as primeiras 500 linhas; a importação considera todos os registros válidos.")

    def clear_document_import(self):
        self._document_records=[]
        self._document_paths=[]
        self.doc_import_files_label.configure(text="Nenhum arquivo selecionado.",text_color=self.MUTED)
        self.doc_import_summary.configure(text="A prévia foi limpa. Selecione arquivos para começar.",text_color=self.MUTED)
        self.fill(self.doc_import_table,[])

    def commit_document_import(self):
        if not self._document_records:
            messagebox.showwarning("Importação","Primeiro selecione arquivos e monte a prévia.")
            return
        kind="books" if self.doc_import_kind.get()=="Livros" else "readers"
        if any(item.get("_kind")!=kind for item in self._document_records):
            messagebox.showwarning("Tipo de cadastro alterado","Você mudou entre livros e alunos depois de ler os arquivos. Limpe a prévia e leia os arquivos novamente.")
            return
        ready=[item for item in self._document_records if not item.get("_status","").startswith("Duplicado")]
        if not ready:
            messagebox.showinfo("Importação","Não existem registros novos para importar.")
            return
        if not messagebox.askyesno("Confirmar importação","Importar %d registro(s) válidos? Os registros com tombo ou matrícula duplicados serão ignorados."%len(ready)):
            return
        imported=0; skipped=0; issues=[]
        try:
            with connect() as c:
                for item in ready:
                    try:
                        if kind=="books":
                            title=(item.get("title") or "").strip()
                            if not title:
                                skipped+=1; continue
                            accession=(item.get("accession_code") or "").strip().upper()
                            if accession and c.execute("SELECT 1 FROM books WHERE accession_code=?",(accession,)).fetchone():
                                skipped+=1; continue
                            if not accession:
                                next_id=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM books").fetchone()[0]
                                accession="LIB-%06d"%next_id
                                while c.execute("SELECT 1 FROM books WHERE accession_code=?",(accession,)).fetchone():
                                    next_id+=1; accession="LIB-%06d"%next_id
                            column=(item.get("column_code") or "").strip().upper()
                            if column and (not column.isalpha() or len(column)>3):
                                column=""
                                issues.append("Coluna inválida em "+title+"; foi deixada vazia.")
                            row_value=(item.get("shelf_row") or "").strip()
                            try: shelf_row=int(float(row_value)) if row_value else None
                            except (ValueError,TypeError): shelf_row=None
                            if shelf_row is not None and shelf_row<1: shelf_row=None
                            condition=(item.get("condition_status") or "Bom").strip()
                            normalized_condition=unicodedata.normalize("NFKD",condition.lower())
                            normalized_condition="".join(ch for ch in normalized_condition if not unicodedata.combining(ch))
                            if normalized_condition in ("extraviado","perdido","perdida"): condition="Extraviado"
                            elif normalized_condition in ("em manutencao","manutencao","reparo"): condition="Em manutenção"
                            else: condition="Bom"
                            c.execute("""INSERT INTO books(title,author,isbn,category,column_code,shelf_row,accession_code,condition_status)
                                VALUES(?,?,?,?,?,?,?,?)""",(title,(item.get("author") or "").strip(),(item.get("isbn") or "").strip() or None,(item.get("category") or "").strip(),column,shelf_row,accession,condition))
                            book_id=c.execute("SELECT id FROM books WHERE accession_code=?",(accession,)).fetchone()[0]
                            log_action("IMPORTACAO","livro",book_id,"Exemplar importado de "+item.get("_source","documento"))
                        else:
                            name=(item.get("name") or "").strip()
                            if not name:
                                skipped+=1; continue
                            registration=(item.get("registration") or "").strip()
                            if registration and c.execute("SELECT 1 FROM readers WHERE registration=?",(registration,)).fetchone():
                                skipped+=1; continue
                            if not registration:
                                number=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM readers").fetchone()[0]
                                registration="ALU-AUTO-%06d"%number
                                while c.execute("SELECT 1 FROM readers WHERE registration=?",(registration,)).fetchone():
                                    number+=1; registration="ALU-AUTO-%06d"%number
                            try: goal=int(float(item.get("reading_goal") or 12))
                            except (ValueError,TypeError): goal=12
                            goal=min(500,max(1,goal))
                            c.execute("INSERT INTO readers(name,registration,class_name,phone,reading_goal) VALUES(?,?,?,?,?)",
                                (name,registration,(item.get("class_name") or "").strip(),(item.get("phone") or "").strip(),goal))
                            reader_id=c.execute("SELECT id FROM readers WHERE registration=?",(registration,)).fetchone()[0]
                            log_action("IMPORTACAO","leitor",reader_id,"Leitor importado de "+item.get("_source","documento"))
                        imported+=1
                    except sqlite3.IntegrityError as exc:
                        skipped+=1
                        issues.append(item.get("_source","Documento")+": registro ignorado ("+str(exc)+").")
            self.refresh()
            self.doc_import_summary.configure(text="Importação concluída. Importados: %d · Ignorados por duplicidade ou dados inválidos: %d%s"%(imported,skipped,("\n"+ "\n".join(issues[:8])) if issues else ""),text_color=self.GREEN)
            messagebox.showinfo("Importação concluída","Importados: %d\nIgnorados: %d\n\nOs dados já estão no banco local do Libris."%(imported,skipped))
            self._document_records=[]
            self.fill(self.doc_import_table,[])
        except sqlite3.Error as exc:
            messagebox.showerror("Importação","Erro ao gravar os registros: "+str(exc))

    def import_csv(self,kind):
        path=filedialog.askopenfilename(title="Importar dados CSV",filetypes=[("Arquivos CSV","*.csv"),("Todos os arquivos","*.*")])
        if not path: return
        imported=0; skipped=0; failures=0
        def key(value):
            return "".join(ch for ch in unicodedata.normalize("NFKD",str(value or "").strip().lower()) if ch.isalnum())
        def get_value(row,*names):
            normalized={key(k):v for k,v in row.items()}
            for name in names:
                value=normalized.get(key(name))
                if value is not None and str(value).strip():
                    return str(value).strip()
            return ""
        try:
            with open(path,"r",newline="",encoding="utf-8-sig") as f:
                sample=f.read(4096); f.seek(0)
                try: dialect=csv.Sniffer().sniff(sample,delimiters=";,\t,")
                except csv.Error: dialect=csv.excel; dialect.delimiter=";"
                reader=csv.DictReader(f,dialect=dialect)
                with connect() as c:
                    for row in reader:
                        try:
                            if kind=="books":
                                title=get_value(row,"Título","Titulo","Title","Nome")
                                if not title:
                                    skipped+=1; continue
                                isbn=get_value(row,"ISBN","ISBN/EAN") or None
                                accession=get_value(row,"Tombo","Código","Codigo","Accession Code","Código de barras").upper()
                                if accession and c.execute("SELECT 1 FROM books WHERE accession_code=?",(accession,)).fetchone():
                                    skipped+=1; continue
                                if not accession:
                                    next_id=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM books").fetchone()[0]
                                    accession="LIB-%06d" % next_id
                                    while c.execute("SELECT 1 FROM books WHERE accession_code=?",(accession,)).fetchone():
                                        next_id+=1; accession="LIB-%06d" % next_id
                                column=get_value(row,"Coluna","Column").upper()
                                shelf_text=get_value(row,"Fileira","Prateleira","Shelf Row")
                                try: shelf_row=int(shelf_text) if shelf_text else None
                                except ValueError: shelf_row=None
                                if shelf_row is not None and shelf_row<1: shelf_row=None
                                genre=get_value(row,"Gênero","Genero","Categoria","Category")
                                status=get_value(row,"Condição","Condicao","Status","Condition") or "Bom"
                                if status not in ("Bom","Em manutenção","Extraviado"): status="Bom"
                                c.execute("""INSERT INTO books(title,author,isbn,category,column_code,shelf_row,accession_code,condition_status)
                                    VALUES(?,?,?,?,?,?,?,?)""",(title,get_value(row,"Autor","Author"),isbn,genre,column,shelf_row,accession,status))
                                imported+=1
                            else:
                                name=get_value(row,"Nome","Nome completo","Name")
                                registration=get_value(row,"Matrícula","Matricula","Registration","ID do leitor")
                                if not name or not registration or c.execute("SELECT 1 FROM readers WHERE registration=?",(registration,)).fetchone():
                                    skipped+=1; continue
                                try: goal=int(get_value(row,"Meta anual","Meta","Reading Goal") or "12")
                                except ValueError: goal=12
                                goal=min(500,max(1,goal))
                                c.execute("""INSERT INTO readers(name,registration,class_name,phone,reading_goal)
                                    VALUES(?,?,?,?,?)""",(name,registration,get_value(row,"Turma","Ano","Class"),get_value(row,"Telefone","Phone"),goal))
                                imported+=1
                        except (sqlite3.IntegrityError,ValueError,TypeError):
                            skipped+=1
                            failures+=1
            log_action("IMPORTACAO",kind,None,"Arquivo "+Path(path).name+": "+str(imported)+" importados, "+str(skipped)+" ignorados")
            self.refresh()
            messagebox.showinfo("Importação concluída","Importados: %d\nIgnorados: %d\nArquivo: %s" % (imported,skipped,Path(path).name))
            if hasattr(self,"report_status"):
                self.report_status.configure(text="Importação concluída: %d registros importados, %d ignorados." % (imported,skipped),text_color=self.GREEN)
        except (OSError,csv.Error,sqlite3.Error) as exc:
            messagebox.showerror("Importação","Não foi possível importar o arquivo: "+str(exc))

    def backup_database(self):
        default="libris-backup-"+date.today().isoformat()+".db"
        path=filedialog.asksaveasfilename(title="Salvar backup do Libris",defaultextension=".db",initialfile=default,filetypes=[("Banco SQLite","*.db")])
        if not path: return
        try:
            source=sqlite3.connect(DB); target=sqlite3.connect(path)
            source.backup(target); target.close(); source.close()
            self.report_status.configure(text="Backup criado com sucesso: "+path,text_color=self.GREEN)
            messagebox.showinfo("Backup","Cópia de segurança salva com sucesso.")
        except Exception as exc:
            messagebox.showerror("Backup","Não foi possível criar o backup: "+str(exc))

    def fill(self,t,rows):
        t.delete(*t.get_children())
        for row in rows: t.insert("","end",values=tuple(row))

    def refresh(self):
        with connect() as c:
            term=self.book_search_var.get().strip() if hasattr(self,"book_search_var") else ""
            pattern="%"+term+"%"
            b=c.execute("""SELECT b.id,COALESCE(b.accession_code,''),b.title,b.author,COALESCE(b.isbn,''),
                COALESCE(b.column_code,''),COALESCE(CAST(b.shelf_row AS TEXT),''),COALESCE(b.category,''),
                CASE WHEN COALESCE(b.condition_status,'Bom')!='Bom' THEN b.condition_status
                     WHEN EXISTS(SELECT 1 FROM loans l WHERE l.book_id=b.id AND l.returned_at IS NULL) THEN 'Emprestado'
                     ELSE 'Disponível' END,COALESCE(substr(b.last_inventory_at,1,16),'Nunca conferido')
                FROM books b
                WHERE ?='' OR b.title LIKE ? OR b.author LIKE ? OR COALESCE(b.isbn,'') LIKE ?
                    OR COALESCE(b.accession_code,'') LIKE ? OR COALESCE(b.category,'') LIKE ?
                    OR COALESCE(b.column_code,'') LIKE ? OR COALESCE(CAST(b.shelf_row AS TEXT),'') LIKE ?
                ORDER BY b.title,b.accession_code""",(term,pattern,pattern,pattern,pattern,pattern,pattern,pattern)).fetchall()
            r=c.execute("SELECT id,name,registration,class_name,phone,reading_goal FROM readers ORDER BY class_name,name").fetchall()
            l=c.execute("""SELECT l.id,b.title,r.name,l.loan_date,l.due_date,COALESCE(l.renewals,0),
                CASE WHEN l.returned_at IS NOT NULL THEN 'Devolvido' WHEN l.due_date<? THEN 'ATRASADO' ELSE 'Em aberto' END
                FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id
                ORDER BY l.returned_at IS NULL DESC,l.due_date""",(date.today().isoformat(),)).fetchall()
            counts=[c.execute("SELECT COUNT(*) FROM books").fetchone()[0],c.execute("SELECT COUNT(*) FROM readers").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL AND due_date<?",(date.today().isoformat(),)).fetchone()[0]]
            rr=c.execute("""SELECT r.name,COALESCE(r.reading_goal,12) goal,COUNT(l.id) n FROM readers r
                LEFT JOIN loans l ON l.reader_id=r.id AND l.returned_at IS NOT NULL AND substr(l.returned_at,1,4)=?
                GROUP BY r.id ORDER BY n DESC,r.name LIMIT 10""",(str(date.today().year),)).fetchall()
            rb=c.execute("SELECT b.title,COUNT(*) n FROM loans l JOIN books b ON b.id=l.book_id GROUP BY b.title ORDER BY n DESC,b.title LIMIT 10").fetchall()
            q=c.execute("""SELECT q.id,COALESCE(b.accession_code,''),b.title,r.name,r.registration,q.request_date,q.status
                FROM reservations q JOIN books b ON b.id=q.book_id JOIN readers r ON r.id=q.reader_id
                ORDER BY CASE q.status WHEN 'Disponível para retirada' THEN 0 WHEN 'Na fila' THEN 1 ELSE 2 END,q.request_date,q.id""").fetchall()
            inventory=c.execute("""SELECT b.accession_code,b.title,i.scanned_at,i.condition_status FROM inventory_scans i
                JOIN books b ON b.id=i.book_id ORDER BY i.id DESC LIMIT 20""").fetchall()
            checked_today=c.execute("SELECT COUNT(DISTINCT book_id) FROM inventory_scans WHERE substr(scanned_at,1,10)=?",(date.today().isoformat(),)).fetchone()[0]
        self.fill(self.btable,b); self.fill(self.rtable,r); self.fill(self.ltable,l)
        self.m_books.configure(text=str(counts[0])); self.m_readers.configure(text=str(counts[1]))
        self.m_loans.configure(text=str(counts[2])); self.m_late.configure(text=str(counts[3]))
        self.fill(self.rr,[(f"{i+1:02}",x["name"],str(x["n"])+"/"+str(x["goal"])) for i,x in enumerate(rr)])
        self.fill(self.rb,[(f"{i+1:02}",x["title"],x["n"]) for i,x in enumerate(rb)])
        self.fill(self.recent_table,[(x[1],x[2],x[4],x[6]) for x in l[:8]])
        if hasattr(self,"qtable"):
            self.fill(self.qtable,q)
        if hasattr(self,"inventory_table"):
            self.fill(self.inventory_table,inventory)
            self.inventory_count.configure(text="Exemplares conferidos hoje: "+str(checked_today))

if __name__=="__main__":
    init_db()
    Libris().mainloop()
