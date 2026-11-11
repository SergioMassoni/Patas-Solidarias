"""Patas Solidárias – Controle de Estoque (projeto de extensão ADS).
Servidor web simples em Python puro (sem bibliotecas externas) + banco SQLite.
Execução:  python app.py   ->  http://localhost:8000
"""
import csv, io, json, os, sqlite3, threading, webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("PATAS_DB", os.path.join(BASE, "patas_solidarias.db"))
CATEGORIAS = ["Rações", "Medicamentos", "Vacinas", "Produtos de higiene",
              "Produtos de limpeza", "Acessórios", "Outros"]
UNIDADES = ["unidade", "kg", "g", "litro", "ml", "pacote", "caixa", "frasco"]
FINALIDADES = ["Alimentação dos cães", "Tratamento veterinário", "Higiene dos animais",
               "Limpeza do abrigo", "Campanha de adoção", "Outra finalidade"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT NOT NULL UNIQUE,
  nome TEXT NOT NULL,
  categoria TEXT NOT NULL,
  descricao TEXT DEFAULT '',
  quantidade REAL NOT NULL DEFAULT 0 CHECK(quantidade >= 0),   -- nunca negativo
  minimo REAL NOT NULL DEFAULT 0 CHECK(minimo >= 0),
  unidade TEXT NOT NULL,
  data_cadastro TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS movimentacoes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  produto_id INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
  codigo TEXT, produto_nome TEXT, unidade TEXT,      -- cópia: histórico sobrevive à exclusão
  tipo TEXT NOT NULL CHECK(tipo IN ('entrada','saida')),
  motivo TEXT NOT NULL,                              -- Doação, Compra, Estoque inicial, Uso
  quantidade REAL NOT NULL CHECK(quantidade > 0),
  data TEXT NOT NULL,                                -- AAAA-MM-DD
  detalhe TEXT DEFAULT '',                           -- origem (entrada) ou finalidade (saída)
  observacoes TEXT DEFAULT '');
"""


class Erro(Exception):
    pass


# ---------- utilidades ----------
def fmt(n):
    return f"{n:.3f}".rstrip("0").rstrip(".").replace(".", ",")

def br(d):
    return "/".join(reversed(d.split("-"))) if d else ""

def situacao(q, m):
    return "Sem estoque" if q <= 0 else ("Estoque baixo" if q < m else "Normal")

def data_valida(s, futura_ok=True):
    try:
        d = datetime.strptime(str(s), "%Y-%m-%d").date()
    except ValueError:
        raise Erro("Data inválida.")
    if not futura_ok and d > date.today():
        raise Erro("A data não pode ser futura.")
    return d.isoformat()

def numero(v, campo, positivo=False):
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        raise Erro(f"{campo}: informe um número válido.")
    if n < 0 or (positivo and n == 0):
        raise Erro(f"{campo}: informe um valor {'maior que zero' if positivo else 'não negativo'}.")
    return round(n, 3)


# ---------- regras de negócio ----------
def criar_produto(con, d, data=None):
    nome = (d.get("nome") or "").strip()
    if not nome: raise Erro("Informe o nome do produto.")
    if d.get("categoria") not in CATEGORIAS: raise Erro("Selecione uma categoria válida.")
    unidade = (d.get("unidade") or "").strip()
    if not unidade: raise Erro("Informe a unidade de medida.")
    minimo = numero(d.get("minimo") or 0, "Quantidade mínima")
    inicial = numero(d.get("quantidade") or 0, "Quantidade inicial")
    codigo = (d.get("codigo") or "").strip().upper()
    if not codigo:
        codigo = f"PS-{(con.execute('SELECT COALESCE(MAX(id),0) FROM produtos').fetchone()[0] + 1):03d}"
    if con.execute("SELECT 1 FROM produtos WHERE codigo=?", (codigo,)).fetchone():
        raise Erro(f"Já existe um produto com o código {codigo}.")
    data = data or date.today().isoformat()
    cur = con.execute("INSERT INTO produtos(codigo,nome,categoria,descricao,quantidade,minimo,unidade,data_cadastro)"
                      " VALUES(?,?,?,?,0,?,?,?)",
                      (codigo, nome, d["categoria"], (d.get("descricao") or "").strip(), minimo, unidade, data))
    if inicial > 0:   # estoque inicial também gera histórico
        mover(con, cur.lastrowid, "entrada", "Estoque inicial", inicial, data, "Cadastro do produto", "")
    return cur.lastrowid

def mover(con, pid, tipo, motivo, qtd, data, detalhe, obs):
    p = con.execute("SELECT * FROM produtos WHERE id=?", (pid,)).fetchone()
    if not p: raise Erro("Produto não encontrado.")
    novo = round(p["quantidade"] + (qtd if tipo == "entrada" else -qtd), 3)
    if novo < 0:
        raise Erro(f"Estoque insuficiente. Disponível: {fmt(p['quantidade'])} {p['unidade']}.")
    con.execute("UPDATE produtos SET quantidade=? WHERE id=?", (novo, pid))
    con.execute("INSERT INTO movimentacoes(produto_id,codigo,produto_nome,unidade,tipo,motivo,quantidade,data,detalhe,observacoes)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (pid, p["codigo"], p["nome"], p["unidade"], tipo, motivo, qtd, data, detalhe, obs))

def registrar_movimentacao(con, d):
    tipo = d.get("tipo")
    if tipo not in ("entrada", "saida"): raise Erro("Tipo de movimentação inválido.")
    if not d.get("produto_id"): raise Erro("Selecione o produto.")
    qtd = numero(d.get("quantidade"), "Quantidade", positivo=True)
    data = data_valida(d.get("data"), futura_ok=False)
    detalhe = (d.get("detalhe") or "").strip()
    if tipo == "entrada":
        motivo = d.get("motivo")
        if motivo not in ("Doação", "Compra"): raise Erro("Informe se a entrada é doação ou compra.")
        if not detalhe: raise Erro("Informe a origem da entrada.")
    else:
        motivo = "Uso"
        if not detalhe: raise Erro("Informe a finalidade da retirada.")
    mover(con, int(d["produto_id"]), tipo, motivo, qtd, data, detalhe, (d.get("observacoes") or "").strip())

def semear(con):
    """Dados FICTÍCIOS de demonstração (só se o banco estiver vazio)."""
    if con.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]:
        return
    h = date.today()
    dia = lambda n: (h - timedelta(days=n)).isoformat()
    itens = [  # nome, categoria, descrição, qtd inicial, mínimo, unidade
        ("Ração para cães adultos", "Rações", "Ração seca para cães adultos", 10, 10, "kg"),
        ("Ração para filhotes", "Rações", "Ração seca para filhotes", 10, 8, "kg"),
        ("Vermífugo", "Medicamentos", "Vermífugo oral (demonstração)", 7, 6, "unidade"),
        ("Antisséptico", "Medicamentos", "Antisséptico para curativos", 3, 3, "unidade"),
        ("Shampoo para cães", "Produtos de higiene", "Shampoo neutro", 8, 4, "unidade"),
        ("Desinfetante para canis", "Produtos de limpeza", "Limpeza dos canis", 12, 5, "unidade"),
        ("Coleiras", "Acessórios", "Coleiras tamanho médio", 10, 3, "unidade"),
        ("Vacina antirrábica", "Vacinas", "Exemplo de item sem estoque", 0, 5, "unidade"),
    ]
    ids = {}
    for nome, cat, desc, q, m, un in itens:
        ids[nome] = criar_produto(con, dict(nome=nome, categoria=cat, descricao=desc,
                                            quantidade=q, minimo=m, unidade=un), dia(30))
    mover(con, ids["Antisséptico"], "entrada", "Compra", 5, dia(8), "Compra fictícia – Pet Shop Exemplo", "")
    mover(con, ids["Ração para cães adultos"], "entrada", "Doação", 10, dia(12), "Doação fictícia – Mercado Exemplo", "Lote de demonstração")
    mover(con, ids["Ração para cães adultos"], "saida", "Uso", 5, dia(3), "Alimentação dos cães", "")
    mover(con, ids["Vermífugo"], "saida", "Uso", 2, dia(5), "Tratamento veterinário", "")
    mover(con, ids["Shampoo para cães"], "saida", "Uso", 2, dia(2), "Higiene dos animais", "")

def dashboard(con):
    q = lambda s: con.execute(s).fetchone()[0]
    mov = lambda w="": q(f"SELECT COUNT(*) FROM movimentacoes WHERE tipo!='x' {w}")
    lim = (date.today() - timedelta(days=30)).isoformat()
    rows = lambda s: [dict(r) for r in con.execute(s)]
    return {
        "total": q("SELECT COUNT(*) FROM produtos"),
        "disponiveis": q("SELECT COUNT(*) FROM produtos WHERE quantidade>0"),
        "baixo": rows("SELECT * FROM produtos WHERE quantidade>0 AND quantidade<minimo ORDER BY nome"),
        "zerados": rows("SELECT * FROM produtos WHERE quantidade<=0 ORDER BY nome"),
        "entradas": mov("AND tipo='entrada' AND motivo!='Estoque inicial'"),
        "saidas": mov("AND tipo='saida'"),
        "entradas30": mov(f"AND tipo='entrada' AND motivo!='Estoque inicial' AND data>='{lim}'"),
        "saidas30": mov(f"AND tipo='saida' AND data>='{lim}'"),
        "ultimas": rows("SELECT * FROM movimentacoes ORDER BY data DESC, id DESC LIMIT 8"),
    }

def relatorio(con, nome, de, ate):
    f, pr = "", []
    if de: f += " AND data>=?"; pr.append(data_valida(de))
    if ate: f += " AND data<=?"; pr.append(data_valida(ate))
    if nome == "geral":
        cols = ["Código", "Produto", "Categoria", "Quantidade", "Mínimo", "Unidade", "Situação", "Cadastro"]
        rows = [[p["codigo"], p["nome"], p["categoria"], fmt(p["quantidade"]), fmt(p["minimo"]), p["unidade"],
                 situacao(p["quantidade"], p["minimo"]), br(p["data_cadastro"])]
                for p in con.execute("SELECT * FROM produtos ORDER BY nome")]
        return "Relatório geral do estoque", cols, rows
    if nome == "falta":
        cols = ["Código", "Produto", "Categoria", "Quantidade", "Mínimo", "Unidade", "Situação", "Repor (sugestão)"]
        rows = [[p["codigo"], p["nome"], p["categoria"], fmt(p["quantidade"]), fmt(p["minimo"]), p["unidade"],
                 situacao(p["quantidade"], p["minimo"]), fmt(p["minimo"] - p["quantidade"])]
                for p in con.execute("SELECT * FROM produtos WHERE quantidade<minimo OR quantidade<=0 ORDER BY quantidade")]
        return "Relatório de produtos em falta", cols, rows
    if nome == "doacoes":
        cols = ["Data", "Produto", "Quantidade", "Unidade", "Origem", "Observações"]
        sql = f"SELECT * FROM movimentacoes WHERE motivo='Doação'{f} ORDER BY data DESC, id DESC"
        titulo = "Relatório de doações recebidas"
    elif nome == "utilizados":
        cols = ["Data", "Produto", "Quantidade", "Unidade", "Finalidade", "Observações"]
        sql = f"SELECT * FROM movimentacoes WHERE tipo='saida'{f} ORDER BY data DESC, id DESC"
        titulo = "Relatório de produtos utilizados"
    else:
        raise Erro("Relatório inexistente.")
    rows = [[br(m["data"]), m["produto_nome"], fmt(m["quantidade"]), m["unidade"], m["detalhe"], m["observacoes"]]
            for m in con.execute(sql, pr)]
    return titulo, cols, rows


# ---------- rotas da API ----------
def rotear(con, metodo, p, qs, corpo):
    if p == ["api", "config"]:
        return {"categorias": CATEGORIAS, "unidades": UNIDADES, "finalidades": FINALIDADES}
    if p == ["api", "dashboard"]:
        return dashboard(con)
    if p[:2] == ["api", "produtos"]:
        if len(p) == 2 and metodo == "GET":
            sql, pr = "SELECT * FROM produtos WHERE 1=1", []
            if qs.get("busca"):
                sql += " AND (nome LIKE ? OR codigo LIKE ?)"; pr += [f"%{qs['busca']}%"] * 2
            if qs.get("categoria"): sql += " AND categoria=?"; pr.append(qs["categoria"])
            if qs.get("situacao") == "baixo": sql += " AND quantidade>0 AND quantidade<minimo"
            if qs.get("situacao") == "zerado": sql += " AND quantidade<=0"
            return [dict(r) for r in con.execute(sql + " ORDER BY nome", pr)]
        if len(p) == 2 and metodo == "POST":
            return {"id": criar_produto(con, corpo)}
        if len(p) == 3 and metodo == "PUT":
            pid = int(p[2])
            if not con.execute("SELECT 1 FROM produtos WHERE id=?", (pid,)).fetchone(): raise Erro("Produto não encontrado.")
            nome = (corpo.get("nome") or "").strip()
            if not nome: raise Erro("Informe o nome do produto.")
            if corpo.get("categoria") not in CATEGORIAS: raise Erro("Selecione uma categoria válida.")
            if not (corpo.get("unidade") or "").strip(): raise Erro("Informe a unidade de medida.")
            con.execute("UPDATE produtos SET nome=?,categoria=?,descricao=?,minimo=?,unidade=? WHERE id=?",
                        (nome, corpo["categoria"], (corpo.get("descricao") or "").strip(),
                         numero(corpo.get("minimo") or 0, "Quantidade mínima"), corpo["unidade"].strip(), pid))
            return {"ok": True}
        if len(p) == 3 and metodo == "DELETE":
            con.execute("DELETE FROM produtos WHERE id=?", (int(p[2]),))  # histórico é mantido
            return {"ok": True}
    if p[:2] == ["api", "movimentacoes"]:
        if metodo == "POST":
            registrar_movimentacao(con, corpo); return {"ok": True}
        sql, pr = "SELECT * FROM movimentacoes WHERE 1=1", []
        if qs.get("tipo") in ("entrada", "saida"): sql += " AND tipo=?"; pr.append(qs["tipo"])
        if qs.get("busca"): sql += " AND (produto_nome LIKE ? OR codigo LIKE ?)"; pr += [f"%{qs['busca']}%"] * 2
        if qs.get("de"): sql += " AND data>=?"; pr.append(data_valida(qs["de"]))
        if qs.get("ate"): sql += " AND data<=?"; pr.append(data_valida(qs["ate"]))
        return [dict(r) for r in con.execute(sql + " ORDER BY data DESC, id DESC LIMIT 500", pr)]
    if p[:2] == ["api", "relatorios"] and len(p) == 3:
        titulo, cols, rows = relatorio(con, p[2], qs.get("de"), qs.get("ate"))
        if qs.get("formato") == "csv":
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=";")   # ';' abre direto no Excel em português
            w.writerow(cols); w.writerows(rows)
            return ("csv", f"{p[2]}_{date.today().isoformat()}.csv", buf.getvalue())
        return {"titulo": titulo, "colunas": cols, "linhas": rows}
    raise Erro("Rota não encontrada.")


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def enviar(self, status, corpo, tipo="application/json; charset=utf-8", extra=()):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in extra: self.send_header(k, v)
        self.end_headers(); self.wfile.write(corpo)

    def tratar(self, metodo):
        u = urlparse(self.path)
        p = [x for x in u.path.split("/") if x]
        if p[:1] != ["api"]:
            with open(os.path.join(BASE, "index.html"), "rb") as f:
                return self.enviar(200, f.read(), "text/html; charset=utf-8")
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        con = conectar()
        try:
            corpo = {}
            if metodo in ("POST", "PUT"):
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with con:  # commit automático; rollback se der erro
                r = rotear(con, metodo, p, qs, corpo)
            if isinstance(r, tuple):
                return self.enviar(200, r[2].encode("utf-8-sig"), "text/csv; charset=utf-8",
                                   [("Content-Disposition", f'attachment; filename="{r[1]}"')])
            self.enviar(200, json.dumps(r, ensure_ascii=False).encode())
        except (Erro, ValueError, sqlite3.Error) as e:
            self.enviar(400, json.dumps({"erro": str(e)}, ensure_ascii=False).encode())
        finally:
            con.close()

    def do_GET(self): self.tratar("GET")
    def do_POST(self): self.tratar("POST")
    def do_PUT(self): self.tratar("PUT")
    def do_DELETE(self): self.tratar("DELETE")


def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def iniciar_banco():
    con = conectar()
    with con:
        con.executescript(SCHEMA)
        semear(con)
    con.close()

if __name__ == "__main__":
    iniciar_banco()
    srv = ThreadingHTTPServer(("127.0.0.1", 8000), Servidor)
    print("Patas Solidárias rodando em http://localhost:8000  (Ctrl+C para encerrar)")
    threading.Timer(1, lambda: webbrowser.open("http://localhost:8000")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nSistema encerrado.")
