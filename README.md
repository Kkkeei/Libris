# Libris Desktop — Biblioteca Escolar

O Libris é um sistema desktop para organizar uma biblioteca escolar, com banco de dados SQLite local e uma página móvel opcional para circulação na mesma rede Wi‑Fi.

## Funcionalidades

### Acervo e localização física
- Cadastro e edição de exemplares com título, autor, ISBN, gênero, coluna e fileira.
- Tombo/código próprio por exemplar, gerado automaticamente quando não informado.
- Suporte a múltiplas cópias com o mesmo ISBN.
- Situação física: bom, em manutenção ou extraviado.
- Busca móvel por título, autor, ISBN ou tombo, incluindo localização física do exemplar.

### Leitores e leitura
- Cadastro e edição de leitores, matrícula, turma/ano, telefone e meta anual de leitura.
- Progresso anual com contagem de empréstimos devolvidos.
- Sugestões de livros por gênero, histórico de empréstimos, popularidade e disponibilidade, sem recomendar exemplares já emprestados ou anteriormente emprestados àquele leitor.

### Circulação
- Empréstimos e devoluções com alerta de atraso.
- Leitura de código de barras por leitor USB que simula teclado: informe o tombo no campo e o leitor preenche o código.
- Seleção automática de exemplar disponível ao informar ISBN com cópias múltiplas.
- Renovação com limite configurável e bloqueio quando existe reserva aguardando o exemplar.
- Fila de reservas; ao devolver um exemplar reservado, o primeiro da fila muda para “Disponível para retirada”.
- Limite de livros ativos por leitor e prazo padrão configuráveis.

### Relatórios e segurança de dados
- Exportação CSV de acervo, leitores/turmas, empréstimos/atrasos e reservas (compatível com Excel e LibreOffice).
- Backup do banco SQLite pela própria interface.
- Registro local de ações relevantes para auditoria.
- Migração automática do banco de versões anteriores, preservando cadastros e histórico durante a atualização da estrutura.

### Acesso móvel na rede local
- Página acessível por QR Code na mesma rede Wi‑Fi para pesquisar acervo e registrar empréstimos.
- A página móvel segue as regras de disponibilidade e limite de empréstimos configuradas no desktop.
- O acesso móvel é voltado à rede interna da escola; não exponha a porta do aplicativo diretamente à internet.

## Instalação e uso — Linux Mint

No diretório do projeto, execute:

```bash
./gerar_executavel_linux.sh
```

O executável será criado em `dist/Libris`. A base de dados fica separada do executável, em `~/.local/share/libris/libris.db` por padrão, para que uma atualização do programa não apague os registros.

Para atualizar uma instalação existente sem apagar arquivos locais do projeto:

```bash
git fetch origin
git reset --hard origin/main
./gerar_executavel_linux.sh
```

Antes de atualizar em uma biblioteca em uso, faça um backup na tela **Relatórios**.

## Windows

Execute `gerar_executavel_windows.bat`. O executável será criado em `dist\Libris\Libris.exe`; o banco fica na pasta de dados do usuário.

## Validação

O GitHub Actions compila sintaticamente `app.py` a cada atualização da branch principal. A validação de sintaxe não substitui um teste funcional da interface no computador da biblioteca.
