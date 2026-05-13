import sqlite3
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template_string, request

app = Flask(__name__, static_folder="static")

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "gastos.db")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            mes TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            tipo TEXT NOT NULL DEFAULT 'Fixo'
        )
    """)
    try:
        cursor.execute(
            "ALTER TABLE gastos ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Fixo'"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE gastos ADD COLUMN vencimento INTEGER")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            mes TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT UNIQUE NOT NULL,
            limite REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_NAME)


MESES_PT = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def mes_label(mes):
    ano, m = map(int, mes.split("-"))
    return f"{MESES_PT[m - 1]} {ano}"


def mes_offset(mes, delta):
    ano, m = map(int, mes.split("-"))
    m += delta
    ano += (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return f"{ano:04d}-{m:02d}"


def gerar_meses(mes_inicio, qtd=12):
    ano, mes = map(int, mes_inicio.split("-"))
    resultado = []
    for i in range(qtd):
        m = mes + i
        a = ano + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        resultado.append(f"{a:04d}-{m:02d}")
    return resultado


@app.route("/")
def index():
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, nome, valor, status, tipo, vencimento FROM gastos
           WHERE mes = ?
           ORDER BY tipo,
                    CASE WHEN vencimento IS NULL THEN 32 ELSE vencimento END,
                    nome""",
        (mes,),
    )
    gastos = cursor.fetchall()

    # Meta do mês
    meta_row = conn.execute("SELECT limite FROM metas WHERE mes = ?", (mes,)).fetchone()
    meta = meta_row[0] if meta_row else None

    conn.close()

    total = sum(g[2] for g in gastos)
    pagos = sum(g[2] for g in gastos if g[3] == "Pago")
    pendentes = total - pagos
    total_fixos = sum(g[2] for g in gastos if g[4] == "Fixo")
    total_esporadicos = sum(g[2] for g in gastos if g[4] == "Esporádico")
    gastos_fixos = [g for g in gastos if g[4] == "Fixo"]
    gastos_esporadicos = [g for g in gastos if g[4] == "Esporádico"]

    meta_pct = None
    if meta and meta > 0:
        meta_pct = round((total / meta) * 100, 1)

    editar_id = request.args.get("editar", type=int)
    editar_receita_id = request.args.get("editar_receita", type=int)

    conn = get_conn()
    receitas = conn.execute(
        "SELECT id, nome, valor, status FROM receitas WHERE mes = ? ORDER BY nome",
        (mes,),
    ).fetchall()
    nomes_gastos = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT nome FROM gastos ORDER BY nome"
        ).fetchall()
    ]
    nomes_receitas = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT nome FROM receitas ORDER BY nome"
        ).fetchall()
    ]
    conn.close()

    total_receitas = sum(r[2] for r in receitas)
    recebido = sum(r[2] for r in receitas if r[3] == "Recebido")
    saldo = total_receitas - total

    now = datetime.now()
    dia_hoje = now.day
    mes_atual = now.strftime("%Y-%m")
    eh_mes_atual = mes == mes_atual

    return render_template_string(
        TEMPLATE,
        gastos=gastos,
        mes=mes,
        mes_label=mes_label(mes),
        mes_anterior=mes_offset(mes, -1),
        mes_seguinte=mes_offset(mes, +1),
        total=total,
        pagos=pagos,
        pendentes=pendentes,
        total_fixos=total_fixos,
        total_esporadicos=total_esporadicos,
        gastos_fixos=gastos_fixos,
        gastos_esporadicos=gastos_esporadicos,
        receitas=receitas,
        total_receitas=total_receitas,
        recebido=recebido,
        saldo=saldo,
        editar_id=editar_id,
        editar_receita_id=editar_receita_id,
        nomes_gastos=nomes_gastos,
        nomes_receitas=nomes_receitas,
        meta=meta,
        meta_pct=meta_pct,
        dia_hoje=dia_hoje,
        eh_mes_atual=eh_mes_atual,
    )


@app.route("/adicionar", methods=["POST"])
def adicionar():
    nome = request.form.get("nome", "").strip()
    valor = request.form.get("valor", "0").replace(",", ".")
    mes = request.form.get("mes") or datetime.now().strftime("%Y-%m")

    if not nome:
        return redirect(f"/?mes={mes}")

    try:
        valor = float(valor)
    except ValueError:
        return redirect(f"/?mes={mes}")

    try:
        qtd_meses = max(1, int(request.form.get("meses", "") or 1))
    except ValueError:
        qtd_meses = 1
    meses = gerar_meses(mes, qtd_meses)

    vencimento_raw = request.form.get("vencimento", "").strip()
    vencimento = None
    if vencimento_raw:
        try:
            v = int(vencimento_raw)
            if 1 <= v <= 31:
                vencimento = v
        except ValueError:
            pass

    conn = get_conn()
    tipo = request.form.get("tipo", "Fixo")
    if tipo not in ("Fixo", "Esporádico"):
        tipo = "Fixo"

    conn.executemany(
        "INSERT INTO gastos (nome, valor, mes, status, tipo, vencimento) VALUES (?, ?, ?, ?, ?, ?)",
        [(nome, valor, m, "Pendente", tipo, vencimento) for m in meses],
    )
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/toggle/<int:gasto_id>")
def toggle(gasto_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM gastos WHERE id = ?", (gasto_id,))
    row = cursor.fetchone()

    if row:
        novo_status = "Pago" if row[0] == "Pendente" else "Pendente"
        conn.execute(
            "UPDATE gastos SET status = ? WHERE id = ?", (novo_status, gasto_id)
        )
        conn.commit()

    conn.close()
    return redirect(f"/?mes={mes}")


@app.route("/editar/<int:gasto_id>", methods=["POST"])
def editar(gasto_id):
    mes = request.form.get("mes") or datetime.now().strftime("%Y-%m")
    valor = request.form.get("valor", "0").replace(",", ".")

    try:
        valor = float(valor)
    except ValueError:
        return redirect(f"/?mes={mes}")

    vencimento_raw = request.form.get("vencimento", "").strip()
    vencimento = None
    if vencimento_raw:
        try:
            v = int(vencimento_raw)
            if 1 <= v <= 31:
                vencimento = v
        except ValueError:
            pass

    todos = request.form.get("todos") == "on"
    conn = get_conn()
    if todos:
        row = conn.execute(
            "SELECT nome FROM gastos WHERE id = ?", (gasto_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE gastos SET valor = ?, vencimento = ? WHERE nome = ?",
                (valor, vencimento, row[0]),
            )
    else:
        conn.execute(
            "UPDATE gastos SET valor = ?, vencimento = ? WHERE id = ?",
            (valor, vencimento, gasto_id),
        )
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/excluir/<int:gasto_id>")
def excluir(gasto_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/excluir-todos/<int:gasto_id>")
def excluir_todos(gasto_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    row = conn.execute("SELECT nome FROM gastos WHERE id = ?", (gasto_id,)).fetchone()
    if row:
        conn.execute("DELETE FROM gastos WHERE nome = ?", (row[0],))
        conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/receita/adicionar", methods=["POST"])
def adicionar_receita():
    nome = request.form.get("nome", "").strip()
    valor = request.form.get("valor", "0").replace(",", ".")
    mes = request.form.get("mes") or datetime.now().strftime("%Y-%m")

    if not nome:
        return redirect(f"/?mes={mes}")

    try:
        valor = float(valor)
    except ValueError:
        return redirect(f"/?mes={mes}")

    try:
        qtd_meses = max(1, int(request.form.get("meses", "") or 1))
    except ValueError:
        qtd_meses = 1
    meses = gerar_meses(mes, qtd_meses)

    conn = get_conn()
    conn.executemany(
        "INSERT INTO receitas (nome, valor, mes, status) VALUES (?, ?, ?, ?)",
        [(nome, valor, m, "Pendente") for m in meses],
    )
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/receita/toggle/<int:receita_id>")
def toggle_receita(receita_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    row = conn.execute(
        "SELECT status FROM receitas WHERE id = ?", (receita_id,)
    ).fetchone()
    if row:
        novo = "Recebido" if row[0] == "Pendente" else "Pendente"
        conn.execute("UPDATE receitas SET status = ? WHERE id = ?", (novo, receita_id))
        conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/receita/editar/<int:receita_id>", methods=["POST"])
def editar_receita(receita_id):
    mes = request.form.get("mes") or datetime.now().strftime("%Y-%m")
    valor = request.form.get("valor", "0").replace(",", ".")

    try:
        valor = float(valor)
    except ValueError:
        return redirect(f"/?mes={mes}")

    todos = request.form.get("todos") == "on"
    conn = get_conn()
    if todos:
        row = conn.execute(
            "SELECT nome FROM receitas WHERE id = ?", (receita_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE receitas SET valor = ? WHERE nome = ?", (valor, row[0])
            )
    else:
        conn.execute("UPDATE receitas SET valor = ? WHERE id = ?", (valor, receita_id))
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/receita/excluir/<int:receita_id>")
def excluir_receita(receita_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    conn.execute("DELETE FROM receitas WHERE id = ?", (receita_id,))
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/receita/excluir-todos/<int:receita_id>")
def excluir_todos_receita(receita_id):
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

    conn = get_conn()
    row = conn.execute(
        "SELECT nome FROM receitas WHERE id = ?", (receita_id,)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM receitas WHERE nome = ?", (row[0],))
        conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/meta/salvar", methods=["POST"])
def salvar_meta():
    mes = request.form.get("mes") or datetime.now().strftime("%Y-%m")
    limite_raw = request.form.get("limite", "0").replace(",", ".")
    try:
        limite = float(limite_raw)
    except ValueError:
        return redirect(f"/?mes={mes}")

    conn = get_conn()
    conn.execute(
        """INSERT INTO metas (mes, limite) VALUES (?, ?)
           ON CONFLICT(mes) DO UPDATE SET limite = excluded.limite""",
        (mes, limite),
    )
    conn.commit()
    conn.close()

    return redirect(f"/?mes={mes}")


@app.route("/api/alertas")
def api_alertas():
    mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")
    now = datetime.now()
    dia_hoje = now.day
    mes_atual = now.strftime("%Y-%m")

    # Só retorna alertas para o mês atual
    if mes != mes_atual:
        return jsonify({"alertas": []})

    conn = get_conn()
    rows = conn.execute(
        """SELECT nome, valor, vencimento FROM gastos
           WHERE mes = ? AND status = 'Pendente' AND vencimento IS NOT NULL
             AND (vencimento - ? <= 3)""",
        (mes, dia_hoje),
    ).fetchall()
    conn.close()

    alertas = []
    for nome, valor, vencimento in rows:
        diff = vencimento - dia_hoje
        alertas.append(
            {
                "nome": nome,
                "valor": valor,
                "vencimento": vencimento,
                "diff": diff,
            }
        )

    # Ordenar: atrasados primeiro, depois por proximidade
    alertas.sort(key=lambda x: x["diff"])

    return jsonify({"alertas": alertas})


@app.route("/comparativo")
def comparativo():
    now = datetime.now()
    mes_atual = now.strftime("%Y-%m")
    mes_anterior = mes_offset(mes_atual, -1)

    mes_a = request.args.get("mes_a") or mes_anterior
    mes_b = request.args.get("mes_b") or mes_atual

    conn = get_conn()

    gastos_a_rows = conn.execute(
        "SELECT nome, tipo, SUM(valor) FROM gastos WHERE mes = ? GROUP BY nome, tipo",
        (mes_a,),
    ).fetchall()
    gastos_b_rows = conn.execute(
        "SELECT nome, tipo, SUM(valor) FROM gastos WHERE mes = ? GROUP BY nome, tipo",
        (mes_b,),
    ).fetchall()

    receitas_a_rows = conn.execute(
        "SELECT nome, SUM(valor) FROM receitas WHERE mes = ? GROUP BY nome", (mes_a,)
    ).fetchall()
    receitas_b_rows = conn.execute(
        "SELECT nome, SUM(valor) FROM receitas WHERE mes = ? GROUP BY nome", (mes_b,)
    ).fetchall()

    conn.close()

    # Merge gastos por (nome, tipo)
    gastos_a = {(r[0], r[1]): r[2] for r in gastos_a_rows}
    gastos_b = {(r[0], r[1]): r[2] for r in gastos_b_rows}
    todas_chaves_gastos = sorted(
        set(gastos_a) | set(gastos_b), key=lambda x: (x[1], x[0])
    )

    tabela_gastos = []
    for nome, tipo in todas_chaves_gastos:
        va = gastos_a.get((nome, tipo), 0)
        vb = gastos_b.get((nome, tipo), 0)
        tabela_gastos.append(
            {
                "nome": nome,
                "tipo": tipo,
                "valor_a": va,
                "valor_b": vb,
                "diff": vb - va,
            }
        )

    # Merge receitas por nome
    receitas_a = {r[0]: r[1] for r in receitas_a_rows}
    receitas_b = {r[0]: r[1] for r in receitas_b_rows}
    todas_chaves_receitas = sorted(set(receitas_a) | set(receitas_b))

    tabela_receitas = []
    for nome in todas_chaves_receitas:
        va = receitas_a.get(nome, 0)
        vb = receitas_b.get(nome, 0)
        tabela_receitas.append(
            {
                "nome": nome,
                "valor_a": va,
                "valor_b": vb,
                "diff": vb - va,
            }
        )

    total_gastos_a = sum(r["valor_a"] for r in tabela_gastos)
    total_gastos_b = sum(r["valor_b"] for r in tabela_gastos)
    total_receitas_a = sum(r["valor_a"] for r in tabela_receitas)
    total_receitas_b = sum(r["valor_b"] for r in tabela_receitas)

    return render_template_string(
        COMPARATIVO_TEMPLATE,
        mes_a=mes_a,
        mes_b=mes_b,
        mes_label_a=mes_label(mes_a),
        mes_label_b=mes_label(mes_b),
        tabela_gastos=tabela_gastos,
        tabela_receitas=tabela_receitas,
        total_gastos_a=total_gastos_a,
        total_gastos_b=total_gastos_b,
        total_receitas_a=total_receitas_a,
        total_receitas_b=total_receitas_b,
        delta_gastos=total_gastos_b - total_gastos_a,
        delta_receitas=total_receitas_b - total_receitas_a,
    )


@app.route("/dashboard")
def dashboard():
    conn = get_conn()

    gastos_por_mes = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT mes, SUM(valor) FROM gastos GROUP BY mes ORDER BY mes"
        ).fetchall()
    }

    receitas_por_mes = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT mes, SUM(valor) FROM receitas GROUP BY mes ORDER BY mes"
        ).fetchall()
    }

    gastos_pagos_por_mes = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT mes, SUM(valor) FROM gastos WHERE status='Pago' GROUP BY mes"
        ).fetchall()
    }

    receitas_recebidas_por_mes = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT mes, SUM(valor) FROM receitas WHERE status='Recebido' GROUP BY mes"
        ).fetchall()
    }

    conn.close()

    todos_meses = sorted(set(gastos_por_mes) | set(receitas_por_mes))

    meses_labels = [mes_label(m) for m in todos_meses]
    valores_gastos = [round(gastos_por_mes.get(m, 0), 2) for m in todos_meses]
    valores_receitas = [round(receitas_por_mes.get(m, 0), 2) for m in todos_meses]
    valores_saldo = [
        round(receitas_por_mes.get(m, 0) - gastos_por_mes.get(m, 0), 2)
        for m in todos_meses
    ]

    total_gastos = sum(valores_gastos)
    total_receitas = sum(valores_receitas)
    saldo_geral = total_receitas - total_gastos
    total_pago = sum(gastos_pagos_por_mes.values())
    total_recebido = sum(receitas_recebidas_por_mes.values())

    tabela = [
        {
            "mes": mes_label(m),
            "receitas": receitas_por_mes.get(m, 0),
            "gastos": gastos_por_mes.get(m, 0),
            "saldo": receitas_por_mes.get(m, 0) - gastos_por_mes.get(m, 0),
        }
        for m in todos_meses
    ]

    now = datetime.now()
    mes_atual = now.strftime("%Y-%m")
    mes_anterior = mes_offset(mes_atual, -1)

    return render_template_string(
        DASHBOARD_TEMPLATE,
        meses_labels=meses_labels,
        valores_gastos=valores_gastos,
        valores_receitas=valores_receitas,
        valores_saldo=valores_saldo,
        total_gastos=total_gastos,
        total_receitas=total_receitas,
        saldo_geral=saldo_geral,
        total_pago=total_pago,
        total_recebido=total_recebido,
        tabela=tabela,
        mes_atual=mes_atual,
        mes_anterior=mes_anterior,
    )


TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Controle de Gastos</title>
    <link rel="manifest" href="/static/manifest.json">
    <script>
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/static/sw.js");
    }
    </script>
    <script>(function(){const t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);})();</script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg: #f0f2f5;
            --surface: #ffffff;
            --text: #333333;
            --text-muted: #888888;
            --text-heading: #1a1a2e;
            --border: #dddddd;
            --border-light: #f0f0f0;
            --input-bg: #ffffff;
            --hover-bg: #fafafa;
            --grupo-bg: #f7f8fa;
            --grupo-border: #eeeeee;
            --btn-nav-bg: #f0f2f5;
            --btn-nav-hover: #e2e6ea;
            --btn-cancel-bg: #eeeeee;
            --btn-cancel-color: #555555;
            --editando-bg: #f0f6ff;
            --shadow: rgba(0,0,0,0.07);
            --empty-color: #bbbbbb;
            --icon-color: #cccccc;
            --check-color: #666666;
        }

        [data-theme="dark"] {
            --bg: #0f1117;
            --surface: #1a1d27;
            --text: #cbd5e1;
            --text-muted: #64748b;
            --text-heading: #f1f5f9;
            --border: #2d3748;
            --border-light: #252a38;
            --input-bg: #252a38;
            --hover-bg: #212636;
            --grupo-bg: #212636;
            --grupo-border: #2d3748;
            --btn-nav-bg: #252a38;
            --btn-nav-hover: #2d3748;
            --btn-cancel-bg: #2d3748;
            --btn-cancel-color: #94a3b8;
            --editando-bg: #1a2840;
            --shadow: rgba(0,0,0,0.35);
            --empty-color: #4a5568;
            --icon-color: #4a5568;
            --check-color: #94a3b8;
        }

        body {
            font-family: Arial, sans-serif;
            max-width: 960px;
            margin: 40px auto;
            padding: 20px;
            background: var(--bg);
            color: var(--text);
            transition: background 0.2s, color 0.2s;
        }

        h1 { font-size: 1.8rem; color: var(--text-heading); }

        .cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }

        @media (max-width: 800px) { .cards { grid-template-columns: repeat(3, 1fr); } }
        @media (max-width: 500px)  { .cards { grid-template-columns: repeat(2, 1fr); } }

        .card {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .card .label {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .card .valor { font-size: 1.6rem; font-weight: bold; }

        .card.total .valor       { color: var(--text-heading); }
        .card.pagos .valor       { color: #27ae60; }
        .card.pendentes .valor   { color: #e74c3c; }
        .card.fixos .valor       { color: #3949ab; }
        .card.esporadicos .valor { color: #e65100; }
        .card.receitas .valor    { color: #0d7a4e; }
        .card.recebido .valor    { color: #0d7a4e; }
        .card.saldo-pos .valor   { color: #0d7a4e; }
        .card.saldo-neg .valor   { color: #e74c3c; }

        .painel {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .painel h2 { font-size: 1rem; margin-bottom: 12px; color: var(--text-muted); }

        .linha { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }

        input[type="text"],
        input[type="number"],
        input[type="month"] {
            padding: 9px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 0.95rem;
            outline: none;
            background: var(--input-bg);
            color: var(--text);
            transition: border-color 0.2s;
        }

        input:focus { border-color: #4a90e2; }

        input[type="text"]   { flex: 2; min-width: 160px; }
        input[type="number"] { flex: 1; min-width: 100px; }
        input[type="month"]  { flex: 1; min-width: 140px; }

        button {
            padding: 9px 18px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: bold;
            transition: background 0.2s;
        }

        .btn-add    { background: #4a90e2; color: white; }
        .btn-add:hover { background: #357abd; }

        .btn-filtro { background: #1a1a2e; color: white; }
        .btn-filtro:hover { background: #2d2d4e; }

        .btn-header {
            background: #1a1a2e;
            color: white;
            padding: 9px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: bold;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
            display: inline-block;
        }
        .btn-header:hover { background: #2d2d4e; }

        .nav-mes {
            background: var(--surface);
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 6px var(--shadow);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .nav-mes .mes-atual {
            flex: 1;
            text-align: center;
            font-size: 1.15rem;
            font-weight: bold;
            color: var(--text-heading);
        }

        .btn-nav {
            background: var(--btn-nav-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 7px 14px;
            font-size: 1rem;
            cursor: pointer;
            color: var(--text);
            text-decoration: none;
            line-height: 1;
            transition: background 0.15s;
        }

        .btn-nav:hover { background: var(--btn-nav-hover); }

        .nav-mes form { display: flex; gap: 6px; align-items: center; }

        .tabela-wrap {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 6px var(--shadow);
        }

        table { width: 100%; border-collapse: collapse; }

        th, td {
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-light);
            font-size: 0.95rem;
        }

        th {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-weight: 600;
        }

        tr:last-child td { border-bottom: none; }
        tr:hover td { background: var(--hover-bg); }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            transition: opacity 0.2s;
        }

        .badge:hover { opacity: 0.75; }

        .badge.pago         { background: #d4f5e2; color: #1a7a43; }
        .badge.pendente     { background: #fde8e8; color: #c0392b; }
        .badge.fixo         { background: #e8eaf6; color: #3949ab; font-size: 0.75rem; cursor: default; }
        .badge.esporadico   { background: #fff3e0; color: #e65100; font-size: 0.75rem; cursor: default; }
        .badge.recebido     { background: #d4f5e2; color: #1a7a43; }
        .badge.rec-pendente { background: #fde8e8; color: #c0392b; }

        .grupo-header td {
            background: var(--grupo-bg);
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            padding: 8px 14px;
            border-bottom: 1px solid var(--grupo-border);
        }

        .grupo-header.fixo td       { border-left: 3px solid #3949ab; }
        .grupo-header.esporadico td { border-left: 3px solid #e65100; }

        select {
            padding: 9px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 0.95rem;
            outline: none;
            background: var(--input-bg);
            color: var(--text);
            cursor: pointer;
            transition: border-color 0.2s;
        }
        select:focus { border-color: #4a90e2; }

        .btn-excluir {
            background: none;
            border: none;
            color: var(--icon-color);
            cursor: pointer;
            font-size: 1rem;
            padding: 4px 8px;
            border-radius: 4px;
            transition: color 0.2s;
        }
        .btn-excluir:hover { color: #e74c3c; }

        .btn-excluir-todos {
            background: none;
            border: none;
            color: var(--icon-color);
            cursor: pointer;
            font-size: 0.75rem;
            padding: 4px 6px;
            border-radius: 4px;
            transition: color 0.2s;
            text-decoration: none;
            white-space: nowrap;
        }
        .btn-excluir-todos:hover { color: #e74c3c; }

        .check-todos {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 0.82rem;
            color: var(--check-color);
            white-space: nowrap;
        }
        .check-todos input { accent-color: #4a90e2; cursor: pointer; }

        .btn-editar {
            background: none;
            border: none;
            color: var(--icon-color);
            cursor: pointer;
            font-size: 1rem;
            padding: 4px 8px;
            border-radius: 4px;
            transition: color 0.2s;
            text-decoration: none;
        }
        .btn-editar:hover { color: #4a90e2; }

        tr.editando td { background: var(--editando-bg); }

        .edit-form { display: flex; gap: 6px; align-items: center; }

        .edit-form input[type="number"] {
            width: 110px;
            padding: 6px 10px;
            font-size: 0.9rem;
        }

        .btn-salvar { background: #4a90e2; color: white; padding: 6px 14px; font-size: 0.85rem; }
        .btn-salvar:hover { background: #357abd; }

        .btn-cancelar {
            background: var(--btn-cancel-bg);
            color: var(--btn-cancel-color);
            padding: 6px 12px;
            font-size: 0.85rem;
            border-radius: 6px;
            text-decoration: none;
            display: inline-block;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-cancelar:hover { background: var(--btn-nav-hover); }

        td.valor-col { font-weight: 600; }

        .secao-titulo {
            font-size: 1rem;
            font-weight: 700;
            color: var(--text-heading);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border-light);
        }
        .secao-titulo.receita { border-color: #0d7a4e; color: #0d7a4e; }

        .empty {
            text-align: center;
            padding: 32px;
            color: var(--empty-color);
            font-style: italic;
        }

        /* Vencimento highlights */
        tr.vence-hoje td {
            background: #fde8e8 !important;
        }
        tr.vence-em-breve td {
            background: #fffbe6 !important;
        }
        [data-theme="dark"] tr.vence-hoje td {
            background: #3d1a1a !important;
        }
        [data-theme="dark"] tr.vence-em-breve td {
            background: #2d2800 !important;
        }

        /* Meta de gastos */
        .progresso-wrap {
            margin-top: 12px;
            background: var(--border-light);
            border-radius: 8px;
            height: 14px;
            overflow: hidden;
            position: relative;
        }
        .progresso-bar {
            height: 100%;
            border-radius: 8px;
            transition: width 0.4s;
            min-width: 2px;
        }
        .progresso-bar.ok      { background: #27ae60; }
        .progresso-bar.alerta  { background: #f39c12; }
        .progresso-bar.critico { background: #e74c3c; }

        /* Alertas banner */
        .alerta-banner {
            position: sticky;
            top: 0;
            z-index: 100;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 16px;
            font-size: 0.92rem;
            display: flex;
            align-items: flex-start;
            gap: 12px;
            box-shadow: 0 2px 8px var(--shadow);
        }
        .alerta-banner.tem-atrasados {
            background: #fde8e8;
            border-left: 4px solid #e74c3c;
            color: #7b1a1a;
        }
        .alerta-banner.so-proximos {
            background: #fffbe6;
            border-left: 4px solid #f39c12;
            color: #5c4000;
        }
        [data-theme="dark"] .alerta-banner.tem-atrasados {
            background: #3d1a1a;
            border-left-color: #e74c3c;
            color: #f8b4b4;
        }
        [data-theme="dark"] .alerta-banner.so-proximos {
            background: #2d2800;
            border-left-color: #f39c12;
            color: #ffd97a;
        }
        .alerta-banner .fechar-banner {
            margin-left: auto;
            background: none;
            border: none;
            font-size: 1.1rem;
            cursor: pointer;
            color: inherit;
            opacity: 0.7;
            padding: 0 4px;
            font-weight: bold;
            flex-shrink: 0;
        }
        .alerta-banner .fechar-banner:hover { opacity: 1; }
        .alerta-banner ul { margin: 6px 0 0 0; padding-left: 18px; }
        .alerta-banner ul li { margin-bottom: 2px; }
    </style>
</head>
<body>

<!-- Banner de alertas (preenchido via JS) -->
<div id="alerta-banner-container"></div>

<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
    <h1 style="margin:0">Controle de Gastos</h1>
    <div style="display:flex;gap:8px;align-items:center">
        <button id="theme-toggle" class="btn-header" onclick="toggleTheme()">🌙</button>
        <a href="/comparativo" class="btn-header">&#8646; Comparativo</a>
        <a href="/dashboard" class="btn-header">&#9998; Dashboard</a>
    </div>
</div>

<!-- Cards de resumo -->
<div class="cards">
    <div class="card total">
        <div class="label">Total</div>
        <div class="valor">R$ {{ "%.2f"|format(total) }}</div>
    </div>
    <div class="card pagos">
        <div class="label">Pago</div>
        <div class="valor">R$ {{ "%.2f"|format(pagos) }}</div>
    </div>
    <div class="card pendentes">
        <div class="label">Pendente</div>
        <div class="valor">R$ {{ "%.2f"|format(pendentes) }}</div>
    </div>
    <div class="card fixos">
        <div class="label">Fixos</div>
        <div class="valor">R$ {{ "%.2f"|format(total_fixos) }}</div>
    </div>
    <div class="card esporadicos">
        <div class="label">Esporádicos</div>
        <div class="valor">R$ {{ "%.2f"|format(total_esporadicos) }}</div>
    </div>
    <div class="card receitas">
        <div class="label">Receitas</div>
        <div class="valor">R$ {{ "%.2f"|format(total_receitas) }}</div>
    </div>
    <div class="card recebido">
        <div class="label">Recebido</div>
        <div class="valor">R$ {{ "%.2f"|format(recebido) }}</div>
    </div>
    <div class="card {{ 'saldo-pos' if saldo >= 0 else 'saldo-neg' }}">
        <div class="label">Saldo</div>
        <div class="valor">R$ {{ "%.2f"|format(saldo) }}</div>
    </div>
</div>

<!-- Navegador de meses -->
<div class="nav-mes">
    <a href="/?mes={{ mes_anterior }}" class="btn-nav">&#8592;</a>
    <span class="mes-atual">{{ mes_label }}</span>
    <a href="/?mes={{ mes_seguinte }}" class="btn-nav">&#8594;</a>
    <form method="GET" action="/" style="margin-left:auto">
        <input type="month" name="mes" value="{{ mes }}">
        <button type="submit" class="btn-filtro" style="padding:7px 14px;font-size:0.9rem">Ir</button>
    </form>
</div>

<!-- Meta de gastos -->
<div class="painel">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <h2 style="margin:0">Meta de gastos — {{ mes_label }}</h2>
        {% if meta %}
        <span style="font-size:0.85rem;color:var(--text-muted)">
            R$ {{ "%.2f"|format(total) }} / R$ {{ "%.2f"|format(meta) }}
            {% if meta_pct is not none %} ({{ meta_pct }}%){% endif %}
        </span>
        {% endif %}
    </div>
    <form method="POST" action="/meta/salvar">
        <input type="hidden" name="mes" value="{{ mes }}">
        <div class="linha">
            <input type="number" name="limite" placeholder="Limite mensal (R$)" step="0.01" min="0"
                   value="{{ '%.2f'|format(meta) if meta else '' }}" style="max-width:200px">
            <button type="submit" class="btn-add" style="padding:9px 16px">Definir meta</button>
        </div>
    </form>
    {% if meta and meta > 0 %}
    {% set pct_bar = [meta_pct, 100] | min %}
    {% set bar_cls = 'critico' if meta_pct >= 100 else ('alerta' if meta_pct >= 70 else 'ok') %}
    <div class="progresso-wrap" style="margin-top:14px">
        <div class="progresso-bar {{ bar_cls }}" style="width:{{ pct_bar }}%"></div>
    </div>
    {% endif %}
</div>

<!-- Formulário de novo gasto -->
<div class="painel">
    <h2>Adicionar gasto</h2>
    <form method="POST" action="/adicionar">
        <input type="hidden" name="mes" value="{{ mes }}">
        <div class="linha">
            <input type="text" name="nome" placeholder="Nome do gasto" list="lista-nomes-gastos" autocomplete="off" required>
            <datalist id="lista-nomes-gastos">
                {% for n in nomes_gastos %}<option value="{{ n }}">{% endfor %}
            </datalist>
            <input type="number" name="valor" placeholder="Valor (R$)" step="0.01" min="0" required>
            <select name="tipo">
                <option value="Fixo">Fixo</option>
                <option value="Esporádico">Esporádico</option>
            </select>
            <input type="number" name="vencimento" placeholder="Venc. (dia)" min="1" max="31"
                   style="max-width:100px" title="Dia de vencimento (1-31, opcional)">
            <input type="number" name="meses" placeholder="Meses" min="1" max="120" style="max-width:90px" title="Quantos meses repetir (vazio = só este mês)">
            <button type="submit" class="btn-add">+ Adicionar</button>
        </div>
    </form>
</div>

<!-- Tabela de gastos -->
<div class="tabela-wrap">
    {% if gastos %}
    <table>
        <thead>
            <tr>
                <th>Nome</th>
                <th>Valor</th>
                <th>Venc.</th>
                <th>Status</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for grupo, rotulo, cls in [(gastos_fixos, 'Fixos', 'fixo'), (gastos_esporadicos, 'Esporádicos', 'esporadico')] %}
            {% if grupo %}
            <tr class="grupo-header {{ cls }}">
                <td colspan="5">{{ rotulo }}</td>
            </tr>
            {% for g in grupo %}
            {% set editando = (g[0] == editar_id) %}
            {% if eh_mes_atual and g[5] is not none and g[3] == 'Pendente' %}
                {% if g[5] <= dia_hoje %}
                    {% set row_cls = 'vence-hoje' %}
                {% elif g[5] <= dia_hoje + 3 %}
                    {% set row_cls = 'vence-em-breve' %}
                {% else %}
                    {% set row_cls = '' %}
                {% endif %}
            {% else %}
                {% set row_cls = '' %}
            {% endif %}
            <tr class="{{ 'editando' if editando else row_cls }}">
                <td>{{ g[1] }}</td>
                <td class="valor-col">
                    {% if editando %}
                    <form class="edit-form" method="POST" action="/editar/{{ g[0] }}" style="flex-wrap:wrap">
                        <input type="hidden" name="mes" value="{{ mes }}">
                        <input type="number" name="valor" value="{{ '%.2f'|format(g[2]) }}"
                               step="0.01" min="0" required autofocus>
                        <input type="number" name="vencimento" value="{{ g[5] or '' }}"
                               min="1" max="31" placeholder="Dia venc." style="max-width:90px">
                        <label class="check-todos">
                            <input type="checkbox" name="todos"> Todos os meses
                        </label>
                        <button type="submit" class="btn-salvar">Salvar</button>
                        <a href="/?mes={{ mes }}" class="btn-cancelar">Cancelar</a>
                    </form>
                    {% else %}
                    R$ {{ "%.2f"|format(g[2]) }}
                    {% endif %}
                </td>
                <td style="color:var(--text-muted);font-size:0.9rem">
                    {{ 'dia ' ~ g[5] if g[5] else '—' }}
                </td>
                <td>
                    <a href="/toggle/{{ g[0] }}?mes={{ mes }}"
                       class="badge {{ 'pago' if g[3] == 'Pago' else 'pendente' }}">
                        {{ g[3] }}
                    </a>
                </td>
                <td style="white-space:nowrap">
                    {% if not editando %}
                    <a href="/?mes={{ mes }}&editar={{ g[0] }}"
                       class="btn-editar" title="Editar valor">&#9998;</a>
                    {% endif %}
                    <a href="/excluir/{{ g[0] }}?mes={{ mes }}"
                       onclick="return confirm('Excluir este gasto?')"
                       class="btn-excluir" title="Excluir este mês">&#10005;</a>
                    <a href="/excluir-todos/{{ g[0] }}?mes={{ mes }}"
                       onclick="return confirm('Excluir TODAS as ocorrências de \'{{ g[1] }}\'?')"
                       class="btn-excluir-todos" title="Excluir todos os meses">&#10005; todos</a>
                </td>
            </tr>
            {% endfor %}
            {% endif %}
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">Nenhum gasto cadastrado para este mês.</div>
    {% endif %}
</div>

<!-- Formulário de nova receita -->
<div class="painel" style="margin-top:32px">
    <div class="secao-titulo receita">Receitas</div>
    <h2 style="margin-bottom:12px">Adicionar receita</h2>
    <form method="POST" action="/receita/adicionar">
        <input type="hidden" name="mes" value="{{ mes }}">
        <div class="linha">
            <input type="text" name="nome" placeholder="Nome da receita" list="lista-nomes-receitas" autocomplete="off" required>
            <datalist id="lista-nomes-receitas">
                {% for n in nomes_receitas %}<option value="{{ n }}">{% endfor %}
            </datalist>
            <input type="number" name="valor" placeholder="Valor (R$)" step="0.01" min="0" required>
            <input type="number" name="meses" placeholder="Meses" min="1" max="120" style="max-width:90px" title="Quantos meses repetir (vazio = só este mês)">
            <button type="submit" class="btn-add" style="background:#0d7a4e">+ Adicionar</button>
        </div>
    </form>
</div>

<!-- Tabela de receitas -->
<div class="tabela-wrap">
    {% if receitas %}
    <table>
        <thead>
            <tr>
                <th>Nome</th>
                <th>Valor</th>
                <th>Status</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for r in receitas %}
            {% set editando = (r[0] == editar_receita_id) %}
            <tr class="{{ 'editando' if editando else '' }}">
                <td>{{ r[1] }}</td>
                <td class="valor-col">
                    {% if editando %}
                    <form class="edit-form" method="POST" action="/receita/editar/{{ r[0] }}" style="flex-wrap:wrap">
                        <input type="hidden" name="mes" value="{{ mes }}">
                        <input type="number" name="valor" value="{{ '%.2f'|format(r[2]) }}"
                               step="0.01" min="0" required autofocus>
                        <label class="check-todos">
                            <input type="checkbox" name="todos"> Todos os meses
                        </label>
                        <button type="submit" class="btn-salvar">Salvar</button>
                        <a href="/?mes={{ mes }}" class="btn-cancelar">Cancelar</a>
                    </form>
                    {% else %}
                    R$ {{ "%.2f"|format(r[2]) }}
                    {% endif %}
                </td>
                <td>
                    <a href="/receita/toggle/{{ r[0] }}?mes={{ mes }}"
                       class="badge {{ 'recebido' if r[3] == 'Recebido' else 'rec-pendente' }}">
                        {{ r[3] }}
                    </a>
                </td>
                <td style="white-space:nowrap">
                    {% if not editando %}
                    <a href="/?mes={{ mes }}&editar_receita={{ r[0] }}"
                       class="btn-editar" title="Editar valor">&#9998;</a>
                    {% endif %}
                    <a href="/receita/excluir/{{ r[0] }}?mes={{ mes }}"
                       onclick="return confirm('Excluir esta receita?')"
                       class="btn-excluir" title="Excluir este mês">&#10005;</a>
                    <a href="/receita/excluir-todos/{{ r[0] }}?mes={{ mes }}"
                       onclick="return confirm('Excluir TODAS as ocorrências de \'{{ r[1] }}\'?')"
                       class="btn-excluir-todos" title="Excluir todos os meses">&#10005; todos</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">Nenhuma receita cadastrada para este mês.</div>
    {% endif %}
</div>

<script>
function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
document.getElementById('theme-toggle').textContent =
    document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';

// Notificações de vencimento
(function() {
    fetch('/api/alertas?mes={{ mes }}')
        .then(r => r.json())
        .then(data => {
            if (!data.alertas || data.alertas.length === 0) return;
            const alertas = data.alertas;
            const temAtrasados = alertas.some(a => a.diff <= 0);
            const container = document.getElementById('alerta-banner-container');
            const banner = document.createElement('div');
            banner.className = 'alerta-banner ' + (temAtrasados ? 'tem-atrasados' : 'so-proximos');

            let html = '<div style="flex:1">';
            html += '<strong>' + (temAtrasados ? '⚠ Gastos em atraso ou vencendo em breve' : '⏰ Gastos vencendo em breve') + '</strong>';
            html += '<ul>';
            alertas.forEach(a => {
                const diffTxt = a.diff < 0
                    ? `atrasado ${Math.abs(a.diff)} dia(s)`
                    : a.diff === 0
                        ? 'vence hoje'
                        : `vence em ${a.diff} dia(s)`;
                html += `<li><strong>${a.nome}</strong> — R$ ${a.valor.toFixed(2)} — dia ${a.vencimento} (${diffTxt})</li>`;
            });
            html += '</ul></div>';
            html += '<button class="fechar-banner" onclick="this.closest(\'.alerta-banner\').remove()" title="Fechar">&#10005;</button>';
            banner.innerHTML = html;
            container.appendChild(banner);
        })
        .catch(() => {});
})();
</script>

</body>
</html>
"""


COMPARATIVO_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comparativo de Meses — Controle de Gastos</title>
    <script>(function(){const t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);})();</script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg: #f0f2f5;
            --surface: #ffffff;
            --text: #333333;
            --text-muted: #888888;
            --text-heading: #1a1a2e;
            --border: #dddddd;
            --border-light: #f0f0f0;
            --input-bg: #ffffff;
            --hover-bg: #fafafa;
            --shadow: rgba(0,0,0,0.07);
            --empty-color: #bbbbbb;
        }

        [data-theme="dark"] {
            --bg: #0f1117;
            --surface: #1a1d27;
            --text: #cbd5e1;
            --text-muted: #64748b;
            --text-heading: #f1f5f9;
            --border: #2d3748;
            --border-light: #252a38;
            --input-bg: #252a38;
            --hover-bg: #212636;
            --shadow: rgba(0,0,0,0.35);
            --empty-color: #4a5568;
        }

        body {
            font-family: Arial, sans-serif;
            max-width: 1000px;
            margin: 40px auto;
            padding: 20px;
            background: var(--bg);
            color: var(--text);
            transition: background 0.2s, color 0.2s;
        }

        h1 { font-size: 1.8rem; color: var(--text-heading); }
        h2 { font-size: 1.1rem; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }

        .btn-header {
            background: #1a1a2e;
            color: white;
            padding: 9px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: bold;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
            display: inline-block;
        }
        .btn-header:hover { background: #2d2d4e; }

        .painel {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .linha { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }

        input[type="month"] {
            padding: 9px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 0.95rem;
            outline: none;
            background: var(--input-bg);
            color: var(--text);
            transition: border-color 0.2s;
        }
        input[type="month"]:focus { border-color: #4a90e2; }

        button {
            padding: 9px 18px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: bold;
            transition: background 0.2s;
        }

        .btn-comparar { background: #4a90e2; color: white; }
        .btn-comparar:hover { background: #357abd; }

        .cards-comp {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-bottom: 24px;
        }
        @media (max-width: 700px) { .cards-comp { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 450px) { .cards-comp { grid-template-columns: 1fr; } }

        .card {
            background: var(--surface);
            border-radius: 10px;
            padding: 18px;
            text-align: center;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .card .label {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .card .valor { font-size: 1.4rem; font-weight: bold; color: var(--text-heading); }
        .card .valor.pos { color: #27ae60; }
        .card .valor.neg { color: #e74c3c; }

        .tabela-wrap {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 6px var(--shadow);
            margin-bottom: 24px;
        }

        table { width: 100%; border-collapse: collapse; }

        th, td {
            padding: 11px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-light);
            font-size: 0.93rem;
        }

        th {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-weight: 600;
        }

        tr:last-child td { border-bottom: none; }
        tr:hover td { background: var(--hover-bg); }

        td.diff-pos { color: #27ae60; font-weight: 600; }
        td.diff-neg { color: #e74c3c; font-weight: 600; }
        td.diff-neutro { color: var(--text-muted); }

        .badge-tipo {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .badge-tipo.fixo       { background: #e8eaf6; color: #3949ab; }
        .badge-tipo.esporadico { background: #fff3e0; color: #e65100; }

        .empty { text-align: center; padding: 32px; color: var(--empty-color); font-style: italic; }
    </style>
</head>
<body>

<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
    <h1 style="margin:0">Comparativo de Meses</h1>
    <div style="display:flex;gap:8px;align-items:center">
        <button id="theme-toggle" class="btn-header" onclick="toggleTheme()">🌙</button>
        <a href="/" class="btn-header">&#8592; Voltar</a>
    </div>
</div>

<!-- Seletor de meses -->
<div class="painel">
    <form method="GET" action="/comparativo">
        <div class="linha">
            <label style="font-size:0.9rem;color:var(--text-muted);white-space:nowrap">Mês A:</label>
            <input type="month" name="mes_a" value="{{ mes_a }}">
            <label style="font-size:0.9rem;color:var(--text-muted);white-space:nowrap">Mês B:</label>
            <input type="month" name="mes_b" value="{{ mes_b }}">
            <button type="submit" class="btn-comparar">Comparar</button>
        </div>
    </form>
</div>

<!-- Cards de resumo -->
<div class="cards-comp">
    <div class="card">
        <div class="label">Gastos — {{ mes_label_a }}</div>
        <div class="valor">R$ {{ "%.2f"|format(total_gastos_a) }}</div>
    </div>
    <div class="card">
        <div class="label">Gastos — {{ mes_label_b }}</div>
        <div class="valor">R$ {{ "%.2f"|format(total_gastos_b) }}</div>
    </div>
    <div class="card">
        <div class="label">Δ Gastos</div>
        {% set dg = delta_gastos %}
        <div class="valor {{ 'neg' if dg > 0 else ('pos' if dg < 0 else '') }}">
            {{ ('+' if dg > 0 else '') }}R$ {{ "%.2f"|format(dg) }}
        </div>
    </div>
    <div class="card">
        <div class="label">Receitas — {{ mes_label_a }}</div>
        <div class="valor pos">R$ {{ "%.2f"|format(total_receitas_a) }}</div>
    </div>
    <div class="card">
        <div class="label">Receitas — {{ mes_label_b }}</div>
        <div class="valor pos">R$ {{ "%.2f"|format(total_receitas_b) }}</div>
    </div>
    <div class="card">
        <div class="label">Δ Receitas</div>
        {% set dr = delta_receitas %}
        <div class="valor {{ 'pos' if dr > 0 else ('neg' if dr < 0 else '') }}">
            {{ ('+' if dr > 0 else '') }}R$ {{ "%.2f"|format(dr) }}
        </div>
    </div>
</div>

<!-- Tabela de gastos -->
<div class="tabela-wrap">
    <h2>Gastos comparados</h2>
    {% if tabela_gastos %}
    <table>
        <thead>
            <tr>
                <th>Nome</th>
                <th>Tipo</th>
                <th>{{ mes_label_a }}</th>
                <th>{{ mes_label_b }}</th>
                <th>Diferença</th>
            </tr>
        </thead>
        <tbody>
            {% for row in tabela_gastos %}
            <tr>
                <td>{{ row.nome }}</td>
                <td>
                    <span class="badge-tipo {{ 'fixo' if row.tipo == 'Fixo' else 'esporadico' }}">
                        {{ row.tipo }}
                    </span>
                </td>
                <td>{% if row.valor_a %}R$ {{ "%.2f"|format(row.valor_a) }}{% else %}<span style="color:var(--text-muted)">—</span>{% endif %}</td>
                <td>{% if row.valor_b %}R$ {{ "%.2f"|format(row.valor_b) }}{% else %}<span style="color:var(--text-muted)">—</span>{% endif %}</td>
                <td class="{{ 'diff-neg' if row.diff > 0 else ('diff-pos' if row.diff < 0 else 'diff-neutro') }}">
                    {{ ('+' if row.diff > 0 else '') }}R$ {{ "%.2f"|format(row.diff) }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">Nenhum gasto encontrado nos meses selecionados.</div>
    {% endif %}
</div>

<!-- Tabela de receitas -->
<div class="tabela-wrap">
    <h2>Receitas comparadas</h2>
    {% if tabela_receitas %}
    <table>
        <thead>
            <tr>
                <th>Nome</th>
                <th>{{ mes_label_a }}</th>
                <th>{{ mes_label_b }}</th>
                <th>Diferença</th>
            </tr>
        </thead>
        <tbody>
            {% for row in tabela_receitas %}
            <tr>
                <td>{{ row.nome }}</td>
                <td>{% if row.valor_a %}R$ {{ "%.2f"|format(row.valor_a) }}{% else %}<span style="color:var(--text-muted)">—</span>{% endif %}</td>
                <td>{% if row.valor_b %}R$ {{ "%.2f"|format(row.valor_b) }}{% else %}<span style="color:var(--text-muted)">—</span>{% endif %}</td>
                <td class="{{ 'diff-pos' if row.diff > 0 else ('diff-neg' if row.diff < 0 else 'diff-neutro') }}">
                    {{ ('+' if row.diff > 0 else '') }}R$ {{ "%.2f"|format(row.diff) }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">Nenhuma receita encontrada nos meses selecionados.</div>
    {% endif %}
</div>

<script>
function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
document.getElementById('theme-toggle').textContent =
    document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
</script>

</body>
</html>
"""


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard — Controle de Gastos</title>
    <script>(function(){const t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);})();</script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg: #f0f2f5; --surface: #ffffff; --text: #333333;
            --text-muted: #888888; --text-heading: #1a1a2e;
            --border-light: #f0f0f0; --hover-bg: #fafafa;
            --shadow: rgba(0,0,0,0.07); --empty-color: #bbbbbb;
        }

        [data-theme="dark"] {
            --bg: #0f1117; --surface: #1a1d27; --text: #cbd5e1;
            --text-muted: #64748b; --text-heading: #f1f5f9;
            --border-light: #252a38; --hover-bg: #212636;
            --shadow: rgba(0,0,0,0.35); --empty-color: #4a5568;
        }

        body {
            font-family: Arial, sans-serif;
            max-width: 1100px;
            margin: 40px auto;
            padding: 20px;
            background: var(--bg);
            color: var(--text);
            transition: background 0.2s, color 0.2s;
        }

        .topo { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; }

        h1 { font-size: 1.8rem; color: var(--text-heading); }

        .btn-header {
            background: #1a1a2e;
            color: white;
            padding: 9px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: bold;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
            display: inline-block;
        }
        .btn-header:hover { background: #2d2d4e; }

        .cards {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }

        .card {
            background: var(--surface);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .card .label {
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }

        .card .valor { font-size: 1.4rem; font-weight: bold; }

        .card.total-gastos .valor   { color: #e74c3c; }
        .card.total-pago .valor     { color: #c0392b; }
        .card.total-receitas .valor { color: #0d7a4e; }
        .card.total-recebido .valor { color: #0d7a4e; }
        .card.saldo-pos .valor      { color: #0d7a4e; }
        .card.saldo-neg .valor      { color: #e74c3c; }

        .grafico-wrap {
            background: var(--surface);
            border-radius: 10px;
            padding: 24px;
            box-shadow: 0 2px 6px var(--shadow);
            margin-bottom: 28px;
        }

        .grafico-wrap h2 { font-size: 1rem; color: var(--text-muted); margin-bottom: 20px; }

        .tabela-wrap {
            background: var(--surface);
            border-radius: 10px;
            padding: 24px;
            box-shadow: 0 2px 6px var(--shadow);
        }

        .tabela-wrap h2 { font-size: 1rem; color: var(--text-muted); margin-bottom: 16px; }

        table { width: 100%; border-collapse: collapse; }

        th, td {
            padding: 11px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-light);
            font-size: 0.93rem;
        }

        th {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-weight: 600;
        }

        tr:last-child td { border-bottom: none; }
        tr:hover td { background: var(--hover-bg); }

        td.pos { color: #0d7a4e; font-weight: 600; }
        td.neg { color: #e74c3c; font-weight: 600; }
        td.receita-col { color: #0d7a4e; font-weight: 600; }
        td.gasto-col   { color: #e74c3c; font-weight: 600; }

        .empty { text-align: center; padding: 48px; color: var(--empty-color); font-style: italic; }

        @media (max-width: 800px) {
            .cards { grid-template-columns: repeat(3, 1fr); }
            .graficos-grid { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 500px)  { .cards { grid-template-columns: repeat(2, 1fr); } }
    </style>
</head>
<body>

<div class="topo">
    <h1>Dashboard</h1>
    <div style="display:flex;gap:8px;align-items:center">
        <button id="theme-toggle" class="btn-header" onclick="toggleTheme()">🌙</button>
        <a href="/comparativo?mes_a={{ mes_anterior }}&mes_b={{ mes_atual }}" class="btn-header">&#8646; Comparativo</a>
        <a href="/" class="btn-header">&#8592; Voltar</a>
    </div>
</div>

<!-- Cards de totais globais -->
<div class="cards">
    <div class="card total-receitas">
        <div class="label">Total Receitas</div>
        <div class="valor">R$ {{ "%.2f"|format(total_receitas) }}</div>
    </div>
    <div class="card total-recebido">
        <div class="label">Recebido</div>
        <div class="valor">R$ {{ "%.2f"|format(total_recebido) }}</div>
    </div>
    <div class="card total-gastos">
        <div class="label">Total Gastos</div>
        <div class="valor">R$ {{ "%.2f"|format(total_gastos) }}</div>
    </div>
    <div class="card total-pago">
        <div class="label">Pago</div>
        <div class="valor">R$ {{ "%.2f"|format(total_pago) }}</div>
    </div>
    <div class="card {{ 'saldo-pos' if saldo_geral >= 0 else 'saldo-neg' }}">
        <div class="label">Saldo Geral</div>
        <div class="valor">R$ {{ "%.2f"|format(saldo_geral) }}</div>
    </div>
</div>

<!-- Gráficos lado a lado -->
<div class="graficos-grid" style="display:grid;grid-template-columns:1fr 340px;gap:20px;margin-bottom:28px">

    <div class="grafico-wrap" style="margin-bottom:0">
        <h2>Receitas vs Gastos por mês</h2>
        {% if tabela %}
        <canvas id="grafico" height="110"></canvas>
        {% else %}
        <div class="empty">Nenhum dado cadastrado ainda.</div>
        {% endif %}
    </div>

    <div class="grafico-wrap" style="margin-bottom:0;display:flex;flex-direction:column">
        <h2>Resumo geral</h2>
        {% if total_receitas or total_gastos %}
        <div style="flex:1;display:flex;align-items:center;justify-content:center">
            <canvas id="grafico-resumo"></canvas>
        </div>
        {% else %}
        <div class="empty">Nenhum dado cadastrado ainda.</div>
        {% endif %}
    </div>

</div>

<!-- Tabela mensal -->
<div class="tabela-wrap">
    <h2>Resumo mensal</h2>
    {% if tabela %}
    <table>
        <thead>
            <tr>
                <th>Mês</th>
                <th>Receitas</th>
                <th>Gastos</th>
                <th>Saldo</th>
            </tr>
        </thead>
        <tbody>
            {% for row in tabela %}
            <tr>
                <td>{{ row.mes }}</td>
                <td class="receita-col">R$ {{ "%.2f"|format(row.receitas) }}</td>
                <td class="gasto-col">R$ {{ "%.2f"|format(row.gastos) }}</td>
                <td class="{{ 'pos' if row.saldo >= 0 else 'neg' }}">R$ {{ "%.2f"|format(row.saldo) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">Nenhum dado cadastrado ainda.</div>
    {% endif %}
</div>

<script>
const ctx = document.getElementById('grafico');
if (ctx) {
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: {{ meses_labels | tojson }},
            datasets: [
                {
                    label: 'Receitas',
                    data: {{ valores_receitas | tojson }},
                    backgroundColor: 'rgba(13, 122, 78, 0.7)',
                    borderColor: 'rgba(13, 122, 78, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'Gastos',
                    data: {{ valores_gastos | tojson }},
                    backgroundColor: 'rgba(231, 76, 60, 0.7)',
                    borderColor: 'rgba(231, 76, 60, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'Saldo',
                    data: {{ valores_saldo | tojson }},
                    type: 'line',
                    borderColor: '#4a90e2',
                    backgroundColor: 'rgba(74, 144, 226, 0.1)',
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: '#4a90e2',
                    fill: false,
                    tension: 0.3,
                    yAxisID: 'y',
                },
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.y;
                            return ` ${ctx.dataset.label}: R$ ${v.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: () => getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim(),
                        callback: v => 'R$ ' + v.toLocaleString('pt-BR', {minimumFractionDigits: 2})
                    },
                    grid: { color: () => getComputedStyle(document.documentElement).getPropertyValue('--border-light').trim() }
                },
                x: {
                    ticks: { color: () => getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() },
                    grid: { color: () => getComputedStyle(document.documentElement).getPropertyValue('--border-light').trim() }
                }
            }
        }
    });
}
</script>

<script>
const resumoCtx = document.getElementById('grafico-resumo');
if (resumoCtx) {
    const saldo = {{ saldo_geral }};
    new Chart(resumoCtx, {
        type: 'doughnut',
        data: {
            labels: ['Receitas', 'Gastos', saldo >= 0 ? 'Saldo positivo' : 'Saldo negativo'],
            datasets: [{
                data: [{{ total_receitas }}, {{ total_gastos }}, Math.abs(saldo)],
                backgroundColor: [
                    'rgba(13, 122, 78, 0.8)',
                    'rgba(231, 76, 60, 0.8)',
                    saldo >= 0 ? 'rgba(74, 144, 226, 0.8)' : 'rgba(180, 50, 30, 0.8)',
                ],
                borderColor: [
                    'rgba(13, 122, 78, 1)',
                    'rgba(231, 76, 60, 1)',
                    saldo >= 0 ? 'rgba(74, 144, 226, 1)' : 'rgba(180, 50, 30, 1)',
                ],
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: () => getComputedStyle(document.documentElement).getPropertyValue('--text').trim(),
                        padding: 12,
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ` R$ ${ctx.parsed.toFixed(2)}`
                    }
                }
            }
        }
    });
}

function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
document.getElementById('theme-toggle').textContent =
    document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
</script>

</body>
</html>
"""


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
