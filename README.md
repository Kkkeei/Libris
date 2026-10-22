# Libris — Biblioteca Inteligente (MVP inicial)

Este MVP utiliza dados reais persistidos no PostgreSQL e não cria registros demonstrativos na inicialização. O acervo, alunos, turmas, empréstimos e indicadores são carregados pela API FastAPI. Quando o banco está vazio, as listas ficam vazias e os indicadores ficam em zero.

## O que está implementado

- Frontend React + TypeScript + Vite conectado à API.
- API FastAPI com documentação OpenAPI.
- PostgreSQL 16 pelo Docker Compose e migrações Alembic.
- Cadastro/listagem/edição básica de livros (edição por PATCH da API), com geração de exemplares físicos.
- Cadastro/listagem/edição básica de alunos, matrícula única e vínculo opcional com turma.
- Cadastro/listagem de turmas por ano letivo.
- Registro de empréstimo de exemplar disponível, consulta de histórico e devolução.
- Disponibilidade calculada pelo banco; proteção contra empréstimo simultâneo do mesmo exemplar.
- Dashboard calculado a partir dos registros reais.
- Desativação lógica de livros e alunos, sem apagar seu histórico.
- Testes automatizados da API com banco isolado de testes.
- Ferramentas para inspecionar e importar futuramente um arquivo SQLite `.db` de origem.

## Limitações importantes deste MVP

- **Autenticação e permissões ainda não estão implementadas.** A API não deve ser exposta à internet nem usada com dados reais de crianças em rede compartilhada até concluir autenticação, autorização, auditoria, revisão de segurança e política de backup.
- O frontend já não apresenta login de demonstração nem registros fictícios, mas o ambiente está identificado como local.
- Ranking, gamificação e gráficos históricos foram retirados desta versão funcional porque não havia registros reais nem regras pedagógicas definidas para sustentá-los.
- O importador de `.db` usa nomes de tabelas e colunas comuns. O arquivo de origem deve ser inspecionado antes da importação; se o esquema for diferente, o mapeamento deve ser ajustado em vez de adivinhar os campos.

## Requisitos

- Docker Engine e Docker Compose plugin.
- Node.js 20+ e npm.

## Configuração e execução

Na raiz do projeto:

```bash
cp -n .env.example .env
```

O exemplo usa a porta externa `5433` para evitar conflito com PostgreSQL instalado no Linux. Se o arquivo `.env` já existir, `cp -n` preserva suas configurações. Confirme que `POSTGRES_PORT=5433` está no `.env` local se a porta 5432 já estiver ocupada. Use uma senha local própria em `POSTGRES_PASSWORD`.

Subir banco e API:

```bash
sudo docker compose up --build -d
sudo docker compose ps
sudo docker compose logs --tail=80 api
```

Verificações:

- API: <http://localhost:8000/api/v1/health>
- Banco: <http://localhost:8000/api/v1/health/db>
- Documentação interativa: <http://localhost:8000/api/v1/docs>
- Frontend: <http://localhost:5173>

Em outro terminal, na raiz:

```bash
npm install
npm run dev
```

Para parar os serviços sem apagar os dados:

```bash
sudo docker compose down
```

**Não use `docker compose down -v`** a menos que queira apagar permanentemente o volume do banco local.

## Testes

Os testes usam SQLite em memória e não alteram o PostgreSQL de desenvolvimento. Dentro do container da API:

```bash
sudo docker compose exec api pytest -v
```

Frontend:

```bash
npm run build
npm run lint
npm run test
```

## API principal

| Método | Endpoint | Finalidade |
|---|---|---|
| GET | `/api/v1/dashboard` | Indicadores reais |
| GET / POST | `/api/v1/books` | Listar e cadastrar livros |
| PATCH | `/api/v1/books/{id}` | Atualizar/desativar livro |
| GET / POST | `/api/v1/students` | Listar e cadastrar alunos |
| PATCH | `/api/v1/students/{id}` | Atualizar/desativar aluno |
| GET / POST | `/api/v1/classes` | Listar e cadastrar turmas |
| GET / POST | `/api/v1/loans` | Listar e registrar empréstimos |
| POST | `/api/v1/loans/{id}/return` | Registrar devolução |

## Preparação para importar o seu arquivo `.db`

O banco atual do Libris é PostgreSQL. Um arquivo SQLite `.db` recebido de outra aplicação **não deve simplesmente substituir o banco PostgreSQL**. Primeiro vamos identificar as tabelas e colunas e então importar os livros e alunos para as tabelas corretas, preservando os dados atuais.

1. Copie o `.db` de origem para um caminho local, por exemplo `~/Downloads/biblioteca.db`.
2. Inspecione apenas a estrutura, sem imprimir dados pessoais:

```bash
sudo docker compose run --rm --no-deps \
  -v "$HOME/Downloads/biblioteca.db:/import/origem.db:ro" \
  api python scripts/inspect_sqlite_db.py /import/origem.db
```

3. Envie o arquivo `.db` aqui na conversa para que possamos conferir o esquema e os campos antes de importar. Não envie senhas nem arquivos que não sejam necessários para o acervo.
4. O importador incluído faz **simulação por padrão**. Depois de revisar o mapeamento e fazer backup do PostgreSQL, pode-se simular assim:

```bash
sudo docker compose run --rm --no-deps \
  -v "$HOME/Downloads/biblioteca.db:/import/origem.db:ro" \
  api python scripts/import_sqlite_catalog.py /import/origem.db
```

5. Somente após validar a prévia e o mapeamento, execute com `--apply` para gravar. Não use `--apply` se a prévia não reconhecer corretamente as tabelas e colunas.

O importador não inventa matrícula de aluno: se não houver uma coluna identificável de matrícula, essa tabela será ignorada e o mapeamento deverá ser ajustado. Livros sem autor ou título também serão ignorados para evitar cadastros incompletos. Registros com ISBN ou matrícula já existentes são tratados como duplicados.

## Dados e privacidade

O sistema pode armazenar dados de alunos menores de idade. Antes do uso real, configure autenticação, permissões por perfil, trilha de auditoria, backup/restauração testados e controles de acesso compatíveis com a LGPD e as regras da escola.
