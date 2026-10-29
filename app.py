import os, sys, sqlite3, socket, threading, webbrowser
from pathlib import Path
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
try:
    import qrcode
    from PIL import ImageTk
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
        CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY,title TEXT NOT NULL,author TEXT DEFAULT '',isbn TEXT UNIQUE,category TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS readers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,registration TEXT UNIQUE,phone TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id),reader_id INTEGER NOT NULL REFERENCES readers(id),loan_date TEXT NOT NULL,due_date TEXT NOT NULL,returned_at TEXT);
        """)
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

class Libris(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Libris — Biblioteca"); self.geometry("1100x720"); self.minsize(850,560); self.configure(bg="#f2f5fa")
        st=ttk.Style(self); st.theme_use("clam"); st.configure("TFrame",background="#f2f5fa"); st.configure("TLabel",background="#f2f5fa",foreground="#172033",font=("Arial",10)); st.configure("Head.TLabel",font=("Arial",22,"bold")); st.configure("Treeview",rowheight=28); st.configure("Treeview.Heading",font=("Arial",10,"bold"))
        init_db(); self.web=make_web()
        if self.web: threading.Thread(target=lambda:serve(self.web,host="0.0.0.0",port=PORT,threads=4),daemon=True).start()
        self.draw()
    def draw(self):
        top=ttk.Frame(self,padding=18); top.pack(fill="x"); ttk.Label(top,text="📚 LIBRIS",style="Head.TLabel").pack(side="left"); ttk.Label(top,text="Gestão de biblioteca").pack(side="left",padx=15,pady=10)
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill="both",expand=True,padx=20,pady=(0,20))
        self.home=ttk.Frame(self.tabs,padding=18); self.tabs.add(self.home,text="Visão geral"); self.home_ui()
        self.bt=ttk.Frame(self.tabs,padding=18); self.tabs.add(self.bt,text="Livros"); self.book_ui()
        self.rt=ttk.Frame(self.tabs,padding=18); self.tabs.add(self.rt,text="Leitores"); self.reader_ui()
        self.lt=ttk.Frame(self.tabs,padding=18); self.tabs.add(self.lt,text="Empréstimos"); self.loan_ui()
        self.rk=ttk.Frame(self.tabs,padding=18); self.tabs.add(self.rk,text="Ranking"); self.rank_ui(); self.refresh()
    def table(self,parent,cols):
        f=ttk.Frame(parent); f.pack(fill="both",expand=True,pady=10); t=ttk.Treeview(f,columns=cols,show="headings")
        sy=ttk.Scrollbar(f,orient="vertical",command=t.yview); t.configure(yscrollcommand=sy.set); t.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns"); f.rowconfigure(0,weight=1); f.columnconfigure(0,weight=1)
        for col in cols: t.heading(col,text=col); t.column(col,width=135)
        return t
    def home_ui(self):
        ttk.Label(self.home,text="Painel da biblioteca",style="Head.TLabel").pack(anchor="w")
        self.stat=ttk.Label(self.home,text="",font=("Arial",14,"bold")); self.stat.pack(anchor="w",pady=16)
        url="http://"+ip_address()+":"+str(PORT)+"/mobile"
        ttk.Label(self.home,text="EMPRÉSTIMO PELO CELULAR",font=("Arial",13,"bold")).pack(anchor="w",pady=(15,4))
        ttk.Label(self.home,text="Celular e computador precisam estar na mesma rede Wi-Fi.").pack(anchor="w")
        ttk.Label(self.home,text=url,font=("Arial",11)).pack(anchor="w",pady=5)
        self.qrl=ttk.Label(self.home); self.qrl.pack(anchor="w",pady=8)
        if qrcode and ImageTk:
            self.qr=ImageTk.PhotoImage(qrcode.make(url).resize((170,170))); self.qrl.configure(image=self.qr)
        ttk.Button(self.home,text="Abrir página mobile neste computador",command=lambda:webbrowser.open("http://127.0.0.1:"+str(PORT)+"/mobile")).pack(anchor="w",pady=8)
    def book_ui(self):
        ttk.Label(self.bt,text="Catálogo de livros",style="Head.TLabel").pack(anchor="w")
        self.bv=[tk.StringVar() for _ in range(4)]; self.inputs(self.bt,[("Título",self.bv[0]),("Autor",self.bv[1]),("ISBN / código",self.bv[2]),("Categoria",self.bv[3])],"Adicionar livro",self.add_book)
        self.btable=self.table(self.bt,("ID","Título","Autor","ISBN","Categoria","Situação"))
    def reader_ui(self):
        ttk.Label(self.rt,text="Cadastro de leitores",style="Head.TLabel").pack(anchor="w")
        self.rv=[tk.StringVar() for _ in range(3)]; self.inputs(self.rt,[("Nome",self.rv[0]),("Matrícula",self.rv[1]),("Telefone",self.rv[2])],"Adicionar leitor",self.add_reader)
        self.rtable=self.table(self.rt,("ID","Nome","Matrícula","Telefone"))
    def inputs(self,parent,fields,button,cmd):
        f=ttk.Frame(parent); f.pack(fill="x",pady=12)
        for label,var in fields:
            ttk.Label(f,text=label).pack(side="left",padx=(0,4)); ttk.Entry(f,textvariable=var,width=17).pack(side="left",padx=(0,8))
        ttk.Button(f,text=button,command=cmd).pack(side="left")
    def loan_ui(self):
        ttk.Label(self.lt,text="Empréstimos e devoluções",style="Head.TLabel").pack(anchor="w")
        self.lv=[tk.StringVar(),tk.StringVar(),tk.StringVar(value=(date.today()+timedelta(days=14)).isoformat())]
        self.inputs(self.lt,[("ISBN",self.lv[0]),("Matrícula",self.lv[1]),("Devolver até AAAA-MM-DD",self.lv[2])],"Registrar empréstimo",self.add_loan)
        bar=ttk.Frame(self.lt); bar.pack(fill="x"); ttk.Button(bar,text="Devolver empréstimo selecionado",command=self.return_loan).pack(anchor="w")
        self.ltable=self.table(self.lt,("ID","Livro","Leitor","Empréstimo","Devolução prevista","Status"))
    def rank_ui(self):
        ttk.Label(self.rk,text="Ranking da biblioteca",style="Head.TLabel").pack(anchor="w")
        ttk.Label(self.rk,text="Atualizado automaticamente conforme os empréstimos registrados.").pack(anchor="w",pady=5)
        f=ttk.Frame(self.rk); f.pack(fill="both",expand=True); a=ttk.Frame(f); a.pack(side="left",fill="both",expand=True,padx=(0,8)); b=ttk.Frame(f); b.pack(side="left",fill="both",expand=True,padx=(8,0))
        ttk.Label(a,text="🏆 Leitores mais ativos",font=("Arial",13,"bold")).pack(anchor="w"); ttk.Label(b,text="📖 Livros mais emprestados",font=("Arial",13,"bold")).pack(anchor="w")
        self.rr=self.table(a,("Posição","Leitor","Devolvidos")); self.rb=self.table(b,("Posição","Livro","Empréstimos"))
    def add_book(self):
        vals=[v.get().strip() for v in self.bv]
        if not vals[0]: messagebox.showwarning("Atenção","Informe o título."); return
        try:
            with connect() as c: c.execute("INSERT INTO books(title,author,isbn,category) VALUES(?,?,?,?)",(vals[0],vals[1],vals[2] or None,vals[3]))
        except sqlite3.IntegrityError: messagebox.showerror("Cadastro","ISBN já cadastrado."); return
        [v.set("") for v in self.bv]; self.refresh()
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
            b=c.execute("SELECT b.id,b.title,b.author,COALESCE(b.isbn,''),b.category,CASE WHEN EXISTS(SELECT 1 FROM loans l WHERE l.book_id=b.id AND l.returned_at IS NULL) THEN 'Emprestado' ELSE 'Disponível' END FROM books b ORDER BY b.title").fetchall()
            r=c.execute("SELECT id,name,registration,phone FROM readers ORDER BY name").fetchall()
            l=c.execute("SELECT l.id,b.title,r.name,l.loan_date,l.due_date,CASE WHEN l.returned_at IS NOT NULL THEN 'Devolvido' WHEN l.due_date<? THEN 'ATRASADO' ELSE 'Em aberto' END FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.returned_at IS NULL DESC,l.due_date",(date.today().isoformat(),)).fetchall()
            counts=[c.execute("SELECT COUNT(*) FROM books").fetchone()[0],c.execute("SELECT COUNT(*) FROM readers").fetchone()[0],c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL").fetchone()[0],c.execute("SELECT COUNT(*) FROM loans WHERE returned_at IS NULL AND due_date<?",(date.today().isoformat(),)).fetchone()[0]]
            rr=c.execute("SELECT r.name,COUNT(*) n FROM loans l JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NOT NULL GROUP BY r.id ORDER BY n DESC LIMIT 10").fetchall()
            rb=c.execute("SELECT b.title,COUNT(*) n FROM loans l JOIN books b ON b.id=l.book_id GROUP BY b.id ORDER BY n DESC LIMIT 10").fetchall()
        self.fill(self.btable,b); self.fill(self.rtable,r); self.fill(self.ltable,l)
        self.stat.configure(text="Livros: %s     Leitores: %s     Empréstimos ativos: %s     Atrasados: %s"%tuple(counts))
        self.fill(self.rr,[(i+1,x["name"],x["n"]) for i,x in enumerate(rr)]); self.fill(self.rb,[(i+1,x["title"],x["n"]) for i,x in enumerate(rb)])

if __name__=="__main__":
    init_db()
    Libris().mainloop()
