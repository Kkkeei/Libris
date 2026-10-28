# Libris — Biblioteca Inteligente

O Libris é um sistema web responsivo para biblioteca escolar. Contém um catálogo público mobile-first e uma área administrativa separada para a bibliotecária.

## Stack
- React + TypeScript + Vite
- Python + FastAPI + SQLAlchemy
- SQLite local persistente (sem Docker obrigatório)
- JWT e hash de senha Argon2
- pytest para testes da API

## Instalar e executar

### Backend — Linux
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp -n .env.example .env
```

Edite `backend/.env` e defina:
- `AUTH_SECRET_KEY`: chave aleatória de pelo menos 32 caracteres.
- `LIBRIS_SETUP_KEY`: chave de configuração inicial de pelo menos 24 caracteres.

Gere valores com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Use valores separados e não compartilhe esses segredos.

Inicie:
```bash
uvicorn app.main:app --reload
```

O banco será criado em `data/libris.db` na raiz do repositório. Ele é persistente; não o apague ao reiniciar. A base começa vazia. Se você tinha dados na versão anterior que usava PostgreSQL, eles não são convertidos automaticamente para SQLite; faça uma exportação/importação específica antes de descartar a base antiga.

### Frontends — dois sites independentes, na raiz do projeto

Instale as dependências uma vez:
```bash
npm install
```

Abra dois terminais na raiz e execute um comando em cada terminal:

**Site do aluno (catálogo, cadastro e empréstimos):**
```bash
npm run dev:student
```
Abre em http://localhost:5173/

**Site da bibliotecária (login e administração):**
```bash
npm run dev:admin
```
Abre em http://localhost:5174/

São duas aplicações de frontend independentes, com builds e URLs separados, mas usam a mesma API e o mesmo banco para compartilhar o catálogo e os registros da biblioteca. Para produção, publique `dist-student` e `dist-admin` como dois sites separados e configure `VITE_API_BASE_URL` e `VITE_ADMIN_SITE_URL` no build de cada site.

Swagger da API: http://localhost:8000/api/v1/docs

### Windows PowerShell
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Em outro terminal na raiz, execute `npm install`; depois abra dois terminais e execute `npm run dev:student` e `npm run dev:admin`. Antes de iniciar, edite `backend/.env` e defina as duas chaves secretas como descrito acima.

## Acesso pelo celular na mesma rede local

Use isto apenas numa rede Wi-Fi confiável, como a rede interna da escola. Não crie redirecionamento de portas no roteador nem exponha a API diretamente à internet.

1. Descubra o IP local do computador que executa o Libris:
   - Linux: `hostname -I`
   - Windows: `ipconfig`
2. Na raiz do projeto, crie o arquivo de ambiente do Vite:
   ```bash
   cp -n .env.example .env
   ```
   Edite `.env` e substitua `VITE_API_BASE_URL` pelo IP do computador, por exemplo:
   `VITE_API_BASE_URL=http://192.168.1.50:8000/api/v1`
3. Em `backend/.env`, ajuste `CORS_ORIGINS` para incluir a origem do frontend usando o mesmo IP, por exemplo:
   `CORS_ORIGINS=["http://192.168.1.50:5173","http://192.168.1.50:5174","http://localhost:5173","http://localhost:5174","http://127.0.0.1:5173","http://127.0.0.1:5174"]`
4. Inicie o backend aceitando conexões da LAN:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   No Windows, ative `.venv\\Scripts\\Activate.ps1` no PowerShell e execute o mesmo comando `uvicorn`.
5. Na raiz, abra dois terminais e inicie os sites para a rede local:
   ```bash
   npm run dev:student
   npm run dev:admin
   ```
6. No celular conectado à mesma rede, abra `http://192.168.1.50:5173` para o site do aluno ou `http://192.168.1.50:5174` para o site administrativo (substitua pelo IP real do computador).

Se o firewall bloquear a conexão, permita as portas 5173 e 8000 somente na rede privada/local, de acordo com as regras da escola. O endereço da API no navegador do celular precisa ser o IP do computador, não `localhost`.

## Primeiro acesso administrativo

Com o backend iniciado e `LIBRIS_SETUP_KEY` configurada, abra http://localhost:8000/api/v1/docs e faça POST em `/api/v1/setup/admin`, informando e-mail, nome, uma senha forte de ao menos 12 caracteres e a chave de setup. O endpoint é de uso único e recusa criar outro primeiro administrador se já existir uma conta de bibliotecária.

Depois entre no site administrativo em http://localhost:5174/entrar.

Os alunos podem criar a própria conta no site público em http://localhost:5173/cadastro, informando nome completo, matrícula, usuário e senha. Matrícula e usuário precisam ser únicos. Para escolas que exigem validação de matrícula, a confirmação do vínculo escolar deve ser adicionada antes de liberar o cadastro para uso real.

## Rotas principais
- `GET /api/v1/health`, `GET /api/v1/health/db`
- `POST /api/v1/auth/login`
- `GET /api/v1/books`, `GET /api/v1/books/{id}` (catálogo público)
- `GET/POST /api/v1/students`, `PATCH /api/v1/students/{id}` (admin)
- `GET/POST /api/v1/classes` (admin)
- `GET/POST /api/v1/loans`, `POST /api/v1/loans/{id}/return` (admin)
- `GET /api/v1/students/me/loans` (aluno autenticado)
- `GET/POST /api/v1/students/me/loan-requests` (solicitações do próprio aluno)
- `GET /api/v1/loan-requests` e `POST /api/v1/loan-requests/{id}/confirm|reject` (admin)
- `POST /api/v1/auth/student-accounts` (admin, para contas criadas manualmente)
- `POST /api/v1/auth/student-register` (cadastro público de aluno)

## Regras e segurança
- O catálogo público não retorna matrícula, nomes de alunos nem histórico.
- Rotas administrativas exigem token de bibliotecária validado no backend.
- A área do aluno retorna apenas empréstimos vinculados à conta autenticada.
- Senhas são armazenadas com hash Argon2; tokens têm expiração.
- SQLite mantém chaves estrangeiras, espera limitada por lock e modo WAL.
- Cada exemplar possui um código único. Um índice único parcial impede dois empréstimos ativos do mesmo exemplar.
- O aluno pode solicitar o registro de um livro que já foi entregue. A solicitação fica pendente e não muda a disponibilidade até a bibliotecária confirmar. Na confirmação, o sistema seleciona um exemplar realmente disponível e registra o empréstimo; uma restrição no SQLite impede emprestar o mesmo exemplar duas vezes. Registrar digitalmente um livro não autoriza retirar um exemplar fisicamente.
- Não coloque dados reais de alunos no GitHub. Não exponha o sistema na internet sem HTTPS, proteção contra abuso, backups e revisão de LGPD.

## Backup / restauração

Pare a API antes de copiar o banco:
```bash
mkdir -p backups
cp data/libris.db "backups/libris-$(date +%Y%m%d-%H%M%S).db"
```
Para restaurar, pare a API e copie o backup desejado para `data/libris.db`. Não modifique o arquivo com o servidor ativo.

## Testes
No backend:
```bash
pytest -v
```
Na raiz:
```bash
npm run lint
npm run build:student
npm run build:admin
npm run test
```

O código deve passar por esses testes no ambiente local antes de usar cadastros reais de estudantes.
