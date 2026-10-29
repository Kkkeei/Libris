import io, os, socket, sqlite3
from pathlib import Path
from datetime import date, timedelta
from flask import Flask, request, redirect, url_for, flash, render_template_string, jsonify, send_file
import qrcode
app=Flask(__name__); app.secret_key=os.environ.get("LIBRIS_SECRET_KEY","troque-esta-chave-local")
DATA=Path(os.environ.get("LIBRIS_DATA_DIR",Path(__file__).resolve().parent/"data")); DATA.mkdir(parents=True,exist_ok=True); DB=DATA/"libris.db"
def db():
 c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
with db() as c:c.executescript("""CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY,title TEXT NOT NULL,author TEXT DEFAULT '',code TEXT NOT NULL UNIQUE,copies INTEGER NOT NULL DEFAULT 1 CHECK(copies>0)); CREATE TABLE IF NOT EXISTS readers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,enrollment TEXT DEFAULT ''); CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id),reader_id INTEGER NOT NULL REFERENCES readers(id),due TEXT NOT NULL,returned TEXT);""")
def ip():
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 try:s.connect(("192.0.2.1",80));return s.getsockname()[0]
 except OSError:return "127.0.0.1"
 finally:s.close()
def br(s):
 try:return date.fromisoformat(s[:10]).strftime("%d/%m/%Y")
 except:return s or "—"
app.jinja_env.filters["br"]=br
BASE="""<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Libris</title><style>body{margin:0;background:#f4f7f5;color:#1a302a;font:15px system-ui}header{background:white;padding:16px max(14px,calc((100% - 1050px)/2));border-bottom:1px solid #dfe8e2;display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap}header b{font-size:20px}nav{display:flex;gap:14px;flex-wrap:wrap}a{color:#24594b;text-decoration:none;font-weight:700;font-size:13px}main{max-width:1050px;margin:28px auto;padding:0 16px}h1{font-size:34px;letter-spacing:-1px}h2{font-size:19px}.muted,small,.hint{color:#718079}.panel,.stat{background:white;border:1px solid #e0e8e3;border-radius:14px;padding:18px;min-width:0}.cols{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:16px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.stat small{display:block}.stat strong{font-size:28px}.form{display:grid;gap:12px}label{display:grid;gap:6px;font-size:12px;font-weight:700}input,select{padding:11px;border:1px solid #d6e2da;border-radius:8px;width:100%;box-sizing:border-box;font:14px system-ui}.btn{background:#163a32;color:white;border:0;border-radius:9px;padding:11px 14px;font-weight:700;cursor:pointer}.secondary{background:#eaf1ed;color:#163a32}.item,.rank{padding:12px 0;border-bottom:1px solid #edf1ee}.item small{display:block;margin-top:4px}.rank{display:flex;align-items:center;gap:10px}.rank span{background:#e7f2ed;border-radius:8px;padding:9px 12px;font-weight:800}.rank div{flex:1}.rank small{display:block;font-size:11px}.empty{text-align:center;padding:20px;color:#718079}.alert{padding:11px;background:#e7f5eb;border-radius:8px;margin:8px 0}.error{background:#fff0ed;color:#963c32}.qr{text-align:center}.qr img{width:150px;height:150px}.qr code{display:block;font-size:11px;overflow-wrap:anywhere}video{width:100%;max-height:240px;background:#12251f;border-radius:10px}@media(max-width:700px){.cols{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}main{padding:0 12px}header{flex-direction:column}}</style><header><b><a href='/'>Libris · Biblioteca</a></b><nav><a href='/books'>Livros</a><a href='/readers'>Leitores</a><a href='/loans'>Empréstimos</a><a href='/ranking'>🏆 Ranking</a></nav></header><main>{% for cat,msg in get_flashed_messages(with_categories=true) %}<div class='alert {{cat}}'>{{msg}}</div>{% endfor %}{{body|safe}}</main><footer style='text-align:center;padding:24px;color:#84938a;font-size:11px'>Libris · dados locais SQLite · faça backup</footer></html>"""
def page(t,**k):return render_template_string(BASE,body=render_template_string(t,**k))
@app.get("/")
def home():
 with db() as c:
  stats=[("Livros",c.execute("select count(*) from books").fetchone()[0]),("Leitores",c.execute("select count(*) from readers").fetchone()[0]),("Em aberto",c.execute("select count(*) from loans where returned is null").fetchone()[0]),("Atrasados",c.execute("select count(*) from loans where returned is null and due<date('now','localtime')").fetchone()[0])]
  rows=c.execute("select l.*,b.title,r.name reader from loans l join books b on b.id=l.book_id join readers r on r.id=l.reader_id where returned is null order by l.id desc limit 8").fetchall()
 return page("""<p class=muted>GESTÃO DA BIBLIOTECA</p><h1>Bem-vindo ao Libris</h1><p class=muted>Acervo, leitores, empréstimos e incentivo à leitura.</p><section class=stats>{% for n,v in stats %}<div class=stat><small>{{n}}</small><strong>{{v}}</strong></div>{% endfor %}</section><div class=cols><section class=panel><h2>Empréstimos em aberto</h2>{% for l in rows %}<div class=item><b>{{l.title}}</b><small>{{l.reader}} · devolver até {{l.due|br}}</small></div>{% else %}<p class=empty>Nenhum empréstimo aberto.</p>{% endfor %}</section><section class='panel qr'><h2>Acesso pelo celular</h2><p class=muted>Celular e computador na mesma rede Wi-Fi.</p><img src=/qr.png><code>http://{{ip}}:8765/mobile</code></section></div>""",stats=stats,rows=rows,ip=ip())
@app.route("/books",methods=["GET","POST"])
def books():
 if request.method=="POST":
  try:
   with db() as c:c.execute("insert into books(title,author,code,copies) values(?,?,?,?)",(request.form["title"].strip(),request.form.get("author","").strip(),''.join(x for x in request.form["code"].strip() if x.isalnum()),max(1,int(request.form.get("copies",1)))))
   flash("Livro cadastrado.")
  except sqlite3.IntegrityError:flash("Código duplicado ou dados inválidos.","error")
  return redirect(url_for("books"))
 q=request.args.get("q","")
 with db() as c:rows=c.execute("select b.*,copies-(select count(*) from loans l where l.book_id=b.id and returned is null) available from books b where title like ? or author like ? or code like ? order by title",(f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
 return page("""<h1>Livros</h1><div class=cols><section class=panel><h2>Cadastrar livro</h2><form class=form method=post><label>Título<input name=title required></label><label>Autor<input name=author></label><label>ISBN / código de barras<input name=code required></label><label>Exemplares<input name=copies type=number min=1 value=1></label><button class=btn>Cadastrar</button></form></section><section class=panel><h2>Acervo</h2><form><input name=q value='{{q}}' placeholder=Buscar><button class='btn secondary'>Buscar</button></form>{% for b in rows %}<div class=item><b>{{b.title}}</b><small>{{b.author}} · {{b.code}} · {{b.available}} disponível(is)</small></div>{% else %}<p class=empty>Nenhum livro cadastrado.</p>{% endfor %}</section></div>""",rows=rows,q=q)
@app.route("/readers",methods=["GET","POST"])
def readers():
 if request.method=="POST":
  with db() as c:c.execute("insert into readers(name,enrollment) values(?,?)",(request.form["name"].strip(),request.form.get("enrollment","").strip()))
  flash("Leitor cadastrado.");return redirect(url_for("readers"))
 q=request.args.get("q","")
 with db() as c:rows=c.execute("select r.*,(select count(*) from loans l where l.reader_id=r.id and returned is null) opened from readers r where name like ? or enrollment like ? order by name",(f"%{q}%",f"%{q}%")).fetchall()
 return page("""<h1>Leitores</h1><div class=cols><section class=panel><h2>Cadastrar leitor</h2><form class=form method=post><label>Nome completo<input name=name required></label><label>Matrícula<input name=enrollment></label><button class=btn>Cadastrar</button></form></section><section class=panel><h2>Leitores cadastrados</h2><form><input name=q value='{{q}}' placeholder=Buscar><button class='btn secondary'>Buscar</button></form>{% for r in rows %}<div class=item><b>{{r.name}}</b><small>{{r.enrollment or 'Sem matrícula'}} · {{r.opened}} empréstimo(s) em aberto</small></div>{% else %}<p class=empty>Nenhum leitor cadastrado.</p>{% endfor %}</section></div>""",rows=rows,q=q)
def lend(code,rid,due):
 try:date.fromisoformat(due)
 except:return False,"Data inválida.",400
 with db() as c:
  b=c.execute("select * from books where upper(code)=upper(?)",(''.join(x for x in (code or '') if x.isalnum()),)).fetchone();r=c.execute("select * from readers where id=?",(rid,)).fetchone()
  if not b:return False,"Livro não cadastrado.",404
  if not r:return False,"Selecione um leitor.",400
  if c.execute("select count(*) from loans where book_id=? and returned is null",(b["id"],)).fetchone()[0]>=b["copies"]:return False,"Sem exemplares disponíveis.",409
  c.execute("insert into loans(book_id,reader_id,due) values(?,?,?)",(b["id"],rid,due))
 return True,"Empréstimo registrado!",200
@app.route("/loans",methods=["GET","POST"])
def loans():
 if request.method=="POST":
  with db() as c:b=c.execute("select code from books where id=?",(request.form.get("book_id"),)).fetchone()
  ok,m,_=lend(b["code"] if b else "",request.form.get("reader_id"),request.form.get("due",""));flash(m,"" if ok else "error");return redirect(url_for("loans"))
 with db() as c:
  rows=c.execute("select l.*,b.title,r.name reader,case when due<date('now','localtime') then 1 else 0 end late from loans l join books b on b.id=l.book_id join readers r on r.id=l.reader_id where returned is null order by due").fetchall()
  bs=c.execute("select b.id,b.title,copies-(select count(*) from loans l where l.book_id=b.id and returned is null) available from books b").fetchall();rs=c.execute("select * from readers order by name").fetchall()
 return page("""<h1>Empréstimos</h1><div class=cols><section class=panel><h2>Novo empréstimo</h2><form class=form method=post><label>Livro<select name=book_id required><option value=''>Selecione</option>{% for b in bs %}<option value={{b.id}} {% if b.available<=0 %}disabled{% endif %}>{{b.title}} · {{b.available}} disponível(is)</option>{% endfor %}</select></label><label>Leitor<select name=reader_id required><option value=''>Selecione</option>{% for r in rs %}<option value={{r.id}}>{{r.name}}</option>{% endfor %}</select></label><label>Devolução<input name=due type=date value='{{due}}' required></label><button class=btn>Registrar empréstimo</button></form></section><section class=panel><h2>Em aberto · {{rows|length}}</h2>{% for l in rows %}<div class=item><b>{{l.title}}</b><small>{{l.reader}} · {{l.due|br}} {% if l.late %}· ATRASADO{% endif %}</small><form method=post action='/loans/{{l.id}}/return'><button class='btn secondary'>Registrar devolução</button></form></div>{% else %}<p class=empty>Nenhum empréstimo aberto.</p>{% endfor %}</section></div>""",rows=rows,bs=bs,rs=rs,due=(date.today()+timedelta(days=14)).isoformat())
@app.post("/loans/<int:i>/return")
def ret(i):
 with db() as c:n=c.execute("update loans set returned=date('now','localtime') where id=? and returned is null",(i,)).rowcount
 flash("Devolução registrada." if n else "Empréstimo já devolvido.","" if n else "error");return redirect(url_for("loans"))
@app.get("/ranking")
def ranking():
 with db() as c:
  readers=c.execute("select r.name,r.enrollment,count(l.id) score from readers r join loans l on l.reader_id=r.id and l.returned is not null group by r.id order by score desc,r.name collate nocase limit 10").fetchall()
  books=c.execute("select b.title,b.author,count(l.id) score from books b join loans l on l.book_id=b.id group by b.id order by score desc,b.title collate nocase limit 10").fetchall()
  total=c.execute("select count(*) from loans where returned is not null").fetchone()[0];n=c.execute("select count(distinct reader_id) from loans where returned is not null").fetchone()[0]
 return page("""<p class=muted>INCENTIVO À LEITURA</p><h1>🏆 Ranking da biblioteca</h1><section class=stats><div class=stat><small>Devoluções concluídas</small><strong>{{total}}</strong></div><div class=stat><small>Leitores ranqueados</small><strong>{{n}}</strong></div></section><div class=cols><section class=panel><h2>Top 10 leitores</h2>{% for r in readers %}<div class=rank><span>{{loop.index}}</span><div><b>{{r.name}}</b><small>{{r.enrollment or 'Sem matrícula'}}</small></div><strong>{{r.score}} <small>livro(s)</small></strong></div>{% else %}<p class=empty>O ranking aparece após devoluções.</p>{% endfor %}</section><section class=panel><h2>Top 10 livros</h2>{% for b in books %}<div class=rank><span>{{loop.index}}</span><div><b>{{b.title}}</b><small>{{b.author or 'Autor não informado'}}</small></div><strong>{{b.score}} <small>vez(es)</small></strong></div>{% else %}<p class=empty>O ranking aparece após empréstimos.</p>{% endfor %}</section></div><p class=hint>Leitores: empréstimos devolvidos. Livros: total emprestado. Empates por ordem alfabética.</p>""",readers=readers,books=books,total=total,n=n)
@app.get("/mobile")
def mobile():
 with db() as c:rs=c.execute("select * from readers order by name").fetchall();bs=c.execute("select title,code,copies-(select count(*) from loans l where l.book_id=b.id and returned is null) available from books b order by title").fetchall()
 return page("""<div style='max-width:600px;margin:auto'><h1>Empréstimo pelo celular</h1><section class=panel><h2>Leitura de código de barras</h2><video id=v playsinline></video><p><button id=start class=btn>Abrir câmera</button> <button id=stop class='btn secondary'>Parar</button></p><p id=msg class=hint>Se a câmera não funcionar, digite o ISBN.</p><label>Código / ISBN<input id=code></label><button id=find class='btn secondary'>Buscar livro</button><div id=book></div><label>Leitor<select id=reader><option value=''>Selecione</option>{% for r in rs %}<option value={{r.id}}>{{r.name}}</option>{% endfor %}</select></label><label>Devolução<input id=due type=date value='{{due}}'></label><button id=send class=btn>Registrar empréstimo</button><div id=result></div></section><section class=panel><h2>Livros</h2>{% for b in bs %}<div class=item><button class='btn secondary pick' data-code='{{b.code}}'>{{b.title}} · {{b.available}} disponível(is)</button></div>{% endfor %}</section></div><script>let found=null,stream=null,det=null,active=false;const $=x=>document.getElementById(x);function stop(){active=false;if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;$('v').srcObject=null}async function find(){let r=await fetch('/api/book?code='+encodeURIComponent($('code').value)),d=await r.json();found=r.ok?d.book:null;$('book').textContent=r.ok?d.book.title+' · disponíveis '+d.book.available:d.message}$('find').onclick=find;document.querySelectorAll('.pick').forEach(b=>b.onclick=()=>{$('code').value=b.dataset.code;find()});$('start').onclick=async()=>{if(!('BarcodeDetector'in window)||!navigator.mediaDevices){$('msg').textContent='Câmera indisponível neste navegador; digite o código.';return}try{det=new BarcodeDetector({formats:['ean_13','ean_8','code_128','upc_a']});stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});$('v').srcObject=stream;await $('v').play();active=true;scan()}catch{$('msg').textContent='Permita acesso à câmera ou digite o ISBN.'}};async function scan(){if(!active)return;try{let a=await det.detect($('v'));if(a[0]){$('code').value=a[0].rawValue;stop();find();return}}catch{}requestAnimationFrame(scan)}$('stop').onclick=stop;$('send').onclick=async()=>{if(!found){$('result').textContent='Busque um livro primeiro.';return}let r=await fetch('/api/mobile-loan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('code').value,reader_id:$('reader').value,due:$('due').value})}),d=await r.json();$('result').textContent=d.message;if(r.ok){found=null;$('code').value='';$('book').textContent='';$('reader').value=''}};document.querySelectorAll('.pick');$('due').value=new Date(Date.now()+14*86400000).toISOString().slice(0,10);window.addEventListener('pagehide',stop)</script>""",rs=rs,bs=bs,due=(date.today()+timedelta(days=14)).isoformat())
@app.get("/qr.png")
def qr():
 b=io.BytesIO();qrcode.make(f"http://{ip()}:8765/mobile").save(b,format="PNG");b.seek(0);return send_file(b,mimetype="image/png")
@app.get("/api/book")
def api_book():
 with db() as c:b=c.execute("select b.id,b.title,b.author,b.code,b.copies-(select count(*) from loans l where l.book_id=b.id and returned is null) available from books b where upper(code)=upper(?)",(''.join(x for x in request.args.get("code","") if x.isalnum()),)).fetchone()
 return (jsonify(book=dict(b)),200) if b else (jsonify(message="Livro não cadastrado."),404)
@app.post("/api/mobile-loan")
def api_loan():
 d=request.get_json(silent=True) or {};ok,m,s=lend(d.get("code"),d.get("reader_id"),d.get("due",""));return jsonify(message=m),s
@app.get("/health")
def health():return jsonify(status="ok")
if __name__=="__main__":
 from waitress import serve
 print(f"Libris: http://127.0.0.1:8765 | celular: http://{ip()}:8765/mobile")
 serve(app,host="0.0.0.0",port=8765)
