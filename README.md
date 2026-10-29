# Libris Desktop — Biblioteca Escolar
O projeto é um projeto estudantil municipal de afogados da ingazeira - PE criado por mim com 14 anos, junto a minha professora orientadora, Gislene Laurenço, e bibliotecárias escolares, Eduarda Chalego e Paula Oliveira. Realizado na escola Centro de excelência municipal Dom João Jóse da Mota executado no contra-turno e nas aulas de robótica/informática e atualmente estando em desenvolvimento.

## O que já está implementado

### Acervo e localização
- Cadastro, edição e pesquisa rápida por título, autor, ISBN, tombo, gênero ou localização.
- Cada exemplar tem tombo próprio, gerado automaticamente quando não informado.
- Várias cópias da mesma edição podem usar o mesmo ISBN.
- Localização por coluna (letras) e fileira/prateleira (número).
- Estado do exemplar: bom, em manutenção ou extraviado.
- Inventário físico por tombo/código de barras: cada leitura registra data e hora, exibe as últimas conferências e permite exportar o controle para CSV.
- Importação de acervo por CSV e exportação para CSV compatível com Excel/LibreOffice.
- Leitor de código de barras USB compatível com entrada de teclado: foco no campo de ISBN/tombo e leitura do código.
- Empréstimos respeitam reservas liberadas: um exemplar reservado fica protegido para o leitor da fila, tanto no desktop como no celular.

### Importação de documentos (livros e alunos)
- Menu lateral **Importar arquivos** permite selecionar vários arquivos e escolher se os dados serão livros ou alunos/leitores.
- Formatos: **PDF pesquisável, DOCX, DOC, CSV, TSV, TXT, XLSX, XLS, ODS, ODT e JSON**.
- O sistema identifica cabeçalhos comuns em português/inglês (Título, Autor, ISBN, Tombo, Gênero, Coluna, Fileira, Nome, Matrícula, Turma, Telefone etc.).
- A prévia lista os registros reconhecidos e marca duplicidades antes de qualquer gravação. A bibliotecária confirma a importação após conferir os dados.
- Livros sem tombo recebem código automático. Alunos sem matrícula recebem código interno `ALU-AUTO-000001` e assim por diante.
- Se os cabeçalhos não forem reconhecidos, use nomes de coluna claros. Para planilhas sem cabeçalho, a importação considera a ordem de campos padrão do tipo selecionado; confira a prévia com cuidado.
- PDF precisa conter texto/tabela selecionável. PDFs digitalizados apenas como imagem exigem OCR antes de importar. Arquivos `.doc` antigos precisam de LibreOffice instalado; salvar como `.docx` também resolve.
- Os arquivos são processados localmente no computador e não são enviados para serviços externos.

### Leitores e incentivo à leitura
- Cadastro e edição de leitores com matrícula, turma/ano, telefone e meta anual.
- Acompanhamento anual de empréstimos devolvidos em relação à meta de leitura.
- Sugestões personalizadas por gênero e histórico, levando em conta popularidade, disponibilidade e exemplares já emprestados àquele leitor.
- Importação de leitores/turmas por CSV.

### Empréstimos, devoluções e reservas
- Registro de empréstimo por ISBN ou tombo, selecionando exemplar disponível quando há cópias múltiplas.
- Devolução, alerta de atraso e histórico de circulação.
- Renovação com limite configurável; bloqueio da renovação quando há reserva pendente para o exemplar.
- Fila de reservas: a devolução libera o exemplar para a primeira reserva, se ele estiver em boas condições.
- Política de circulação configurável: prazo padrão, limite de livros ativos por leitor e máximo de renovações.
- Página móvel acessível por QR Code, para pesquisar livros e registrar empréstimos pela rede Wi‑Fi local.

### Operação e segurança
- Painel com total de exemplares, leitores, empréstimos ativos e atrasos.
- Ranking anual de leitura e livros mais emprestados.
- Exportação de acervo, leitores/turmas, empréstimos/atrasos, reservas, histórico de ações e inventário físico.
- Backup do banco de dados pela interface.
- Log local de atividades relevantes.
- Migração automática do banco de versões anteriores, preservando cadastros e histórico enquanto adiciona a nova estrutura.

## Linux Mint

No diretório do projeto, execute:

```bash
git fetch origin
git reset --hard origin/main
./gerar_executavel_linux.sh
```

O executável será criado em `dist/Libris`. A base fica fora da pasta do projeto, por padrão em `~/.local/share/libris/libris.db`, para que recriar o executável não apague os cadastros.

**Antes da primeira atualização em uma biblioteca em uso:** abra **Relatórios** e crie um backup do banco. A migração é feita automaticamente, mas a cópia de segurança continua sendo a proteção mais importante.

## Windows

Execute `gerar_executavel_windows.bat`. O executável será criado em `dist\Libris\Libris.exe`.

## Rede local e privacidade

A página móvel foi pensada para dispositivos na mesma rede Wi‑Fi da biblioteca. Não exponha a porta do aplicativo diretamente à internet: o acesso móvel não é um portal com autenticação de usuários. Evite guardar dados pessoais que não sejam necessários à operação escolar.

## Validação

O GitHub Actions executa `python -m py_compile app.py` a cada atualização da branch principal. Isso valida a sintaxe; o funcionamento completo das telas e o processo de empacotamento ainda precisam ser conferidos no computador-alvo.
