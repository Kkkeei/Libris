# Libris Desktop

Aplicativo desktop de biblioteca com interface moderna em CustomTkinter + SQLite, com painel visual e opção de empréstimo pelo celular via QR Code.

## Recursos
- Cadastro de livros e leitores.
- Empréstimos, devoluções e alerta de atraso.
- Ranking dos leitores mais ativos e livros mais emprestados.
- Página mobile na rede local para registrar empréstimos e pesquisar livros.
- Banco de dados local persistente, independente do executável.

## Linux Mint
Instale dependências do sistema:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk python3-pip
```
Execute em modo desenvolvimento:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Gere o executável:
```bash
chmod +x gerar_executavel_linux.sh
./gerar_executavel_linux.sh
```
O executável será gerado em `dist/Libris`.

## Windows
Instale Python 3.11+ e marque “Add Python to PATH”. Execute `gerar_executavel_windows.bat`. O arquivo ficará em `dist\Libris\Libris.exe`.

**Atenção:** o executável deve ser compilado no próprio sistema de destino. Para gerar um EXE Windows, rode o script no Windows.

## QR Code e celular
Conecte celular e computador à mesma rede Wi-Fi e leia o QR Code no painel. Se a câmera não funcionar pelo endereço HTTP, digite o ISBN manualmente. Não exponha a porta 8765 à internet; o servidor mobile foi pensado para uma rede local confiável.

## Dados e backup
O banco fica em `~/.local/share/libris/libris.db` no Linux ou em `%LOCALAPPDATA%\Libris\libris.db` no Windows. Faça backup regularmente.
