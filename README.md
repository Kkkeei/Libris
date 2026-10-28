# Libris — Biblioteca Inteligente

Sistema web responsivo para biblioteca escolar, com catálogo público, painel administrativo e portal individual de alunos.

## Tecnologias
- Frontend: React, TypeScript e Vite.
- API: Python, FastAPI, Pydantic e SQLAlchemy.
- Banco padrão: SQLite persistente em disco.
- Autenticação: JWT com hash de senha.
- Testes de API: pytest e HTTPX.

O sistema não cria livros ou alunos fictícios automaticamente.

## Requisitos
- Python 3.11 ou superior.
- Node.js 20 ou superior e npm.
- Docker não é necessário.

## Instalação no Linux

Na raiz do projeto, abra dois terminais.

### 1. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
cp -n .env.example .env
```

Edite `backend/.env` e defina chaves aleatórias exclusivas para o computador. Gere cada uma com:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Use o primeiro resultado em `AUTH_SECRET_KEY` e gere outro para `LIBRIS_SETUP_KEY`. Não publique esses valores.

Inicie a API:
```bash
uvicorn app.main:app --reload
```

A primeira inicialização cria automaticamente `data/libris.db` na raiz do projeto. Não exclua esse arquivo: ele contém os dados da biblioteca.

### 2. Frontend
Na raiz do repositório:
```bash
npm install
npm run dev
```

Abra http://localhost:5173. A API e o Swagger ficam em http://localhost:8000 e http://localhost:8000/api/v1/docs.

## Instalação no Windows (PowerShell)

Terminal 1:
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Edite `backend/.env`, configure `AUTH_SECRET_KEY` e `LIBRIS_SETUP_KEY` com valores aleatórios e inicie:
```powershell
uvicorn app.main:app --reload
```

Terminal 2, na raiz do projeto:
```powershell
npm install
npm run dev
```

## Primeiro acesso da bibliotecária
1. Configure `AUTH_SECRET_KEY` e `LIBRIS_SETUP_KEY` no ambiente do backend antes de iniciar.
2. Faça uma solicitação POST a `/api/v1/setup/admin` usando o Swagger. Envie `email`, `full_name`, uma senha forte com pelo menos 12 caracteres e `setup_key` igual a `LIBRIS_SETUP_KEY`.
3. A configuração é de uso único; não redefine contas existentes.
4. Entre pela tela **Entrar**. Contas adicionais de bibliotecária e credenciais de alunos são criadas pelas rotas protegidas da API.

## Rotas principais
- `GET /api/v1/health`: saúde da API.
- `GET /api/v1/health/db`: verifica o banco.
- `POST /api/v1/auth/login`: login.
- `GET /api/v1/books`: catálogo público com dados bibliográficos.
- `GET /api/v1/students`, `POST /api/v1/students`: cadastro administrativo protegido.
- `POST /api/v1/auth/student-accounts`: vincula credencial a aluno existente, somente pela bibliotecária.
- `POST /api/v1/loans`: registra empréstimo pela bibliotecária.
- `GET /api/v1/students/me/loans`: histórico do aluno autenticado.
- `POST /api/v1/loans/{id}/return`: registra devolução pela bibliotecária.

## Regras e segurança
- Dados de alunos, empréstimos e rotas de alteração exigem autenticação de bibliotecária.
- O portal público mostra apenas o catálogo, nunca a lista de estudantes.
- O histórico do portal é filtrado no backend pela conta individual do aluno.
- Senhas são armazenadas como hash; sessões usam tokens com expiração.
- Uma restrição única no SQLite impede mais de um empréstimo ativo por exemplar.
- O cadastro pelo aluno só deve ser liberado após a escola definir o procedimento de entrega. O portal atual dá acesso ao catálogo e ao próprio histórico; o registro de retirada fica com a bibliotecária para evitar retirada sem confirmação.
- Não exponha o serviço à internet sem HTTPS, proteção de rede e revisão de segurança/LGPD.
- Mantenha `data/libris.db` privado e faça backups regulares.

## Backup e restauração

Com a API parada, copie o arquivo `data/libris.db` para um local seguro:
```bash
mkdir -p backups
cp data/libris.db "backups/libris-$(date +%Y%m%d-%H%M%S).db"
```
Para restaurar, pare a API e substitua `data/libris.db` pelo backup escolhido. Nunca edite o banco enquanto o servidor está ativo.

## Testes
No terminal do backend, com o ambiente virtual ativado:
```bash
pytest -v
```
Frontend:
```bash
npm run lint
npm run build
npm run test
```

Execute os testes após cada atualização e antes de utilizar dados reais de estudantes.
