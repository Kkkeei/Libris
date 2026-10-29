"""Document import and normalization for Libris school libraries.

Supported inputs: PDF text/tables, DOCX tables, CSV, TXT, XLSX, XLS, ODS, ODT and JSON.
Scanned/image-only PDFs are reported clearly; OCR is intentionally not silently guessed.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ods", ".odt", ".json"}

BOOK_FIELDS = ("title", "author", "isbn", "accession_code", "category", "column_code", "shelf_row", "condition_status")
READER_FIELDS = ("name", "registration", "class_name", "phone", "reading_goal")

ALIASES = {
    "books": {
        "title": ("titulo", "titulodolivro", "livro", "obratitulo", "obra", "title", "booktitle", "nomedolivro", "nome", "name", "descricao", "tituloobra"),
        "author": ("autor", "autores", "author", "authors", "escritor", "escritora"),
        "isbn": ("isbn", "isbnean", "ean", "codigouniversal", "codigoisbn"),
        "accession_code": ("tombo", "codigodotom", "numerodotom", "codigodebarras", "barcode", "accessioncode", "patrimonio", "registrodoacervo", "codigoexemplar", "idexemplar"),
        "category": ("genero", "categoria", "assunto", "classification", "genre", "category", "generoliterario", "tematica"),
        "column_code": ("coluna", "colunaestante", "letradacoluna", "column", "shelfcolumn"),
        "shelf_row": ("fileira", "prateleira", "numerodafileira", "numerodaprateleira", "shelfrow", "shelf", "estante"),
        "condition_status": ("condicao", "estadodeconservacao", "condicaofisica", "condition", "statusfisico"),
    },
    "readers": {
        "name": ("nome", "nomecompleto", "nomealuno", "nomedoaluno", "aluno", "aluna", "estudante", "student", "name", "full name", "nomeleitor", "nomedoleitor"),
        "registration": ("matricula", "matriculaescolar", "registro", "registroacademico", "ra", "idaluno", "codigoaluno", "codigoleitor", "registration", "studentid", "id", "numeroaluno"),
        "class_name": ("turma", "ano", "serie", "anoescolar", "turmaano", "class", "classroom", "grade", "classe", "serieano"),
        "phone": ("telefone", "celular", "contato", "phone", "mobile", "whatsapp"),
        "reading_goal": ("metaanual", "metadeleitura", "livrosmeta", "objetivoleitura", "readinggoal", "meta"),
    },
}

FIELD_LABELS = {
    "title": "Título", "author": "Autor", "isbn": "ISBN", "accession_code": "Tombo",
    "category": "Gênero", "column_code": "Coluna", "shelf_row": "Fileira",
    "condition_status": "Condição", "name": "Nome", "registration": "Matrícula",
    "class_name": "Turma", "phone": "Telefone", "reading_goal": "Meta anual",
}


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalized_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(ch for ch in text if ch.isalnum())


def _canonical_field(header: Any, kind: str) -> str | None:
    key = normalized_key(header)
    if not key:
        return None
    for field, aliases in ALIASES[kind].items():
        normalized_aliases = [normalized_key(alias) for alias in aliases]
        if key in normalized_aliases:
            return field
    # Tolerate common verbose headings such as "Título do livro (obrigatório)".
    for field, aliases in ALIASES[kind].items():
        for alias in sorted((normalized_key(a) for a in aliases if len(normalized_key(a)) >= 5), key=len, reverse=True):
            if alias and alias in key:
                return field
    return None


def _header_score(row: list[Any], kind: str) -> int:
    return len({_canonical_field(cell, kind) for cell in row if _canonical_field(cell, kind)})


def _split_delimited_line(line: str) -> list[str] | None:
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if "|" in line:
        return [part.strip() for part in line.split("|")]
    return None


def _key_value_records(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n+", text):
        record: dict[str, Any] = {}
        for line in block.splitlines():
            line = line.strip().lstrip("•*- ").strip()
            if not line:
                continue
            match = re.match(r"^([^:=]{2,70})\s*[:=]\s*(.+)$", line)
            if not match:
                match = re.match(r"^([^—–-]{2,50})\s+[—–-]\s+(.+)$", line)
            if match:
                record[match.group(1).strip()] = match.group(2).strip()
        if len(record) >= 2:
            result.append(record)
    return result


def _text_rows(text: str) -> list[list[str]] | list[dict[str, Any]]:
    keyed = _key_value_records(text)
    if keyed:
        return keyed
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    delimited = [_split_delimited_line(line) for line in lines]
    if delimited and all(row is not None for row in delimited):
        return [row for row in delimited if row is not None]
    # Text extracted from PDFs often represents visual columns as multiple spaces.
    spaced = [re.split(r"\s{2,}", line) for line in lines]
    if len(spaced) >= 2 and sum(len(row) > 1 for row in spaced) >= max(2, int(len(spaced) * 0.7)):
        width = max(len(row) for row in spaced)
        if width >= 2:
            return [row for row in spaced if len(row) > 1]
    # A plain list of book titles/names is a legitimate one-column import.
    return [[line] for line in lines]


def _read_csv(path: Path) -> list[list[list[Any]]]:
    raw = path.read_bytes()
    text: str
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(text.splitlines(), dialect))
    return [rows] if rows else []


def _read_excel(path: Path) -> list[list[list[Any]]]:
    tables: list[list[list[Any]]] = []
    if path.suffix.lower() in (".xlsx",):
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in workbook.worksheets:
                rows = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
                rows = [list(row) for row in rows if any(value is not None and str(value).strip() for value in row)]
                if rows:
                    tables.append(rows)
        finally:
            workbook.close()
        return tables
    if path.suffix.lower() == ".xls":
        import xlrd
        workbook = xlrd.open_workbook(str(path), on_demand=True)
        try:
            for sheet in workbook.sheets():
                rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
                rows = [row for row in rows if any(str(value).strip() for value in row if value is not None)]
                if rows:
                    tables.append(rows)
        finally:
            workbook.release_resources()
        return tables
    # ODS is handled by odfpy and kept separate from the Excel readers.
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    document = load(str(path))
    for table in document.getElementsByType(Table):
        rows = []
        for tr in table.getElementsByType(TableRow):
            values = []
            for cell in tr.childNodes:
                if getattr(cell, "qname", (None, None))[1] != "table-cell":
                    continue
                paras = cell.getElementsByType(P)
                values.append(" ".join("".join(p.itertext()) for p in paras).strip())
            if any(values):
                rows.append(values)
        if rows:
            tables.append(rows)
    return tables


def _read_odt(path: Path) -> list[list[list[Any]]] | list[dict[str, Any]]:
    from odf.opendocument import load
    from odf.table import Table, TableRow
    from odf.text import P
    document = load(str(path))
    tables: list[list[list[Any]]] = []
    for table in document.getElementsByType(Table):
        rows = []
        for tr in table.getElementsByType(TableRow):
            values = []
            for cell in tr.childNodes:
                if getattr(cell, "qname", (None, None))[1] != "table-cell":
                    continue
                paras = cell.getElementsByType(P)
                values.append(" ".join("".join(p.itertext()) for p in paras).strip())
            if any(values):
                rows.append(values)
        if rows:
            tables.append(rows)
    if tables:
        return tables
    paragraphs = ["".join(p.itertext()) for p in document.getElementsByType(P)]
    return [_text_rows("\n".join(paragraphs))]


def _read_docx(path: Path) -> list[list[list[Any]]] | list[dict[str, Any]]:
    from docx import Document
    document = Document(str(path))
    tables: list[list[list[Any]]] = []
    for table in document.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if rows:
            tables.append(rows)
    if tables:
        return tables
    return [_text_rows("\n".join(p.text for p in document.paragraphs))]


def _read_pdf(path: Path) -> tuple[list[list[list[Any]]], str]:
    import pdfplumber
    tables: list[list[list[Any]]] = []
    texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            try:
                extracted_tables = page.extract_tables() or []
                for table in extracted_tables:
                    cleaned = [[cell.strip() if isinstance(cell, str) else cell for cell in row] for row in table]
                    cleaned = [row for row in cleaned if any(value not in (None, "") for value in row)]
                    if cleaned:
                        tables.append(cleaned)
            except Exception:
                pass
            text = page.extract_text() or ""
            if text:
                texts.append(text)
    return tables, "\n\n".join(texts)


def _convert_legacy_doc(path: Path, temp_dir: Path) -> Path:
    office = shutil.which("libreoffice") or shutil.which("soffice")
    if not office:
        raise ValueError("Este arquivo .doc antigo precisa do LibreOffice instalado para ser convertido. Salve-o como .docx e tente novamente.")
    command = [office, "--headless", "--convert-to", "docx", "--outdir", str(temp_dir), str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    converted = temp_dir / (path.stem + ".docx")
    if result.returncode != 0 or not converted.exists():
        raise ValueError("O LibreOffice não conseguiu converter este .doc antigo. Salve-o como .docx e tente novamente.")
    return converted


def _map_record(source: dict[str, Any], kind: str) -> dict[str, Any]:
    mapped = {field: "" for field in (BOOK_FIELDS if kind == "books" else READER_FIELDS)}
    normalized_source = {normalized_key(key): value for key, value in source.items()}
    for header, value in normalized_source.items():
        # Match by normalized label to avoid dependence on accents and punctuation.
        field = _canonical_field(header, kind)
        if field and _value_text(value):
            mapped[field] = _value_text(value)
    return mapped


def normalize_rows(tables: list[list[Any] | list[dict[str, Any]]], kind: str) -> tuple[list[dict[str, str]], list[str]]:
    if kind not in ("books", "readers"):
        raise ValueError("Tipo de cadastro inválido.")
    records: list[dict[str, str]] = []
    warnings: list[str] = []
    required = "title" if kind == "books" else "name"
    for table_number, table in enumerate(tables, start=1):
        if not table:
            continue
        if isinstance(table[0], dict):
            candidate_dicts = [row for row in table if isinstance(row, dict)]
            for row_number, row in enumerate(candidate_dicts, start=1):
                record = _map_record(row, kind)
                if record.get(required, "").strip():
                    records.append(record)
                else:
                    warnings.append(f"Bloco {table_number}, registro {row_number}: faltou o campo obrigatório {FIELD_LABELS[required]}.")
            continue

        rows = [list(row) for row in table if isinstance(row, (list, tuple)) and any(value is not None and str(value).strip() for value in row)]
        if not rows:
            continue
        header_index = None
        best_score = 0
        for index, row in enumerate(rows[:12]):
            score = _header_score(row, kind)
            if score > best_score:
                best_score, header_index = score, index
        data_rows = rows
        headers: list[str] | None = None
        if header_index is not None and best_score >= 2:
            headers = [str(value or "").strip() for value in rows[header_index]]
            data_rows = rows[header_index + 1:]
        elif all(len(row) == 1 for row in rows):
            # One-column lists (such as a PDF with one title/name per line).
            for row_number, row in enumerate(rows, start=1):
                value = str(row[0] or "").strip()
                if row_number == 1 and normalized_key(value) in ("titulo", "livro", "nome", "aluno", "estudante", "title", "name"):
                    continue
                record = {field: "" for field in (BOOK_FIELDS if kind == "books" else READER_FIELDS)}
                record[required] = value
                if value:
                    records.append(record)
            warnings.append(f"Tabela {table_number}: lista de uma coluna; confira os dados complementares.")
            continue
        elif not headers:
            expected = list(BOOK_FIELDS if kind == "books" else READER_FIELDS)
            headers = expected

        seen = 0
        rejected = 0
        for row_number, row in enumerate(data_rows, start=(header_index + 2 if headers and header_index is not None else 1)):
            seen += 1
            if headers is None:
                continue
            source = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            record = _map_record(source, kind)
            # For older spreadsheets with no header, the documented field order is used.
            if record.get(required, "").strip():
                records.append(record)
            else:
                rejected += 1
        if rejected:
            warnings.append(f"Tabela {table_number}: {rejected} linha(s) ignorada(s) sem {FIELD_LABELS[required]}.")
    return records, warnings


def parse_document(path: str | Path, kind: str) -> tuple[list[dict[str, str]], list[str]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("Formato não suportado: " + (suffix or "sem extensão"))
    if not source.is_file():
        raise FileNotFoundError(str(source))

    raw_tables: list[list[Any] | list[dict[str, Any]]] = []
    extraction_notes: list[str] = []
    if suffix in (".csv", ".tsv"):
        raw_tables = _read_csv(source)
        if suffix == ".tsv" and raw_tables and raw_tables[0]:
            raw_tables = [[row[0].split("\t") if len(row) == 1 else row for row in raw_tables[0]]]
    elif suffix in (".xlsx", ".xls", ".ods"):
        raw_tables = _read_excel(source)
    elif suffix in (".docx",):
        raw_tables = _read_docx(source)
    elif suffix == ".doc":
        with tempfile.TemporaryDirectory(prefix="libris-doc-") as temporary:
            converted = _convert_legacy_doc(source, Path(temporary))
            raw_tables = _read_docx(converted)
    elif suffix == ".odt":
        raw_tables = _read_odt(source)
    elif suffix == ".pdf":
        pdf_tables, text = _read_pdf(source)
        raw_tables = list(pdf_tables)
        if not raw_tables and text.strip():
            raw_tables = [_text_rows(text)]
        if not raw_tables:
            raise ValueError("Não foi encontrado texto ou tabela legível neste PDF. Se for um documento digitalizado como imagem, execute OCR nele ou salve uma versão pesquisável antes de importar.")
    elif suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("data", data.get("records", [data]))
        if not isinstance(data, list):
            raise ValueError("O JSON precisa conter uma lista de registros.")
        if data and all(isinstance(row, dict) for row in data):
            raw_tables = [data]
        elif data and all(isinstance(row, (list, tuple)) for row in data):
            raw_tables = [[list(row) for row in data]]
        else:
            raise ValueError("Estrutura JSON não reconhecida; use uma lista de objetos.")
    elif suffix == ".txt":
        raw_tables = [_text_rows(source.read_text(encoding="utf-8-sig", errors="replace"))]

    records, warnings = normalize_rows(raw_tables, kind)
    if not records:
        if raw_tables:
            warnings.append("Nenhum cadastro válido foi reconhecido. Confira os cabeçalhos e os campos obrigatórios.")
        else:
            warnings.append("O arquivo não contém linhas ou tabelas reconhecíveis.")
    return records, extraction_notes + warnings
