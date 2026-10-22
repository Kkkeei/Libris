# Libris — Biblioteca Inteligente

Sistema de gestão de biblioteca escolar em desenvolvimento. Esta versão é um **MVP inicial**: possui interface web, API e banco PostgreSQL, com cadastros e circulação de exemplares usando dados persistidos — sem criar livros, alunos ou empréstimos fictícios automaticamente.

> **Atenção:** esta versão ainda não implementa autenticação nem permissões de usuário. Use somente em ambiente local de desenvolvimento. Não exponha a API à internet nem utilize dados pessoais reais de alunos em um ambiente compartilhado antes de concluir os controles de segurança e privacidade.

## Índice

- [Funcionalidades](#funcionalidades)
- [Tecnologias](#tecnologias)
- [Requisitos](#requisitos)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Instalação e execução](#instalação-e-execução)
- [Verificação dos serviços](#verificação-dos-serviços)
- [Parar e reiniciar](#parar-e-reiniciar)
- [Testes e validações](#testes-e-validações)
- [API](#api)
- [Importação de um banco SQLite `.db`](#importação-de-um-banco-sqlite-db)
- [Persistência, backup e privacidade](#persistência-backup-e-privacidade)
- [Limitações conhecidas e próximos passos](#limitações-conhecidas-e-próximos-passos)
- [Solução de problemas](#solução-de-problemas)

## Funcionalidades

- **Livros:** cadastro, consulta, atualização básica e desativação lógica.
- **Exemplares físicos:** geração e controle de exemplares vinculados a cada livro.
- **Alunos:** cadastro, consulta, atualização básica e desativação lógica; número de matrícula único e vínculo opcional com turma.
- **Turmas:** cadastro e consulta por ano letivo.
- **Empréstimos:** registro de empréstimo de exemplar disponível, consulta de histórico e registro de devolução.
- **Disponibilidade:** calculada com base nos registros do banco, com proteção contra empréstimos simultâneos do mesmo exemplar.
- **Painel:** indicadores calculados a partir dos dados efetivamente cadastrados. Se o banco estiver vazio, as listas ficam vazias e os indicadores começam em zero.
- **Migrações:** estrutura do banco gerenciada pelo Alembic.
- **Testes automatizados:** testes da API com banco de testes isolado.
- **Importação assistida:** ferramentas para inspecionar um arquivo SQLite e preparar a importação de livros e alunos, com simulação antes de gravar.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Interface | React, TypeScript e Vite |
| Rotas e formulários | React Router, React Hook Form e Zod |
| Visualizações/ícones | Recharts e Lucide React |
| API | Python, FastAPI e Uvicorn |
| Persistência | SQLAlchemy e PostgreSQL 16 |
| Migrações | Alembic |
| Ambiente local | Docker Compose |
| Testes da API | Pytest e HTTPX |

## Requisitos

- Linux, macOS ou Windows com ambiente compatível.
- Docker Engine e plugin Docker Compose.
- Node.js 20 ou superior e npm.
- Git (opcional, para clonar e versionar o projeto).

## Estrutura do projeto

```text
sistema-bibliotecario/
├── backend/
│   ├── app/
│   │   ├── api/             # Rotas da API
│   │   ├── core/            # Configurações
│   │   ├── db/              # Conexão e sessão do banco
│   │   ├── models/          # Modelos SQLAlchemy
│   │   ├── schemas/         # Esquemas de validação
│   │   └── tests/           # Testes automatizados
│   ├── alembic/             # Migrações do banco
│   ├── scripts/             # Inspeção e importação de SQLite
│   ├── Dockerfile
│   └── pyproject.toml
├── src/                     # Frontend React/TypeScript
├── docker-compose.yml       # PostgreSQL e API
├── .env.example             # Exemplo de variáveis de ambiente
└── README.md
```

## Instalação e execução

Execute os comandos a partir da pasta raiz do projeto, onde estão `docker-compose.yml` e `package.json`.

### 1. Criar as configurações locais

```bash
cp -n .env.example .env
```

O arquivo `.env.example` configura a porta externa do PostgreSQL como `5433`, para evitar conflito com uma instalação local que já esteja usando a porta `5432`. Se o `.env` já existir, `cp -n` não o substitui.

Confira as variáveis relevantes no `.env`:

```dotenv
POSTGRES_DB=libris
POSTGRES_USER=libris
POSTGRES_PASSWORD=troque-por-uma-senha-local
POSTGRES_PORT=5433
API_PORT=8000
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Use uma senha própria para o ambiente local. Não publique o arquivo `.env` nem coloque senhas reais no Git.

### 2. Iniciar o banco e a API

```bash
sudo docker compose up --build -d
sudo docker compose ps
```

A primeira execução pode demorar enquanto as imagens e dependências são baixadas. A API aguarda o banco ficar saudável e executa as migrações configuradas na inicialização.

Para acompanhar os logs:

```bash
sudo docker compose logs -f api
```

Pressione `Ctrl+C` para sair da visualização dos logs; isso não para os serviços.

### 3. Iniciar a interface web

Abra outro terminal, entre na raiz do projeto e execute:

```bash
npm install
npm run dev
```

Abra o endereço informado pelo Vite, normalmente <http://localhost:5173>.

Para compilar a interface para produção:

```bash
npm run build
```

## Verificação dos serviços

Com banco e API iniciados, estes endereços devem responder:

| Serviço | Endereço |
|---|---|
| Frontend Vite | <http://localhost:5173> |
| Verificação da API | <http://localhost:8000/api/v1/health> |
| Verificação da conexão com o banco | <http://localhost:8000/api/v1/health/db> |
| Documentação interativa da API | <http://localhost:8000/api/v1/docs> |
| Especificação OpenAPI | <http://localhost:8000/api/v1/openapi.json> |

A verificação de saúde da API deve retornar um JSON com status `ok`. A verificação do banco confirma que a API consegue acessar o PostgreSQL.

## Parar e reiniciar

Para parar a API e o banco sem apagar o volume persistente:

```bash
sudo docker compose down
```

Para parar apenas o frontend, vá ao terminal onde `npm run dev` está rodando e pressione `Ctrl+C`.

Para iniciar novamente:

```bash
sudo docker compose up -d
npm run dev
```

> **Importante:** não use `sudo docker compose down -v` como comando normal de parada. A opção `-v` remove os volumes do Compose e pode apagar permanentemente os dados do PostgreSQL.

## Testes e validações

### Backend

Os testes estão em `backend/app/tests`. Para executá-los dentro do container da API:

```bash
sudo docker compose exec api pytest -v
```

Eles usam um banco de testes isolado, conforme a configuração de testes, e não devem alterar o banco de desenvolvimento.

### Frontend

Na raiz do projeto:

```bash
npm run build
npm run lint
npm run test
```

- `build`: verifica os tipos TypeScript e gera a compilação Vite.
- `lint`: executa o ESLint.
- `test`: executa os testes de frontend disponíveis; a configuração permite concluir sem testes quando ainda não houver testes implementados.

## API

A documentação completa e interativa fica em <http://localhost:8000/api/v1/docs> enquanto a API estiver rodando.

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/health` | Verificar a API |
| `GET` | `/api/v1/health/db` | Verificar a conexão com o banco |
| `GET` | `/api/v1/dashboard` | Consultar indicadores calculados a partir dos dados reais |
| `GET`, `POST` | `/api/v1/books` | Listar e cadastrar livros |
| `PATCH` | `/api/v1/books/{id}` | Atualizar ou desativar um livro |
| `GET`, `POST` | `/api/v1/students` | Listar e cadastrar alunos |
| `PATCH` | `/api/v1/students/{id}` | Atualizar ou desativar um aluno |
| `GET`, `POST` | `/api/v1/classes` | Listar e cadastrar turmas |
| `GET`, `POST` | `/api/v1/loans` | Consultar empréstimos e registrar um empréstimo |
| `POST` | `/api/v1/loans/{id}/return` | Registrar a devolução de um empréstimo |

Os formatos dos campos e as respostas podem ser consultados no Swagger da API.

## Importação de um banco SQLite `.db`

O banco usado pelo Libris é PostgreSQL. Um arquivo `.db` de outra aplicação pode ser SQLite e **não deve substituir diretamente** o banco atual. Primeiro inspecione a estrutura e confirme o mapeamento das tabelas e colunas.

### 1. Colocar o arquivo em um caminho conhecido

Por exemplo, salve o arquivo recebido em `~/Downloads/biblioteca.db`. O exemplo abaixo monta o arquivo em modo somente leitura dentro do container.

### 2. Inspecionar as tabelas e colunas

Com o serviço `db` iniciado, execute na raiz do projeto:

```bash
sudo docker compose run --rm --no-deps \
  -v "$HOME/Downloads/biblioteca.db:/import/origem.db:ro" \
  api python scripts/inspect_sqlite_db.py /import/origem.db
```

Confira a saída e valide quais tabelas representam livros e alunos. Evite compartilhar relatórios com dados pessoais desnecessários.

### 3. Simular a importação

O importador reconhece alguns nomes comuns de tabelas e colunas. Por padrão, ele faz uma **simulação e não grava registros**:

```bash
sudo docker compose run --rm --no-deps \
  -v "$HOME/Downloads/biblioteca.db:/import/origem.db:ro" \
  api python scripts/import_sqlite_catalog.py /import/origem.db
```

O container da base de dados precisa estar em execução para que o script consulte o PostgreSQL. A simulação deve ser revisada antes de qualquer gravação.

### 4. Fazer backup e importar somente após validar

Antes de gravar, faça um backup do banco PostgreSQL, confira os resultados da simulação e confirme o mapeamento. Só então execute novamente acrescentando `--apply`:

```bash
sudo docker compose run --rm --no-deps \
  -v "$HOME/Downloads/biblioteca.db:/import/origem.db:ro" \
  api python scripts/import_sqlite_catalog.py /import/origem.db --apply
```

**Não use `--apply` sem revisar a prévia.** O importador não gera matrículas artificiais: se não identificar nome e matrícula, ignora a tabela de alunos e exige ajuste manual. Livros sem título ou autor também são ignorados. ISBNs e matrículas já existentes são tratados como duplicados. O mapeamento é limitado a nomes comuns; estruturas diferentes exigem adaptação do script.

## Persistência, backup e privacidade

- Os dados do PostgreSQL ficam no volume Docker `libris_postgres_data`, que persiste mesmo depois de `docker compose down`.
- Excluir o volume pode eliminar os dados. Antes de manutenção, faça backup e confirme que o arquivo de backup pode ser restaurado.
- O projeto pode armazenar informações de estudantes, inclusive menores de idade. Antes do uso institucional, implemente autenticação, autorização por perfil, auditoria, política de retenção, backups protegidos e controles adequados à LGPD e às regras da escola.
- Não coloque dados reais de alunos, credenciais ou arquivos de banco no repositório Git.

## Limitações conhecidas e próximos passos

Esta versão é um ponto de partida para desenvolvimento, não uma versão pronta para produção. Entre os itens que ainda exigem implementação ou validação estão:

1. Autenticação, gestão de usuários e permissões por perfil.
2. Auditoria de operações e trilha de alterações.
3. Política de backup e teste de restauração.
4. Revisão de segurança, privacidade e configuração de produção.
5. Validação de regras operacionais da biblioteca, incluindo prazos, renovações, reservas e penalidades, antes de adotá-las oficialmente.
6. Testes adicionais de interface e testes de ponta a ponta.
7. Ajuste e validação do importador conforme a estrutura real do arquivo de origem.

## Solução de problemas

### A porta 5432 já está ocupada

Defina `POSTGRES_PORT=5433` no `.env`. A aplicação dentro do Docker continua acessando o PostgreSQL pelo host interno `db` e pela porta `5432`; a porta `5433` é apenas a porta publicada no computador.

### A API não inicia

Veja os logs:

```bash
sudo docker compose logs --tail=100 api
sudo docker compose logs --tail=100 db
```

Confirme que o banco está saudável e que o `.env` contém as variáveis esperadas. Depois de alterar dependências ou o Dockerfile, reconstrua com `sudo docker compose up --build -d`.

### O frontend não consegue acessar a API

Confirme que a API responde em <http://localhost:8000/api/v1/health> e que `VITE_API_BASE_URL` aponta para `http://localhost:8000/api/v1`. Reinicie `npm run dev` após mudar variáveis de ambiente do Vite.

### Os cadastros aparecem vazios

O sistema não insere registros demonstrativos automaticamente. Um banco novo deve mostrar listas vazias e indicadores zerados até que os primeiros dados sejam cadastrados ou importados.

---

**Projeto:** Libris — Biblioteca Inteligente  
**Versão documentada:** MVP inicial  
**Status:** em desenvolvimento
