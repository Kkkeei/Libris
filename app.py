import os, sys, sqlite3, socket, threading, webbrowser
from pathlib import Path
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
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
        CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY,title TEXT NOT NULL,author TEXT DEFAULT '',isbn TEXT UNIQUE,category TEXT DEFAULT '',column_code TEXT DEFAULT '',shelf_row INTEGER);
        CREATE TABLE IF NOT EXISTS readers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,registration TEXT UNIQUE,phone TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id),reader_id INTEGER NOT NULL REFERENCES readers(id),loan_date TEXT NOT NULL,due_date TEXT NOT NULL,returned_at TEXT);
        """)
        # Migração segura para bancos criados em versões anteriores.
        columns = {row["name"] for row in c.execute("PRAGMA table_info(books)").fetchall()}
        if "column_code" not in columns:
            c.execute("ALTER TABLE books ADD COLUMN column_code TEXT DEFAULT ''")
        if "shelf_row" not in columns:
            c.execute("ALTER TABLE books ADD COLUMN shelf_row INTEGER")
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
    <div class=wrap><h1>📚 Libris</h1><p>Empréstimo pelo celular na mesma rede Wi-Fi.</p><div class=card><h3>Novo empréstimo</h3><form id=f><label>ISBN do livro</label><input id=isbn required><label>Matrícula do leitor</label><input id=reg required><label>Devolução prevista</label><input id=due type=date required><button>Registrar empréstimo</button></form><p id=msg></p></div><div class=card><h3>Pesquisar livro</h3><input id=q placeholder="Título, autor ou ISBN"><button onclick=searchBook()>Pesquisar</button><div id=results></div></div></div>
    <script>document.getElementById('due').value=new Date(Date.now()+12096e5).toISOString().slice(0,10);document.getElementById('f').onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/mobile-loan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({isbn:document.getElementById('isbn').value.trim(),registration:document.getElementById('reg').value.trim(),due:document.getElementById('due').value})});let j=await r.json();let m=document.getElementById('msg');m.className=j.ok?'ok':'err';m.textContent=j.message};async function searchBook(){let r=await fetch('/api/book?q='+encodeURIComponent(document.getElementById('q').value));let j=await r.json();document.getElementById('results').innerHTML=j.books.length?j.books.map(b=>'<p><b>'+b.title+'</b><br>'+b.author+' · ISBN '+(b.isbn||'—')+'</p>').join(''):'Nenhum livro encontrado.'}</script></html>"""
    @web.get("/mobile")
    def mobile(): return render_template_string(page)
    @web.get("/api/book")
    def books_search():
        q=request.args.get("q","")
        with connect() as c: rows=c.execute("SELECT title,author,isbn FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? ORDER BY title LIMIT 30",("%"+q+"%","%"+q+"%","%"+q+"%")).fetchall()
        return jsonify(books=[dict(r) for r in rows])
    @web.post("/api/mobile-loan")
    def mobile_loan():
        d=request.get_json(silent=True) or {}; isbn=(d.get("isbn") or "").strip(); reg=(d.get("registration") or "").strip()
        try:
            due=date.fromisoformat(d.get("due",""))
            if due<date.today(): raise ValueError()
        except ValueError: return jsonify(ok=False,message="Informe uma data de devolução válida."),400
        with connect() as c:
            b=c.execute("SELECT * FROM books WHERE isbn=?",(isbn,)).fetchone(); r=c.execute("SELECT * FROM readers WHERE registration=?",(reg,)).fetchone()
            if not b: return jsonify(ok=False,message="ISBN não encontrado."),404
            if not r: return jsonify(ok=False,message="Matrícula não encontrada."),404
            if c.execute("SELECT 1 FROM loans WHERE book_id=? AND returned_at IS NULL",(b["id"],)).fetchone(): return jsonify(ok=False,message="Este livro já está emprestado."),409
            c.execute("INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)",(b["id"],r["id"],date.today().isoformat(),due.isoformat()))
        return jsonify(ok=True,message="Empréstimo registrado para "+r["name"]+".")
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
        navs=[("Visão geral","⌂"),("Livros","▤"),("Leitores","♙"),("Empréstimos","⇄"),("Ranking","✦")]
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
        self.pages["Ranking"]=ctk.CTkFrame(self.content,fg_color="transparent")
        self.rank_ui(self.pages["Ranking"])

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
        t.configure(yscrollcommand=sy.set)
        t.pack(side="left",fill="both",expand=True)
        sy.pack(side="right",fill="y")
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
        ctk.CTkButton(inner,text=button,height=39,corner_radius=9,fg_color=self.BLUE,hover_color="#3453D5",font=("Arial",11,"bold"),command=cmd,width=150).pack(side="left",pady=(22,0))
        return card

    def book_ui(self,parent):
        self.section_title(parent,"Catálogo de livros","Cadastre o livro e informe onde ele fica no acervo.")
        self.bv=[tk.StringVar() for _ in range(6)]
        card=self.panel(parent); card.pack(fill="x",pady=(0,16))
        inner=ctk.CTkFrame(card,fg_color="transparent"); inner.pack(fill="x",padx=18,pady=16)
        row1=ctk.CTkFrame(inner,fg_color="transparent"); row1.pack(fill="x",pady=(0,10))
        for label,var in [("TÍTULO",self.bv[0]),("AUTOR",self.bv[1]),("ISBN / CÓDIGO",self.bv[2])]:
            cell=ctk.CTkFrame(row1,fg_color="transparent"); cell.pack(side="left",fill="x",expand=True,padx=(0,10))
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",10,"bold")).pack(anchor="w",pady=(0,5))
            ctk.CTkEntry(cell,textvariable=var,height=38,corner_radius=9,border_color="#DDE3EE",fg_color="#FBFCFE",text_color=self.INK).pack(fill="x")
        row2=ctk.CTkFrame(inner,fg_color="transparent"); row2.pack(fill="x")
        for label,var,placeholder in [("COLUNA (LETRA)",self.bv[3],"Ex.: A"),("FILEIRA (NÚMERO)",self.bv[4],"Ex.: 3"),("GÊNERO",self.bv[5],"Ex.: Romance")]:
            cell=ctk.CTkFrame(row2,fg_color="transparent"); cell.pack(side="left",fill="x",expand=True,padx=(0,10))
            ctk.CTkLabel(cell,text=label,text_color=self.MUTED,font=("Arial",10,"bold")).pack(anchor="w",pady=(0,5))
            ctk.CTkEntry(cell,textvariable=var,placeholder_text=placeholder,height=38,corner_radius=9,border_color="#DDE3EE",fg_color="#FBFCFE",text_color=self.INK).pack(fill="x")
        ctk.CTkButton(row2,text="＋  Adicionar livro",height=38,corner_radius=9,fg_color=self.BLUE,hover_color="#3453D5",font=("Arial",11,"bold"),command=self.add_book,width=155).pack(side="left",pady=(22,0))
        self.btable=self.table(parent,("ID","Título","Autor","ISBN","Coluna","Fileira","Gênero","Situação"),height=11)
        self.btable.pack(fill="both",expand=True)

    def reader_ui(self,parent):
        self.section_title(parent,"Leitores","Gerencie o cadastro de pessoas que utilizam a biblioteca.")
        self.rv=[tk.StringVar() for _ in range(3)]
        self.form_card(parent,[("NOME COMPLETO",self.rv[0]),("MATRÍCULA",self.rv[1]),("TELEFONE",self.rv[2])],"＋  Adicionar",self.add_reader)
        self.rtable=self.table(parent,("ID","Nome","Matrícula","Telefone"),height=14)
        self.rtable.pack(fill="both",expand=True)

    def loan_ui(self,parent):
        self.section_title(parent,"Empréstimos","Registre retiradas, acompanhe prazos e confirme devoluções.")
        self.lv=[tk.StringVar(),tk.StringVar(),tk.StringVar(value=(date.today()+timedelta(days=14)).isoformat())]
        self.form_card(parent,[("ISBN DO LIVRO",self.lv[0]),("MATRÍCULA DO LEITOR",self.lv[1]),("DEVOLUÇÃO (AAAA-MM-DD)",self.lv[2])],"＋  Registrar empréstimo",self.add_loan)
        actions=ctk.CTkFrame(parent,fg_color="transparent"); actions.pack(fill="x",pady=(0,10))
        ctk.CTkLabel(actions,text="Histórico de empréstimos",text_color=self.INK,font=("Arial",15,"bold")).pack(side="left")
        ctk.CTkButton(actions,text="✓  Marcar devolução",height=34,corner_radius=9,fg_color="#E3F5EE",hover_color="#C8EBDD",text_color="#117452",command=self.return_loan).pack(side="right")
        self.ltable=self.table(parent,("ID","Livro","Leitor","Empréstimo","Devolução prevista","Status"),height=11)
        self.ltable.pack(fill="both",expand=True)

    def rank_ui(self,parent):
        self.section_title(parent,"Ranking da biblioteca","Descubra os leitores mais ativos e os livros mais procurados.")
        grid=ctk.CTkFrame(parent,fg_color="transparent"); grid.pack(fill="both",expand=True)
        left=self.panel(grid); left.pack(side="left",fill="both",expand=True,padx=(0,10))
        right=self.panel(grid); right.pack(side="left",fill="both",expand=True,padx=(10,0))
        ctk.CTkLabel(left,text="🏆  Leitores mais ativos",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=18,pady=(18,3))
        ctk.CTkLabel(left,text="Empréstimos já devolvidos",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=18,pady=(0,12))
        ctk.CTkLabel(right,text="📚  Livros em destaque",text_color=self.INK,font=("Arial",16,"bold")).pack(anchor="w",padx=18,pady=(18,3))
        ctk.CTkLabel(right,text="Total de empréstimos registrados",text_color=self.MUTED,font=("Arial",11)).pack(anchor="w",padx=18,pady=(0,12))
        self.rr=self.table(left,("Posição","Leitor","Devolvidos"),height=14); self.rr.pack(fill="both",expand=True,padx=12,pady=(0,14))
        self.rb=self.table(right,("Posição","Livro","Empréstimos"),height=14); self.rb.pack(fill="both",expand=True,padx=12,pady=(0,14))

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
            messagebox.showwarning("Atenção","Informe o título.")
            return
        column=vals[3].upper()
        if column and (len(column)>3 or not column.isalpha()):
            messagebox.showwarning("Coluna inválida","Informe a coluna usando letras (ex.: A ou AB).")
            return
        try:
            shelf_row=int(vals[4]) if vals[4] else None
            if shelf_row is not None and shelf_row < 1:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Fileira inválida","Informe a fileira com um número inteiro maior que zero.")
            return
        try:
            with connect() as c:
                c.execute("INSERT INTO books(title,author,isbn,category,column_code,shelf_row) VALUES(?,?,?,?,?,?)",
                          (vals[0],vals[1],vals[2] or None,vals[5],column,shelf_row))
        except sqlite3.IntegrityError:
            messagebox.showerror("Cadastro","ISBN já cadastrado.")
            return
        [v.set("") for v in self.bv]
        self.refresh()

    def add_reader(self):
        vals=[v.get().strip() for v in self.rv]
        if not vals[0] or not vals[1]: messagebox.showwarning("Atenção","Informe nome e matrícula."); return
        try:
            with connect() as c: c.execute("INSERT INTO readers(name,registration,phone) VALUES(?,?,?)",vals)
        except sqlite3.IntegrityError: messagebox.showerror("Cadastro","Matrícula já cadastrada."); return
        [v.set("") for v in self.rv]; self.refresh()

    def add_loan(self):
        isbn,reg,due_s=[v.get().strip() for v in self.lv]
        try:
            due=date.fromisoformat(due_s)
            if due<date.today(): raise ValueError()
        except ValueError: messagebox.showwarning("Data inválida","Informe a data no formato AAAA-MM-DD."); return
        with connect() as c:
            b=c.execute("SELECT * FROM books WHERE isbn=?",(isbn,)).fetchone(); r=c.execute("SELECT * FROM readers WHERE registration=?",(reg,)).fetchone()
            if not b: messagebox.showerror("Empréstimo","ISBN não encontrado."); return
            if not r: messagebox.showerror("Empréstimo","Matrícula não encontrada."); return
            if c.execute("SELECT 1 FROM loans WHERE book_id=? AND returned_at IS NULL",(b["id"],)).fetchone(): messagebox.showerror("Empréstimo","Livro já emprestado."); return
            c.execute("INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)",(b["id"],r["id"],date.today().isoformat(),due.isoformat()))
        self.refresh(); messagebox.showinfo("Libris","Empréstimo registrado.")

    def return_loan(self):
        sel=self.ltable.selection()
        if not sel: messagebox.showwarning("Devolução","Selecione um empréstimo."); return
        lid=self.ltable.item(sel[0])["values"][0]
        with connect() as c: c.execute("UPDATE loans SET returned_at=? WHERE id=? AND returned_at IS NULL",(date.today().isoformat(),lid))
        self.refresh()

    def fill(self,t,rows):
        t.delete(*t.get_children())
        for row in rows: t.insert("","end",values=tuple(row))

    def refresh(self):
        with connect() as c:
            b=c.execute("SELECT b.id,b.title,b.author,COALESCE(b.isbn,''),COALESCE(b.column_code,''),COALESCE(CAST(b.shelf_row AS TEXT),''),b.category,CASE WHEN EXISTS(SELECT 1 FROM loans l WHERE l.book_id=b.id AND l.returned_at IS NULL) THEN 'Emprestado' ELSE 'Disponível' END FROM books b ORDER BY b.title").fetchall()
            r=c.execute("SELECT id,name,registration,phone FROM readers ORDER BY name").fetchall()
            l=c.execute("SELECT l.id,b.title,r.name,l.loan_date,l.due_date,CASE WHEN l.returned_at IS NOT NULL THEN 'Devolvido' WHEN l.due_date<? THEN 'ATRASADO' ELSE 'Em aberto' END FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.returned_at IS NULL DESC,l.due_date",(date.today().isoformat(),)).fetchall()
            counts=[c.execute("SELECT COUNT(*) FROM books").fetchone()[0],c.execute("SELECT COUNT(*) FROM readers").fetchone()[0],c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL").fetchone()[0],c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL AND due_date<?",(date.today().isoformat(),)).fetchone()[0]]
            rr=c.execute("SELECT r.name,COUNT(*) n FROM loans l JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NOT NULL GROUP BY r.id ORDER BY n DESC LIMIT 10").fetchall()
            rb=c.execute("SELECT b.title,COUNT(*) n FROM loans l JOIN books b ON b.id=l.book_id GROUP BY b.id ORDER BY n DESC LIMIT 10").fetchall()
        self.fill(self.btable,b); self.fill(self.rtable,r); self.fill(self.ltable,l)
        self.m_books.configure(text=str(counts[0])); self.m_readers.configure(text=str(counts[1])); self.m_loans.configure(text=str(counts[2])); self.m_late.configure(text=str(counts[3]))
        self.fill(self.rr,[(f"{i+1:02}",x["name"],x["n"]) for i,x in enumerate(rr)])
        self.fill(self.rb,[(f"{i+1:02}",x["title"],x["n"]) for i,x in enumerate(rb)])
        self.fill(self.recent_table,[(x[1],x[2],x[4],x[5]) for x in l[:8]])

if __name__=="__main__":
    init_db()
    Libris().mainloop()
