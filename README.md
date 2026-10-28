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

O banco será criado em `data/libris.db` na raiz do repositório. Ele é persistente; não o apague ao reiniciar.

### Frontend — outro terminal, na raiz
```bash
npm install
npm run dev
```

Acesse:
- Catálogo público e portal do aluno: http://localhost:5173/
- Painel da bibliotecária: http://localhost:5173/entrar-admin
- Swagger: http://localhost:8000/api/v1/docs

### Windows PowerShell
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Em outro terminal na raiz: `npm install` e `npm run dev`. Antes de iniciar, edite `backend/.env` e defina as duas chaves secretas como descrito acima.

## Primeiro acesso administrativo

Com o backend iniciado e `LIBRIS_SETUP_KEY` configurada, abra http://localhost:8000/api/v1/docs e faça POST em `/api/v1/setup/admin`, informando e-mail, nome, uma senha forte de ao menos 12 caracteres e a chave de setup. O endpoint é de uso único e recusa criar outro primeiro administrador se já existir uma conta de bibliotecária.

Depois entre em http://localhost:5173/entrar-admin.

A bibliotecária pode cadastrar alunos e, em seguida, criar acesso individual pela rota protegida `POST /api/v1/auth/student-accounts` no Swagger. O usuário do aluno usa o nome de acesso definido, não o nome/matrícula pública do estudante.

## Rotas principais
- `GET /api/v1/health`, `GET /api/v1/health/db`
- `POST /api/v1/auth/login`
- `GET /api/v1/books`, `GET /api/v1/books/{id}` (catálogo público)
- `GET/POST /api/v1/students`, `PATCH /api/v1/students/{id}` (admin)
- `GET/POST /api/v1/classes` (admin)
- `GET/POST /api/v1/loans`, `POST /api/v1/loans/{id}/return` (admin)
- `GET /api/v1/students/me/loans` (aluno autenticado)
- `POST /api/v1/auth/student-accounts` (admin)

## Regras e segurança
- O catálogo público não retorna matrícula, nomes de alunos nem histórico.
- Rotas administrativas exigem token de bibliotecária validado no backend.
- A área do aluno retorna apenas empréstimos vinculados à conta autenticada.
- Senhas são armazenadas com hash Argon2; tokens têm expiração.
- SQLite mantém chaves estrangeiras, espera limitada por lock e modo WAL.
- Cada exemplar possui um código único. Um índice único parcial impede dois empréstimos ativos do mesmo exemplar.
- O portal permite pesquisar e consultar o próprio histórico. Por segurança operacional, o registro da retirada permanece sob confirmação administrativa: registrar digitalmente um livro não autoriza retirar um exemplar fisicamente.
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
npm run build
npm run test
```

O código deve passar por esses testes no ambiente local antes de usar cadastros reais de estudantes.
