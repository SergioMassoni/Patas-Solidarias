"""Testes automáticos. Execução:  python testes.py   (usa um banco temporário, não mexe nos seus dados)"""
import json, os, tempfile, threading, urllib.request, urllib.error
os.environ["PATAS_DB"] = os.path.join(tempfile.mkdtemp(), "teste.db")
import app

app.iniciar_banco()
srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Servidor)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/api/"
ok = falhas = 0

def req(rota, metodo="GET", corpo=None, bruto=False):
    r = urllib.request.Request(URL + rota, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else None,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            d = resp.read(); return resp.status, (d if bruto else json.loads(d))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def teste(nome, cond):
    global ok, falhas
    ok += cond; falhas += (not cond)
    print(("✔ " if cond else "✘ ") + nome)

prod = lambda nome: next(p for p in req("produtos")[1] if p["nome"] == nome)
teste("Página inicial carrega", urllib.request.urlopen(URL.replace("api/", "")).status == 200)
d = req("dashboard")[1]
teste("Dashboard: 8 produtos, 7 disponíveis", d["total"] == 8 and d["disponiveis"] == 7)
teste("Alerta de estoque baixo (Vermífugo)", [p["nome"] for p in d["baixo"]] == ["Vermífugo"])
teste("Alerta sem estoque (Vacina)", [p["nome"] for p in d["zerados"]] == ["Vacina antirrábica"])
teste("Dados de demonstração conforme o enunciado",
      [prod(n)["quantidade"] for n in ("Ração para cães adultos", "Ração para filhotes", "Vermífugo", "Antisséptico", "Shampoo para cães", "Desinfetante para canis", "Coleiras")] == [15, 10, 5, 8, 6, 12, 10])
teste("Últimas movimentações aparecem", len(d["ultimas"]) == 8)

# cadastro
c, r = req("produtos", "POST", {"nome": "", "categoria": "Rações", "unidade": "kg"})
teste("Valida nome obrigatório", c == 400)
c, r = req("produtos", "POST", {"nome": "X", "categoria": "Inválida", "unidade": "kg"})
teste("Valida categoria", c == 400)
c, r = req("produtos", "POST", {"nome": "Tapete higiênico", "categoria": "Produtos de higiene", "unidade": "pacote", "quantidade": 4, "minimo": 2})
teste("Cadastra produto com código automático", c == 200 and prod("Tapete higiênico")["codigo"] == "PS-009")
pid = r["id"]
c, _ = req("produtos", "POST", {"codigo": "ps-009", "nome": "Dup", "categoria": "Outros", "unidade": "unidade"})
teste("Impede código duplicado", c == 400)
c, _ = req(f"produtos/{pid}", "PUT", {"nome": "Tapete higiênico G", "categoria": "Produtos de higiene", "unidade": "pacote", "minimo": 3})
teste("Edita produto", c == 200 and prod("Tapete higiênico G")["minimo"] == 3)

# entrada
c, _ = req("movimentacoes", "POST", {"tipo": "entrada", "produto_id": pid, "quantidade": 6, "data": "2026-01-10", "motivo": "Doação", "detalhe": "Doação fictícia", "observacoes": "teste"})
teste("Entrada atualiza estoque (4 + 6 = 10)", c == 200 and prod("Tapete higiênico G")["quantidade"] == 10)
c, _ = req("movimentacoes", "POST", {"tipo": "entrada", "produto_id": pid, "quantidade": 1, "data": "2026-01-10", "motivo": "Compra", "detalhe": ""})
teste("Entrada exige origem", c == 400)
c, _ = req("movimentacoes", "POST", {"tipo": "entrada", "produto_id": pid, "quantidade": 0, "data": "2026-01-10", "motivo": "Compra", "detalhe": "X"})
teste("Quantidade deve ser maior que zero", c == 400)
c, _ = req("movimentacoes", "POST", {"tipo": "entrada", "produto_id": pid, "quantidade": 1, "data": "2999-01-01", "motivo": "Compra", "detalhe": "X"})
teste("Não aceita data futura", c == 400)

# saída
c, _ = req("movimentacoes", "POST", {"tipo": "saida", "produto_id": pid, "quantidade": 4, "data": "2026-01-11", "detalhe": "Higiene dos animais"})
teste("Saída atualiza estoque (10 - 4 = 6)", c == 200 and prod("Tapete higiênico G")["quantidade"] == 6)
c, r = req("movimentacoes", "POST", {"tipo": "saida", "produto_id": pid, "quantidade": 99, "data": "2026-01-11", "detalhe": "Higiene dos animais"})
teste("Bloqueia estoque negativo", c == 400 and "insuficiente" in r["erro"] and prod("Tapete higiênico G")["quantidade"] == 6)
c, _ = req("movimentacoes", "POST", {"tipo": "saida", "produto_id": pid, "quantidade": 1, "data": "2026-01-11", "detalhe": ""})
teste("Saída exige finalidade", c == 400)

# histórico
h = req("movimentacoes?busca=Tapete")[1]
teste("Histórico registra estoque inicial + entrada + saída", len(h) == 3)
teste("Histórico filtra por tipo", all(m["tipo"] == "saida" for m in req("movimentacoes?tipo=saida")[1]))
teste("Histórico filtra por período", len(req("movimentacoes?de=2026-01-10&ate=2026-01-10")[1]) == 1)

# relatórios
for nome in ("geral", "doacoes", "utilizados", "falta"):
    c, r = req(f"relatorios/{nome}")
    teste(f"Relatório '{nome}' gera dados", c == 200 and len(r["linhas"]) > 0)
teste("Relatório de falta: Vermífugo e Vacina", {l[1] for l in req("relatorios/falta")[1]["linhas"]} == {"Vermífugo", "Vacina antirrábica"})
teste("Relatório de doações só tem doações", all("Doação" in l[4] for l in req("relatorios/doacoes")[1]["linhas"]))
c, csvb = req("relatorios/geral?formato=csv", bruto=True)
txt = csvb.decode("utf-8-sig")
teste("Exporta CSV (separador ';' e datas dd/mm/aaaa)", c == 200 and txt.startswith("Código;Produto") and "/" in txt.splitlines()[1])

# exclusão
c, _ = req(f"produtos/{pid}", "DELETE")
teste("Exclui produto e mantém histórico", c == 200 and len(req("movimentacoes?busca=Tapete")[1]) == 3)

# persistência
import sqlite3
n = sqlite3.connect(app.DB).execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
app.iniciar_banco()
teste("Dados persistem no arquivo .db e não duplicam ao reiniciar", n == 8 and sqlite3.connect(app.DB).execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 8)
print(f"\n{ok} testes passaram, {falhas} falharam.")
raise SystemExit(1 if falhas else 0)
