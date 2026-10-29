# Libris — biblioteca local com ranking

Aplicação Python, Flask e SQLite para Linux Mint, com site responsivo e acesso pelo celular via QR Code.

## Recursos
- Cadastro e busca de livros por ISBN/código de barras.
- Cadastro de leitores e matrícula.
- Empréstimos, controle de exemplares, devoluções e atrasos.
- Site móvel para registrar empréstimos pelo celular; câmera quando suportada pelo navegador e entrada manual alternativa.
- QR Code no painel para abrir o site móvel na mesma rede.
- Ranking Top 10 de leitores (empréstimos devolvidos) e livros mais emprestados.
- Banco SQLite persistente em `data/libris.db`.

## Instalar no Linux Mint
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Abra http://127.0.0.1:8765. Celular e computador precisam estar na mesma rede Wi-Fi ou hotspot. Se necessário, libere TCP 8765 no firewall.

## Ranking
Leitores são classificados por empréstimos devolvidos; livros pelo total de empréstimos. Empates em ordem alfabética.

## Segurança
Versão local inicial sem autenticação. Não exponha à internet; faça backup de `data/`. Alguns navegadores exigem HTTPS para a câmera; nesse caso use entrada manual ou leitor USB.
