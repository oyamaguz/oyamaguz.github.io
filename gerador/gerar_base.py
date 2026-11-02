"""
Gera a base fictícia da DemoFoods usada pelas três demonstrações do portfólio.

Nada aqui vem de dado real: o script não lê nenhum arquivo. Tudo é criado a
partir dos parâmetros abaixo, com valor aleatório fixo (rodar de novo gera a mesma base).

Mundo: uma indústria de alimentos que processa matéria-prima e envasa o produto
final em três fábricas. As três demonstrações usam os MESMOS lotes:
  1. monitoramento.json  -> painel de processamento e envase (com alertas)
  2. planejamento.json   -> plano de etapas por fábrica (demanda, embalagens, insumos)
  3. automacoes.json     -> logs simulados dos lançamentos no ERP

Uso: python gerar_base.py   (só biblioteca padrão; grava em ../dados/)
"""

import json
import math
import os
import random
from collections import defaultdict
from datetime import date, timedelta

# ============================== PARÂMETROS ==============================

ALEATORIO_FIXO = 2025
INICIO = date(2025, 6, 2)
CORTE = date(2025, 10, 13)          # "hoje" no mundo fictício
SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dados")

FABRICAS = {"Fábrica 1": 0.45, "Fábrica 2": 0.35, "Fábrica 3": 0.20}
N_PRODUTOS = 10
N_FORNECEDORES = 30
N_LOTES_MP = 60                      # lotes de matéria-prima
UN_MEDIA_LOTE_PROC = 500             # unidades por lote processado
UN_POR_PACK_IND = 40                 # unidades equivalentes por embalagem industrial
CATEGORIAS = ["A", "B", "C", "D", "E", "F"]

# regras de negócio (fictícias)
TOL_EMB_VAREJO = 0.04                # embalagens consumidas × projetadas
TOL_EMB_INDUSTRIAL = 1               # ± embalagens
TOL_REND = 0.06                      # rendimento: atenção
TOL_REND_CRIT = 0.12                 # rendimento: crítico
TOL_PESO = 0.015                     # peso por unidade informado × contagem
MARGEM_SEGURANCA = 0.03              # necessidade de embalagens e insumos

# frequência das anomalias plantadas (para os alertas terem o que mostrar)
P_REND_FORA = 0.03
P_PESO_FORA = 0.015
P_EMB_FORA = 0.04
P_EMB_SEM_LANC = 0.02
P_SEM_REPORTE = 0.01
P_QUALIDADE_PEND = 0.01

rnd = random.Random(ALEATORIO_FIXO)


def iso(d):
    return d.isoformat() if d else None


def arred(v, n=0):
    return None if v is None else (round(v, n) if n else int(round(v)))


def escolhe_pesado(opcoes):
    """opcoes: dict {valor: peso}"""
    return rnd.choices(list(opcoes), weights=list(opcoes.values()))[0]


# ============================== CADASTROS ==============================

produtos = []
for i in range(1, N_PRODUTOS + 1):
    pref_ind = rnd.choice([0.0, 0.0, 0.15, 0.3, 0.5])     # parte industrial da demanda
    cat_pesos = [rnd.uniform(0.5, 3) for _ in CATEGORIAS]
    cat_pesos[0] *= 1.6; cat_pesos[1] *= 1.8               # A e B mais comuns
    produtos.append(dict(
        produto=f"SKU-{i:02d}",
        peso_un=rnd.choice([18, 20, 20, 22, 25]),         # kg por unidade de varejo
        pref_industrial=pref_ind,
        cat_pesos=cat_pesos,
    ))
P = {p["produto"]: p for p in produtos}

# cada fábrica trabalha com 4 a 5 produtos
fab_produtos = {}
nomes_prod = [p["produto"] for p in produtos]
for f in FABRICAS:
    fab_produtos[f] = sorted(rnd.sample(nomes_prod, rnd.choice([4, 5])))

fornecedores = [f"Fornecedor {i:02d}" for i in range(1, N_FORNECEDORES + 1)]

# ========================== MATÉRIA-PRIMA ==========================

def data_entrada():
    # entradas concentradas no meio da janela
    dias = (CORTE - INICIO).days
    x = rnd.betavariate(2.2, 2.0)
    return INICIO + timedelta(days=int(x * (dias - 5)))

N_FUTUROS = 6                                              # lotes previstos que ainda vão entrar
# fábrica de cada lote na proporção exata do porte (sorteio puro distorce com 60 lotes)
fab_lotes = [f for f, w in FABRICAS.items() for _ in range(round(w * (N_LOTES_MP + N_FUTUROS)))]
rnd.shuffle(fab_lotes)
lotes_mp = []
for i, fab in enumerate(fab_lotes, 1):
    prod = rnd.choice(fab_produtos[fab])
    prev = arred(rnd.lognormvariate(math.log(6500), 0.45) / 10) * 10
    futuro = i > N_LOTES_MP
    entrada = CORTE + timedelta(days=rnd.randint(2, 35)) if futuro else data_entrada()
    lotes_mp.append(dict(
        lote_mp=f"MP-{i:03d}", fornecedor=rnd.choice(fornecedores), fabrica=fab,
        produto=prod, entrada=entrada, previsao=prev,
    ))
lotes_mp.sort(key=lambda r: r["entrada"])
for i, r in enumerate(lotes_mp, 1):                       # numera na ordem de entrada
    r["lote_mp"] = f"MP-{i:03d}"
MP = {r["lote_mp"]: r for r in lotes_mp}

# anomalias de cadastro: 2 lotes sem previsão
for r in rnd.sample([r for r in lotes_mp if r["entrada"] < CORTE - timedelta(days=40)], 2):
    r["sem_previsao"] = True

# ========================== LOTES PROCESSADOS ==========================

lotes_proc = []
seq_proc = 0
for mp in lotes_mp:
    inicio = mp["entrada"] + timedelta(days=rnd.randint(4, 12))
    janela = rnd.randint(10, 32)
    fim = inicio + timedelta(days=janela)
    mp["fim_previsto_proc"] = fim
    total = mp["previsao"] * rnd.gauss(0.97, 0.05)
    n = max(1, round(total / UN_MEDIA_LOTE_PROC))
    for k in range(n):
        d = inicio + timedelta(days=int(janela * (k + rnd.random()) / n))
        if d > CORTE:
            continue
        seq_proc += 1
        un = max(120, min(1000, rnd.gauss(total / n, total / n * 0.18)))
        prod = P[mp["produto"]]
        lotes_proc.append(dict(
            lote=None, fabrica=mp["fabrica"], produto=mp["produto"], origem=[(mp["lote_mp"], 1.0)],
            categoria=rnd.choices(CATEGORIAS, weights=prod["cat_pesos"])[0],
            un=arred(un), kg=arred(un * prod["peso_un"] * rnd.gauss(1, 0.01)), data=d,
        ))

# misturas: ~15% dos lotes processados juntam dois lotes de MP (mesma fábrica e produto)
por_chave = defaultdict(list)
for mp in lotes_mp:
    por_chave[(mp["fabrica"], mp["produto"])].append(mp["lote_mp"])
for lp in lotes_proc:
    irmaos = [m for m in por_chave[(lp["fabrica"], lp["produto"])] if m != lp["origem"][0][0]
              and abs((MP[m]["entrada"] - MP[lp["origem"][0][0]]["entrada"]).days) < 30]
    if irmaos and rnd.random() < 0.15:
        a = round(rnd.uniform(0.3, 0.7), 2)
        lp["origem"] = [(lp["origem"][0][0], a), (rnd.choice(irmaos), round(1 - a, 2))]

lotes_proc.sort(key=lambda r: (r["data"], r["fabrica"]))
misturas = []
for i, lp in enumerate(lotes_proc, 1):
    lp["lote"] = f"LP-{i:04d}"
    if len(lp["origem"]) > 1:
        lp["mistura"] = f"MX-{len(misturas) + 1:03d}"
        misturas.append(dict(mistura=lp["mistura"], fabrica=lp["fabrica"],
                             partes=[dict(lote_mp=m, pct=p) for m, p in lp["origem"]]))
    else:
        lp["mistura"] = None

# status de cada lote processado e data em que vai para o envase
for lp in lotes_proc:
    idade = (CORTE - lp["data"]).days
    r = rnd.random()
    lp["envase_em"] = None
    if r < 0.06:
        lp["status"], lp["data_status"] = "Descarte", lp["data"] + timedelta(days=rnd.randint(2, 8))
    elif r < 0.085:
        lp["status"], lp["data_status"] = rnd.choice(["Retido", "Retrabalho"]), lp["data"] + timedelta(days=rnd.randint(2, 6))
    else:
        inspecao = rnd.randint(2, 6)
        envase = lp["data"] + timedelta(days=inspecao + int(rnd.expovariate(1 / 9)))
        if idade < inspecao:
            lp["status"], lp["data_status"] = "Em inspeção", lp["data"]
        elif envase <= CORTE:
            lp["status"], lp["data_status"], lp["envase_em"] = "Envasado", envase, envase
        else:
            lp["status"], lp["data_status"] = "Aprovado – não envasado", lp["data"] + timedelta(days=inspecao)
    if lp["data_status"] > CORTE:
        lp["data_status"] = CORTE

# anomalias de status
for lp in rnd.sample(lotes_proc[:-40], 3):                # sem status
    lp["status"], lp["envase_em"] = None, None
envasados = [lp for lp in lotes_proc if lp["status"] == "Envasado"]
sem_envase = set(lp["lote"] for lp in rnd.sample(envasados, max(1, len(envasados) // 100)))
aprovados = [lp for lp in lotes_proc if lp["status"] == "Aprovado – não envasado"]
com_envase_indevido = set(lp["lote"] for lp in rnd.sample(aprovados, max(1, len(aprovados) // 25)))

# ============================== LOTES FINAIS ==============================

lotes_finais = []
for lp in lotes_proc:
    if lp["lote"] in sem_envase:
        continue
    if lp["status"] == "Envasado":
        d0 = lp["envase_em"]
    elif lp["lote"] in com_envase_indevido:
        d0 = min(CORTE, lp["data_status"] + timedelta(days=rnd.randint(1, 4)))
    else:
        continue
    prod = P[lp["produto"]]
    rend = rnd.gauss(0.997, 0.007)
    if rnd.random() < P_REND_FORA:
        rend = 1 + rnd.choice([-1, 1]) * rnd.uniform(0.07, 0.18)
    un_total = lp["un"] * rend
    partes = rnd.choices([1, 2, 3], weights=[50, 35, 15])[0]
    fatias = [rnd.uniform(0.6, 1.4) for _ in range(partes)]
    for k, fa in enumerate(fatias):
        un = un_total * fa / sum(fatias)
        industrial = rnd.random() < prod["pref_industrial"] and un >= UN_POR_PACK_IND * 3
        packs = None
        if industrial:                                     # o último pack pode sair parcial
            packs = max(1, math.ceil(un / UN_POR_PACK_IND))
        peso_real = prod["peso_un"] * rnd.gauss(1, 0.008)
        peso_cont = peso_real
        peso_inf = peso_cont * (1 + rnd.gauss(0, 0.004))
        if rnd.random() < P_PESO_FORA:
            peso_inf = peso_cont * (1 + rnd.choice([-1, 1]) * rnd.uniform(0.02, 0.05))
        # embalagens consumidas
        if industrial:
            emb_proj = packs
            emb_cons = packs + rnd.choices([0, 1, -1, 2, 3], weights=[85, 6, 4, 3, 2])[0]
            emb_nome = rnd.choices(["Industrial padrão", "Industrial grande"], weights=[80, 20])[0]
        else:
            emb_proj = round(un)
            desvio = rnd.gauss(0.012, 0.009)
            if rnd.random() < P_EMB_FORA:
                desvio = rnd.uniform(0.05, 0.12)
            emb_cons = round(un * (1 + desvio))
            emb_nome = {"A": "Varejo P", "B": "Varejo P", "C": "Varejo M", "D": "Varejo M",
                        "E": "Varejo G", "F": "Varejo GG"}[lp["categoria"]]
        if rnd.random() < P_EMB_SEM_LANC:
            emb_cons = None
        di = d0 + timedelta(days=k * rnd.randint(0, 2))
        if di > CORTE:
            di = CORTE
        df = min(CORTE, di + timedelta(days=rnd.randint(0, 2)))
        dr = df + timedelta(days=rnd.randint(1, 4))
        if dr > CORTE or rnd.random() < P_SEM_REPORTE:
            dr = None
        lotes_finais.append(dict(
            lote_final=None, lote_proc=lp["lote"], fabrica=lp["fabrica"], produto=lp["produto"],
            categoria=lp["categoria"], tipo="Industrial" if industrial else "Varejo",
            un=arred(un), packs=packs, kg=arred(un * peso_real),
            embalagem=emb_nome, emb_consumidas=emb_cons, emb_projetadas=emb_proj,
            data_inicial=di, data_final=df, data_reporte=dr,
            qualidade="Pendente" if rnd.random() < P_QUALIDADE_PEND else "Aprovado",
            peso_un_informado=round(peso_inf, 2), peso_un_contagem=round(peso_cont, 2),
        ))

# anomalias: lotes finais sem lote processado de origem e sem data inicial
for lf in rnd.sample(lotes_finais, 4):
    lf["lote_proc"] = f"LP-9{rnd.randint(100, 999)}"
for lf in rnd.sample(lotes_finais, 2):
    lf["data_inicial"] = None

lotes_finais.sort(key=lambda r: (r["data_inicial"] or r["data_final"], r["lote_proc"]))
for i, lf in enumerate(lotes_finais, 1):
    lf["lote_final"] = f"LF-{i:05d}"

# status da embalagem (mesma regra do painel)
for lf in lotes_finais:
    if lf["emb_consumidas"] is None:
        lf["status_emb"] = "Sem lançamento"
        lf["desvio_emb"] = None
        continue
    dif = lf["emb_consumidas"] - lf["emb_projetadas"]
    lf["desvio_emb"] = round(dif / lf["emb_projetadas"], 4) if lf["emb_projetadas"] else None
    if lf["tipo"] == "Industrial":
        lf["status_emb"] = "Ok" if abs(dif) <= TOL_EMB_INDUSTRIAL else "Fora"
    else:
        lf["status_emb"] = "Ok" if abs(lf["desvio_emb"]) <= TOL_EMB_VAREJO else "Fora"

# ========================== VISÃO POR LOTE DE MP ==========================

LP = {lp["lote"]: lp for lp in lotes_proc}
proc_mp = defaultdict(float); desc_mp = defaultdict(float); env_mp = defaultdict(float)
pendente_mp = defaultdict(bool)
for lp in lotes_proc:
    for m, p in lp["origem"]:
        proc_mp[m] += lp["un"] * p
        if lp["status"] == "Descarte":
            desc_mp[m] += lp["un"] * p
        if lp["status"] in ("Aprovado – não envasado", "Em inspeção", "Retido", "Retrabalho", None):
            pendente_mp[m] = True
for lf in lotes_finais:
    lp = LP.get(lf["lote_proc"])
    if lp:
        for m, p in lp["origem"]:
            env_mp[m] += lf["un"] * p

for mp in lotes_mp:
    m = mp["lote_mp"]
    proc, env, desc = proc_mp[m], env_mp[m], desc_mp[m]
    proc_fim = mp["fim_previsto_proc"] <= CORTE - timedelta(days=3) and proc > 0
    env_fim = proc_fim and not pendente_mp[m]
    mp["sit_proc"] = "Finalizado" if proc_fim else ("Em andamento" if proc > 0 else "Não iniciado")
    mp["sit_env"] = "Finalizado" if env_fim else ("Em andamento" if env > 0 else "Não iniciado")
    mp["fase"] = ("Finalizado" if env_fim else "Em envase" if env > 0
                  else "Em processamento" if proc > 0 else "Não iniciado")
    mp["processado"], mp["envasado"], mp["descarte"] = arred(proc), arred(env), arred(desc)
    mp["saldo"] = 0 if env_fim else arred(proc - desc - env)
    mp["dif_final"] = arred(env - (proc - desc)) if env_fim else None

# ================================ ALERTAS ================================

alertas = []

def alerta(nivel, tipo, fabrica, produto, lote, detalhe, data):
    alertas.append(dict(nivel=nivel, tipo=tipo, fabrica=fabrica, produto=produto,
                        lote=lote, detalhe=detalhe, data=iso(data)))

fmt = lambda v: f"{v:,.0f}".replace(",", ".")              # 12.345
pct = lambda v: f"{v * 100:.1f}%".replace(".", ",")         # 107,7%
lotes_com_envase = set(lf["lote_proc"] for lf in lotes_finais)
kg_env = defaultdict(float)
for lf in lotes_finais:
    kg_env[lf["lote_proc"]] += lf["kg"]

for lp in lotes_proc:
    if lp["status"] == "Envasado" and lp["lote"] not in lotes_com_envase:
        alerta("Crítico", "Status × envase", lp["fabrica"], lp["produto"], lp["lote"],
               "Lote marcado como Envasado, mas não há envase com este lote", lp["data_status"])
    if lp["status"] == "Aprovado – não envasado" and lp["lote"] in lotes_com_envase:
        alerta("Atenção", "Status × envase", lp["fabrica"], lp["produto"], lp["lote"],
               "Lote marcado como Aprovado – não envasado, mas já existe envase", lp["data_status"])
    if lp["status"] is None:
        alerta("Atenção", "Cadastro", lp["fabrica"], lp["produto"], lp["lote"], "Lote processado sem status", lp["data"])
    if lp["lote"] in kg_env and lp["kg"]:
        rend = kg_env[lp["lote"]] / lp["kg"]
        if abs(rend - 1) > TOL_REND:
            alerta("Crítico" if abs(rend - 1) > TOL_REND_CRIT else "Atenção", "Rendimento", lp["fabrica"],
                   lp["produto"], lp["lote"],
                   f"Envasado {fmt(kg_env[lp['lote']])} kg de {fmt(lp['kg'])} kg processados ({pct(rend)})",
                   lp["data_status"])

for lf in lotes_finais:
    ref = lf["data_inicial"] or lf["data_final"]
    if lf["lote_proc"] not in LP:
        alerta("Info", "Sem lote de origem", lf["fabrica"], lf["produto"], lf["lote_final"],
               f"Lote processado {lf['lote_proc']} não existe no cadastro", ref)
    if lf["qualidade"] != "Aprovado":
        alerta("Atenção", "Qualidade", lf["fabrica"], lf["produto"], lf["lote_final"],
               f"Status de qualidade: {lf['qualidade']}", ref)
    if lf["data_reporte"] is None and lf["data_final"] and lf["data_final"] <= CORTE - timedelta(days=4):
        alerta("Atenção", "Sem data de reporte", lf["fabrica"], lf["produto"], lf["lote_final"],
               "Envase sem data de reporte preenchida", ref)
    if lf["data_inicial"] is None:
        alerta("Atenção", "Sem data inicial", lf["fabrica"], lf["produto"], lf["lote_final"],
               "Envase sem data inicial: aparece como (em branco) nos gráficos por semana", lf["data_final"])
    if abs(lf["peso_un_informado"] - lf["peso_un_contagem"]) / lf["peso_un_contagem"] > TOL_PESO:
        alerta("Atenção", "Peso por unidade", lf["fabrica"], lf["produto"], lf["lote_final"],
               f"Peso informado difere {abs(lf['peso_un_informado'] - lf['peso_un_contagem']):.2f} kg do peso pela contagem ({lf['peso_un_contagem']:.2f} kg)".replace(".", ","),
               ref)
    if lf["status_emb"] == "Sem lançamento":
        alerta("Atenção", "Embalagem", lf["fabrica"], lf["produto"], lf["lote_final"],
               "Envase sem embalagens consumidas lançadas", ref)

fora = defaultdict(int)
for lf in lotes_finais:
    if lf["status_emb"] == "Fora":
        fora[(lf["fabrica"], lf["tipo"])] += 1
for (fab, tipo), n in sorted(fora.items()):
    txt = (f"Industrial com embalagens fora de ±{TOL_EMB_INDUSTRIAL} do número de packs em {n} lotes"
           if tipo == "Industrial" else
           f"Varejo fora de ±{TOL_EMB_VAREJO:.0%} de embalagens por unidade em {n} lotes")
    alerta("Atenção", "Embalagem", fab, None, tipo, txt + " (lista na aba Envase)", None)

for mp in lotes_mp:
    if mp.get("sem_previsao") and mp["processado"] > 0:
        alerta("Atenção", "Previsão", mp["fabrica"], mp["produto"], mp["lote_mp"],
               "Lote de matéria-prima com processamento, mas sem previsão de entrada", mp["entrada"])
    elif mp["processado"] == 0:
        alerta("Info", "Previsão", mp["fabrica"], mp["produto"], mp["lote_mp"],
               f"Previsto ({fmt(mp['previsao'])} un), ainda sem processamento", mp["entrada"])
    if mp["envasado"] > mp["processado"] - mp["descarte"] + 0.5 and mp["processado"] > 0:
        alerta("Atenção", "Envasado > processado", mp["fabrica"], mp["produto"], mp["lote_mp"],
               f"Lote com {fmt(mp['envasado'])} un envasadas para {fmt(mp['processado'] - mp['descarte'])} un aprovadas", mp["entrada"])

ordem = {"Crítico": 0, "Atenção": 1, "Info": 2}
alertas.sort(key=lambda a: (ordem[a["nivel"]], a["data"] or "9999"))

# ============================ PLANEJAMENTO ============================

LOTES_POR_ETAPA = 3                  # uma etapa junta até 3 lotes do mesmo produto
INTERVALO_MAX_ETAPA = 20             # dias entre entradas para caber na mesma etapa
ITENS_EMB = ["Industrial padrão", "Industrial grande", "Varejo P", "Varejo M", "Varejo G", "Varejo GG"]
VAREJO_POR_CAT = {"A": "Varejo P", "B": "Varejo P", "C": "Varejo M", "D": "Varejo M", "E": "Varejo G", "F": "Varejo GG"}
INSUMOS = [
    # item, unidade, regra, dose, base ("kg" = kg de produção, "mil_un" = por mil un, "pack", "un_varejo", "un")
    ("Insumo A", "L", "ml/kg × peso de produção", 1.2, "kg"),
    ("Insumo B", "L", "ml/kg × peso de produção", 2.5, "kg"),
    ("Insumo C", "L", "ml/kg × peso de produção", 0.06, "kg"),
    ("Insumo D", "L", "ml/mil un × unidades equivalentes", 55, "mil_un"),
    ("Insumo E", "L", "ml/mil un × unidades equivalentes", 30, "mil_un"),
    ("Lacre industrial", "UN", "2 por pack industrial", 2, "pack"),
    ("Etiqueta de produto", "UN", "1 por unidade de varejo", 1, "un_varejo"),
    ("Palete", "UN", "por unidade equivalente", 0.02, "un"),
    ("Filme stretch", "KG", "por unidade equivalente", 0.015, "un"),
    ("Caixa de amostra", "UN", "por unidade equivalente", 0.006, "un"),
]

def situacao(saldo, nec):
    if not nec:
        return "SEM NECESSIDADE"
    return "OK" if saldo >= 0 else "FALTA"

planejamento = {}
for fab in FABRICAS:
    mps = [m for m in lotes_mp if m["fabrica"] == fab]
    # etapas: lotes do mesmo produto, em ordem de entrada e próximos no tempo
    grupos = []
    for prod in sorted(set(m["produto"] for m in mps)):
        atual = []
        for m in [m for m in mps if m["produto"] == prod]:
            if atual and (len(atual) == LOTES_POR_ETAPA
                          or (m["entrada"] - atual[0]["entrada"]).days > INTERVALO_MAX_ETAPA):
                grupos.append(atual)
                atual = []
            atual.append(m)
        if atual:
            grupos.append(atual)
    grupos.sort(key=lambda g: g[0]["entrada"])

    # demanda por produto (unidades), definida contra o potencial total
    pot_prod = defaultdict(float)
    for m in mps:
        pot_prod[m["produto"]] += m["previsao"] * 0.95
    demanda = {}
    for prod, pot in pot_prod.items():
        tot = pot * rnd.uniform(0.85, 1.15)
        ind = tot * P[prod]["pref_industrial"]
        demanda[prod] = {"Industrial": round(ind / UN_POR_PACK_IND) if ind else None,  # em packs
                         "Varejo": round(tot - ind)}
    # estoque por fábrica: entre 0,8× e 2,5× o que uma etapa típica consome,
    # para as etapas maiores acusarem falta de vez em quando
    pots = sorted(sum(m["previsao"] for m in g) * 0.95 for g in grupos)
    pot_tipico = pots[len(pots) // 2]
    fator = lambda: rnd.uniform(0.8, 2.5)
    estoque_emb = {it: round(pot_tipico * fator() * (0.25 / UN_POR_PACK_IND if it.startswith("Industrial") else 0.3))
                   for it in ITENS_EMB}
    estoque_ins = {}
    for nome, um, regra, dose, base in INSUMOS:
        ref = {"kg": pot_tipico * 20 * 0.94 * dose / 1000, "mil_un": pot_tipico / 1000 * dose / 1000,
               "pack": pot_tipico * 0.25 / UN_POR_PACK_IND * dose, "un_varejo": pot_tipico * 0.75 * dose,
               "un": pot_tipico * dose}[base]
        estoque_ins[nome] = round(ref * fator(), 1 if um in ("L", "KG") else 0)

    aberta = {prod: dict(d) for prod, d in demanda.items()}
    etapas = []
    for n, g in enumerate(grupos, 1):
        prod = g[0]["produto"]
        pp = P[prod]
        pot_un = sum((m["previsao"] or 0) * 0.95 for m in g)
        volume = sum((m["previsao"] or 0) * pp["peso_un"] for m in g)
        peso_prod = volume * 0.94
        # regra: industrial primeiro, até completar a demanda aberta; o restante vai para varejo
        dem = []
        ab_ind, ab_var = aberta[prod]["Industrial"], aberta[prod]["Varejo"]
        packs = min(ab_ind or 0, math.floor(pot_un / UN_POR_PACK_IND)) if ab_ind else 0
        un_var = pot_un - packs * UN_POR_PACK_IND
        for destino, total_d, ab, producao in (("Varejo", demanda[prod]["Varejo"], ab_var, un_var),
                                                ("Industrial", demanda[prod]["Industrial"], ab_ind, packs)):
            if not total_d:
                dem.append(dict(destino=destino, total=None, antes=None, aberta=None, producao=arred(producao) or None,
                                falta=None, excedente=arred(producao) or None, situacao="SEM DEMANDA"))
                continue
            falta = max(0, ab - producao); exc = max(0, producao - ab)
            dem.append(dict(destino=destino, total=total_d, antes=total_d - ab, aberta=ab, producao=arred(producao),
                            falta=arred(falta), excedente=arred(exc), situacao="FALTA" if falta > 0 else "OK"))
        aberta[prod]["Varejo"] = max(0, ab_var - un_var)
        if ab_ind:
            aberta[prod]["Industrial"] = max(0, ab_ind - packs)

        # distribuição por embalagem
        dist = []
        pk_g = round(packs * rnd.uniform(0.1, 0.3))
        for item, q in (("Industrial padrão", packs - pk_g), ("Industrial grande", pk_g)):
            dist.append(dict(item=item, unidade="Packs", qtd=q, part=round(q / packs, 3) if packs else 0,
                             peso=arred(q * UN_POR_PACK_IND * pp["peso_un"])))
        cats = defaultdict(float)
        for c, w in zip(CATEGORIAS, pp["cat_pesos"]):
            cats[VAREJO_POR_CAT[c]] += w
        tw = sum(cats.values())
        for item in ITENS_EMB[2:]:
            q = round(un_var * cats[item] / tw)
            dist.append(dict(item=item, unidade="Unidades", qtd=q, part=round(cats[item] / tw, 3),
                             peso=arred(q * pp["peso_un"])))
        if not packs:
            dist = [d for d in dist if d["unidade"] == "Unidades"]

        emb = []
        for d in dist:
            nec = round(d["qtd"] * (1 + MARGEM_SEGURANCA))
            est = estoque_emb[d["item"]]
            emb.append(dict(item=d["item"], potencial=d["qtd"], estoque=est, necessidade=nec,
                            saldo=est - nec, situacao=situacao(est - nec, nec)))

        ins = []
        for nome, um, regra, dose, base in INSUMOS:
            qtd = {"kg": peso_prod * dose / 1000, "mil_un": pot_un / 1000 * dose / 1000, "pack": packs * dose,
                   "un_varejo": un_var * dose, "un": pot_un * dose}[base]
            nec = round(qtd * (1 + MARGEM_SEGURANCA), 1 if um in ("L", "KG") else 0)
            est = estoque_ins[nome]
            ins.append(dict(item=nome, um=um, regra=regra, dose=dose, necessidade=nec, estoque=est,
                            saldo=round(est - nec, 1), situacao=situacao(est - nec, nec)))

        fora_spec = []
        for m in g:
            if rnd.random() < 0.35:
                for c in rnd.sample(CATEGORIAS[2:], rnd.randint(1, 3)):
                    lim = 12.0
                    med = round(lim - rnd.uniform(0.1, 4), 2)
                    fora_spec.append(dict(lote=m["lote_mp"], categoria=c, medida=med, faixa="12 a 24",
                                          motivo=f"Abaixo {lim - med:.2f}".replace(".", ","),
                                          un=rnd.randint(20, 900), embalagem=VAREJO_POR_CAT[c]))

        lotes = []
        for k, m in enumerate(g, 1):
            pot = round((m["previsao"] or 0) * 0.95)
            pk = round(packs * pot / pot_un) if pot_un else 0
            lotes.append(dict(lote=m["lote_mp"], produto=prod, seq=k, status=m["fase"],
                              peso=arred((m["previsao"] or 0) * pp["peso_un"]), potencial=pot, packs=pk,
                              un=max(0, pot - pk * UN_POR_PACK_IND), situacao="OK"))
        alerta_et = None
        if rnd.random() < 0.15 and len(lotes) > 1:
            lotes[-1]["situacao"] = "PREVISÃO DUPLICADA"
            alerta_et = "Confira as situações dos lotes da etapa."

        fases = [m["fase"] for m in g]
        st = ("Finalizado" if all(f == "Finalizado" for f in fases)
              else "Não iniciado" if all(f == "Não iniciado" for f in fases) else "Em andamento")
        etapas.append(dict(etapa=f"{n}ª", status=st, produtos=prod, n_lotes=len(g), volume=arred(volume),
                           peso_producao=arred(peso_prod), un_eq=arred(pot_un), un_varejo=arred(un_var),
                           packs=packs, alerta=alerta_et, demanda=dem, distribuicao=dist, embalagens=emb,
                           insumos=ins, fora_spec=fora_spec, lotes=lotes))
    planejamento[fab] = etapas

# ======================= AUTOMAÇÕES (logs simulados) =======================

ETAPAS_ERP = ["1 · Peso por unidade", "2 · Dados de embalagem", "3 · Características do lote", "4 · Vínculo de origem"]
JANELA_LOGS = CORTE - timedelta(weeks=7)
execucoes = []
candidatos = sorted([lf for lf in lotes_finais if lf["data_reporte"] and lf["data_reporte"] >= JANELA_LOGS
                     and lf["lote_proc"] in LP], key=lambda r: r["data_reporte"])
# uma rodada por semana (às vezes duas): processa o que foi reportado desde a anterior
datas = []
d = JANELA_LOGS
while d <= CORTE:
    datas.append(d + timedelta(days=rnd.choice([0, 1, 2])))
    if rnd.random() < 0.35:
        datas.append(d + timedelta(days=rnd.choice([3, 4])))
    d += timedelta(days=7)
datas = sorted(set(x for x in datas if x <= CORTE))
seq_erp = 8_100_000
ja_processado = set()
for i, dia in enumerate(datas):
    lote_rodada = [lf for lf in candidatos if lf["data_reporte"] <= dia and lf["lote_final"] not in ja_processado]
    if not lote_rodada:
        continue
    for lf in lote_rodada:
        ja_processado.add(lf["lote_final"])
    hora = timedelta(hours=rnd.randint(7, 15), minutes=rnd.randint(0, 59))
    for e_idx, etapa in enumerate(ETAPAS_ERP):
        linhas, ok, bloq, erro = [], 0, 0, 0
        t = hora + timedelta(minutes=6 * e_idx)
        hh = lambda tt: f"{int(tt.total_seconds()) // 3600:02d}:{int(tt.total_seconds()) % 3600 // 60:02d}:{int(tt.total_seconds()) % 60:02d}"
        linhas.append(f"[{hh(t)}] [OK]   Conexão com o ERP estabelecida.")
        linhas.append(f"[{hh(t)}] [OK]   Planilha de controle conectada. {len(lote_rodada)} lotes a processar.")
        for lf in lote_rodada:
            t += timedelta(seconds=rnd.randint(3, 6))
            validade = (lf["data_final"] + timedelta(days=365)).strftime("%m/%Y")
            if e_idx == 1 and rnd.random() < 0.025:
                linhas.append(f"[{hh(t)}] [BLOQ] {lf['lote_final']} | Campo já preenchido no ERP: lote ignorado para não sobrescrever.")
                bloq += 1
                continue
            if rnd.random() < 0.004:
                linhas.append(f"[{hh(t)}] [ERRO] {lf['lote_final']} | ERP não respondeu; lote mantido na fila para a próxima rodada.")
                erro += 1
                continue
            detalhe = {
                0: f"Peso líquido = {lf['peso_un_informado']:.2f} kg".replace(".", ","),
                1: f"Embalagem = {lf['embalagem']} | Quantidade = {lf['packs'] or lf['un']}",
                2: f"Produto = {lf['produto']} | Categoria = {lf['categoria']} | Validade = {validade}",
                3: f"Lote de origem = {lf['lote_proc']}",
            }[e_idx]
            linhas.append(f"[{hh(t)}] [OK]   {lf['lote_final']} | {detalhe}")
            ok += 1
        linhas.append(f"[{hh(t)}] [INFO] Fim: {ok} ok, {bloq} bloqueados, {erro} com erro.")
        execucoes.append(dict(data=iso(dia), hora=hh(hora + timedelta(minutes=6 * e_idx)), modulo="Atualização de lotes",
                              etapa=etapa, lotes=len(lote_rodada), ok=ok, bloqueados=bloq, erros=erro, log=linhas))

# módulo de criação de lotes de inspeção (um por lote processado recente)
insp = [lp for lp in lotes_proc if lp["data"] >= JANELA_LOGS]
seq_insp = 11_000_000
for dia in datas:
    rodada = [lp for lp in insp if dia - timedelta(days=7) < lp["data"] <= dia]
    if not rodada:
        continue
    linhas = ["[08:00:00] [OK]   Conexão com o ERP estabelecida."]
    for k, lp in enumerate(rodada):
        seq_insp += 1
        linhas.append(f"[08:{k // 12:02d}:{(k * 5) % 60:02d}] [OK]   {lp['lote']} | Lote de inspeção gerado -> {seq_insp}")
    linhas.append(f"[08:{len(rodada) // 12:02d}:59] [INFO] Fim: {len(rodada)} ok, 0 bloqueados, 0 com erro.")
    execucoes.append(dict(data=iso(dia), hora="08:00:00", modulo="Lotes de inspeção", etapa="Criação de lote de inspeção",
                          lotes=len(rodada), ok=len(rodada), bloqueados=0, erros=0, log=linhas))
execucoes.sort(key=lambda e: (e["data"], e["hora"]))

# ================================ SAÍDA ================================

meta = dict(empresa="DemoFoods", aviso="Dados fictícios, gerados para demonstração.",
            gerado_em=iso(CORTE), inicio=iso(INICIO), fim=iso(CORTE), aleatorio_fixo=ALEATORIO_FIXO,
            regras=dict(tol_emb_varejo=TOL_EMB_VAREJO, tol_emb_industrial=TOL_EMB_INDUSTRIAL,
                        tol_rendimento=TOL_REND, tol_rendimento_critico=TOL_REND_CRIT, tol_peso=TOL_PESO,
                        un_por_pack_industrial=UN_POR_PACK_IND))

monitoramento = dict(
    meta=meta,
    fabricas=list(FABRICAS),
    produtos=[dict(produto=p["produto"], peso_un=p["peso_un"]) for p in produtos],
    lotes_processados=[dict(lote=lp["lote"], fabrica=lp["fabrica"], produto=lp["produto"], categoria=lp["categoria"],
                            mistura=lp["mistura"], lotes_mp=[m for m, _ in lp["origem"]], un=lp["un"], kg=lp["kg"],
                            data=iso(lp["data"]), status=lp["status"], data_status=iso(lp["data_status"]))
                       for lp in lotes_proc],
    lotes_finais=[dict(lote_final=lf["lote_final"], lote_proc=lf["lote_proc"], fabrica=lf["fabrica"],
                       produto=lf["produto"], categoria=lf["categoria"], tipo=lf["tipo"], un=lf["un"],
                       packs=lf["packs"], kg=lf["kg"], embalagem=lf["embalagem"],
                       emb_consumidas=lf["emb_consumidas"], emb_projetadas=lf["emb_projetadas"],
                       status_emb=lf["status_emb"], desvio_emb=lf["desvio_emb"],
                       data_inicial=iso(lf["data_inicial"]), data_final=iso(lf["data_final"]),
                       data_reporte=iso(lf["data_reporte"]), qualidade=lf["qualidade"],
                       peso_un_informado=lf["peso_un_informado"], peso_un_contagem=lf["peso_un_contagem"])
                  for lf in lotes_finais],
    misturas=misturas,
    lotes_mp=[dict(lote_mp=m["lote_mp"], fornecedor=m["fornecedor"], fabrica=m["fabrica"], produto=m["produto"],
                   entrada=iso(m["entrada"]), previsao=None if m.get("sem_previsao") else m["previsao"],
                   processado=m["processado"], envasado=m["envasado"], descarte=m["descarte"],
                   sit_processamento=m["sit_proc"], sit_envase=m["sit_env"], fase=m["fase"],
                   saldo=m["saldo"], dif_final=m["dif_final"]) for m in lotes_mp],
    alertas=alertas,
)

os.makedirs(SAIDA, exist_ok=True)
for nome, obj in (("monitoramento.json", monitoramento),
                  ("planejamento.json", dict(meta=meta, fabricas=planejamento)),
                  ("automacoes.json", dict(meta=meta, etapas=ETAPAS_ERP, execucoes=execucoes))):
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{nome}: {os.path.getsize(os.path.join(SAIDA, nome)) / 1024:.0f} KB")
