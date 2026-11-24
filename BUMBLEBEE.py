"""BUMBLEBEE -- foto mensal dos veiculos cujo PROPRIETARIO nao tem certificado.

O Senatran so responde pelo dono do e-CNPJ, entao veiculo de empresa sem
certificado nunca entra no CADSEN pelo caminho normal (TRANSFORMER -> OPTIMUS/
MEGATRON). Este script cobre esses veiculos pela consulta do DETRAN estadual --
hoje so PI -- e grava a MESMA linha que o Senatran gravaria, com a DTA_EXEC da
rodada do dia, mais as infracoes em TB_RENAINF.

Onde entra no ciclo mensal (rodar_producao.ps1):

    TRANSFORMER.py  ->  BUMBLEBEE.py  ->  IRONHIDE.py  ->  ATUALIZA_FIPE.py

Depois do TRANSFORMER porque a linha precisa cair na MESMA DTA_EXEC da foto do
mes; antes do ATUALIZA_FIPE porque ele preenche COD_FIPE/TABELA_FIPE/
MESREFERENCIA de quem esta na foto do dia -- assim a FIPE vem de graca.

As placas daqui NAO podem entrar no IRONHIDE: com o certificado de outra
empresa a consulta e paga e volta vazia. A propria tabela de cadastro serve de
lista de exclusao la (SELECT PLACA FROM tb_veiculo_sem_cert).

O que o DETRAN nao devolve, e por que nao faz falta no PI:
  - IPVA: e da SEFAZ, endpoint separado. Medido no CADSEN, os veiculos de PI
    COM certificado tambem estao com IPVA vazio -- ou seja, nao ha perda aqui.
  - TOTAL_PROCESSOS / PROCESSO / TIPO_RESTRICAO / TRIBUNAL / ORGAO: so o
    Senatran tem. As quatro ultimas ja vem 100% vazias hoje, com certificado.
  - SITUACAO da multa (paga/vencida): fica vazia, e a tela mostra isso como
    "Sem informacao" em vez de inventar "nao paga" (ver regra_multa.py no app).
"""

import argparse
import json
import re
import sys
import time
from datetime import date, datetime

import armazenamento as bd
import requests

from config import obter_credencial

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8")

# =============================================================
# CONFIGURACAO
# =============================================================

TOKEN = obter_credencial("INFOSIMPLES_TOKEN")  # vem de obter_credencial() (config.py)

# Uma UF por vez, de proposito: cada DETRAN tem endpoint e campos proprios (ver
# as funcoes debito_* do DETRAN.py). Acrescentar UF aqui exige tambem conferir
# os nomes dos campos em linha_do_cadsen/totais.
URL_POR_UF = {"PI": "https://api.infosimples.com/api/v2/consultas/detran/pi/veiculo"}

TIMEOUT_API = 300
TENTATIVAS = 3
PAUSA_ENTRE_TENTATIVAS = 5

TABELA_CADASTRO = "tb_veiculo_sem_cert"

# Idade maxima, em dias, da ultima DTA_EXEC que ainda conta como "a foto de
# agora". Cobre a rodada que atravessa a meia-noite: gravar num dia diferente
# racharia a foto do mes em duas datas, e a tela (janela de 7 dias) mostraria
# esses veiculos separados do resto.
DIAS_FOTO_ABERTA = 2

# Na produção: BANCO = dict(host=..., database="bd_senatran", ...) -- MySQL.
# Nesta versão pública as tabelas são arquivos Parquet em dados/ (ver armazenamento.py).

COLUNAS_CADSEN = [
    "CNPJ_EMP", "UF", "CNPJ_PROP", "PLACA", "TIPO", "MODELO", "ANO_FAB", "ANO",
    "CARROCERIA", "CHASSI", "RENAVAM", "GRAVAME", "GRAVAME_PENDENTE",
    "RESTRICAO_ADM", "RENAJUD", "PROCESSO", "TIPO_RESTRICAO", "TRIBUNAL",
    "ORGAO", "TOTAL_PROCESSOS", "COD_FIPE", "INFO_UF_FIPE", "DEBITO_DETRAN",
    "LICENCIAMENTO", "MULTA", "IPVA", "IPVA_AL_ANT", "CUSTO_API", "DTA_EXEC",
    "TABELA_FIPE", "COMBUSTIVEL", "MESREFERENCIA",
]

TIPOS_SEM_CARROCERIA = ("MOTOCICLETA", "MOTONETA", "CICLOMOTOR")


# =============================================================
# CADASTRO
# =============================================================

def garantir_tabela():
    # Na produção: CREATE TABLE IF NOT EXISTS tb_veiculo_sem_cert (PLACA VARCHAR(7) PK,
    # RENAVAM VARCHAR(11), UF VARCHAR(2), CNPJ_EMP VARCHAR(18), CNPJ_PROP VARCHAR(14),
    # ATIVO TINYINT DEFAULT 1). Aqui: cria o Parquet vazio com as mesmas colunas.
    bd.garantir(TABELA_CADASTRO)


def veiculos_cadastrados(placa=None):
    cadastro = bd.ler(TABELA_CADASTRO)
    cadastro = cadastro[cadastro["ATIVO"].fillna(0) == 1]
    if placa:
        cadastro = cadastro[cadastro["PLACA"] == placa]
    cadastro = cadastro.sort_values("PLACA")
    return bd.registros(cadastro[["PLACA", "RENAVAM", "UF", "CNPJ_EMP", "CNPJ_PROP"]])


def avisar_empresa_desconhecida(veiculos):
    """CNPJ_EMP fora de tb_empresas deixa a coluna "Empresa" VAZIA na tela (o
    app resolve o nome por LEFT JOIN). Falha silenciosa classica -- avisa."""
    cnpjs = sorted({v["CNPJ_EMP"] for v in veiculos})
    if not cnpjs:
        return
    empresas = bd.ler("tb_empresas")
    conhecidos = set(empresas.loc[empresas["CNPJ_EMP"].isin(cnpjs), "CNPJ_EMP"])
    for cnpj in cnpjs:
        if cnpj not in conhecidos:
            print(f"  AVISO: {cnpj} nao esta em tb_empresas -- a coluna Empresa fica vazia na tela")


# =============================================================
# DATA DA RODADA
# =============================================================

def _dias_desde(dta_exec):
    try:
        return (date.today() - datetime.strptime(str(dta_exec), "%Y%m%d").date()).days
    except (TypeError, ValueError):
        return None


def data_da_rodada(escolhida=None):
    if escolhida:
        return escolhida
    hoje = date.today().strftime("%Y%m%d")
    datas = bd.ler("CADSEN")["DTA_EXEC"].dropna()
    ultima = datas.max() if len(datas) else None
    dias = _dias_desde(ultima)
    if ultima and dias is not None and 0 <= dias <= DIAS_FOTO_ABERTA:
        return str(ultima)
    print(f"  AVISO: a ultima foto do CADSEN e de {ultima} ({dias} dia(s)) -- usando {hoje}. "
          f"O ATUALIZA_FIPE.py so preenche a FIPE de DTA_EXEC = hoje.")
    return hoje


def ja_esta_na_foto(placa, dta_exec):
    cadsen = bd.ler("CADSEN")
    return bool(((cadsen["PLACA"] == placa) & (cadsen["DTA_EXEC"] == dta_exec)).any())


# =============================================================
# CONSULTA AO DETRAN
# =============================================================

def consultar(placa, renavam, uf, json_teste=None):
    """Devolve (dados, preco, erro), onde "dados" e o data[0] da resposta."""
    if json_teste:
        with open(json_teste, encoding="utf-8") as arquivo:
            resposta = json.load(arquivo)
        return (resposta.get("data") or [None])[0], 0.0, None

    url = URL_POR_UF.get((uf or "").upper())
    if not url:
        return None, 0.0, f"UF {uf} ainda nao implementada"

    args = {"placa": placa, "renavam": renavam, "token": TOKEN, "timeout": TIMEOUT_API}
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = requests.post(url, args, timeout=TIMEOUT_API + 30).json()
        except Exception as erro:
            print(f"    tentativa {tentativa}/{TENTATIVAS} falhou na rede: {erro}")
            time.sleep(PAUSA_ENTRE_TENTATIVAS)
            continue

        preco = float((resposta.get("header") or {}).get("price") or 0)
        codigo = resposta.get("code")
        if codigo == 200 and resposta.get("data"):
            return resposta["data"][0], preco, None

        motivo = f"code {codigo}: {resposta.get('code_message')}"
        # 6xx e indisponibilidade do site do DETRAN, que costuma passar sozinha;
        # erro de parametro (placa/renavam errados) nao passa, e repetir gastaria
        # a consulta de novo.
        if isinstance(codigo, int) and codigo >= 600 and tentativa < TENTATIVAS:
            print(f"    tentativa {tentativa}/{TENTATIVAS} -- {motivo}")
            time.sleep(PAUSA_ENTRE_TENTATIVAS)
            continue
        return None, preco, motivo

    return None, 0.0, f"sem resposta apos {TENTATIVAS} tentativas"


# =============================================================
# API -> COLUNAS DO CADSEN
# =============================================================

def _anos(ano_fabricacao):
    """"2012 / 2013" -> ("2012", "2013"). ANO e o ano-MODELO, e e ele que decide
    o preco da FIPE -- trocar os dois muda o valor do veiculo na tela."""
    numeros = re.findall(r"\d{4}", str(ano_fabricacao or ""))
    if not numeros:
        return "", ""
    return numeros[0], (numeros[1] if len(numeros) > 1 else numeros[0])


def _tem(texto, *palavras):
    alvo = str(texto or "").upper()
    return any(palavra in alvo for palavra in palavras)


def _restricoes(veiculo):
    """RENAJUD/RESTRICAO_ADM/GRAVAME a partir do campo "restricao".

    Campo ausente fica VAZIO em vez de "Nao": o DETRAN nao ter respondido nao e
    o mesmo que o veiculo nao ter restricao (a mesma licao da coluna "Paga" das
    multas). GRAVAME_PENDENTE nunca vem -- e ja e 62% vazio hoje, com Senatran.
    """
    texto = veiculo.get("restricao")
    if texto is None or str(texto).strip() == "":
        return "", "", ""
    nao = "Não"
    return ("Sim" if _tem(texto, "JUDICIAL") else nao,
            "Sim" if _tem(texto, "ADMINISTRATIV") else nao,
            "Sim" if _tem(texto, "ALIENA", "FIDUCIAR", "GRAVAME") else nao)


def _valor(numero):
    # Texto com PONTO decimal, como o resto do CADSEN ("1591.82").
    return f"{float(numero or 0):.2f}"


def totais(dados):
    """Licenciamento, multas e o total -- a mesma conta de DETRAN.py::debito_PI,
    refeita sobre o JSON que ja temos em maos (chamar debito_PI aqui pagaria uma
    segunda consulta pela mesma informacao)."""
    licenciamento = 0.0
    for grupo in dados.get("debitos") or []:
        if any(item.get("debito") == "Taxa de Licenciamento" for item in (grupo.get("lista") or [])):
            licenciamento += float(grupo.get("normalizado_total") or 0)
    multas = sum(float(inf.get("normalizado_valor_multa") or inf.get("normalizado_valor_total") or 0)
                 for inf in (dados.get("infracoes") or []))
    return licenciamento, multas, round(licenciamento + multas, 2)


def linha_do_cadsen(cadastro, dados, preco, dta_exec):
    veiculo = dados.get("veiculo") or {}
    ano_fab, ano = _anos(veiculo.get("ano_fabricacao"))
    renajud, rest_adm, gravame = _restricoes(veiculo)
    licenciamento, multas, debito = totais(dados)
    tipo = (veiculo.get("tipo") or "").strip().upper()
    return {
        "CNPJ_EMP": cadastro["CNPJ_EMP"],
        "UF": cadastro["UF"],
        "CNPJ_PROP": cadastro["CNPJ_PROP"] or "",
        "PLACA": cadastro["PLACA"],
        "TIPO": tipo,
        # Formato "MARCA/MODELO", o mesmo do Senatran -- e a chave do casamento
        # com a FIPE (join por MODELO + ANO). Escrever "FAN125" aqui deixaria o
        # veiculo sem valor na tela.
        "MODELO": (veiculo.get("marca_modelo") or "").strip().upper(),
        "ANO_FAB": ano_fab,
        "ANO": ano,
        # O Senatran grava "NAO APLICAVEL" para duas rodas; nos outros tipos o
        # DETRAN nao informa carroceria, e vazio e melhor que chute.
        "CARROCERIA": "NÃO APLICAVEL" if tipo in TIPOS_SEM_CARROCERIA else "",
        "CHASSI": (veiculo.get("chassi") or "").strip().upper(),
        "RENAVAM": str(veiculo.get("renavam") or cadastro["RENAVAM"]).strip().zfill(11),
        "GRAVAME": gravame,
        "GRAVAME_PENDENTE": "",
        "RESTRICAO_ADM": rest_adm,
        "RENAJUD": renajud,
        "PROCESSO": "",
        "TIPO_RESTRICAO": "",
        "TRIBUNAL": "",
        "ORGAO": "",
        "TOTAL_PROCESSOS": 0,
        "COD_FIPE": "",
        "INFO_UF_FIPE": "",
        "DEBITO_DETRAN": _valor(debito),
        "LICENCIAMENTO": _valor(licenciamento),
        "MULTA": _valor(multas),
        # IPVA e IPVA_AL_ANT ficam vazios: o DETRAN do PI nao informa, e o
        # veiculo de PI COM certificado tambem esta assim hoje no CADSEN.
        "IPVA": "",
        "IPVA_AL_ANT": "",
        "CUSTO_API": _valor(preco),
        "DTA_EXEC": dta_exec,
        # As tres da FIPE ficam para o ATUALIZA_FIPE.py, que roda depois.
        "TABELA_FIPE": "",
        "COMBUSTIVEL": (veiculo.get("combustivel") or "").strip().upper()[:8],
        "MESREFERENCIA": "",
    }


# =============================================================
# API -> TB_RENAINF
# =============================================================

def _orgao(orgao_autuador):
    """"(000100)DEPARTAMENTO DE POLICIA RODOVIARIA FEDERAL" ->
    "000100 - DEPARTAMENTO DE POLICIA RODOVIARIA FEDERAL", o formato que o
    IRONHIDE grava. O nome pode nao ser igual ao que o Senatran usa para o mesmo
    codigo -- o codigo, que e o que identifica o orgao, e o mesmo."""
    texto = str(orgao_autuador or "").strip()
    casamento = re.match(r"^\((\d+)\)\s*(.*)$", texto)
    return f"{casamento.group(1)} - {casamento.group(2).strip()}" if casamento else texto


def _infracao(descricao):
    """"(504-5) DIRIGIR COM CNH VENCIDA" -> "504-5 - DIRIGIR COM CNH VENCIDA"."""
    texto = str(descricao or "").strip()
    casamento = re.match(r"^\(([\w-]+)\)\s*(.*)$", texto)
    return f"{casamento.group(1)} - {casamento.group(2).strip()}" if casamento else texto


def linhas_das_infracoes(placa, dados, dta_exec):
    linhas = []
    for inf in dados.get("infracoes") or []:
        data_hora = f"{inf.get('data_infracao') or ''} {inf.get('hora_infracao') or ''}".strip()
        linhas.append({
            "PLACA": placa,
            "ORGAO": _orgao(inf.get("orgao_autuador")),
            "INFRACAO": _infracao(inf.get("descricao")),
            "AUTO_INFRACAO": str(inf.get("auto_infracao") or "").strip(),
            "RENAINF": str(inf.get("renainf") or "").strip(),
            "LOCAL": str(inf.get("local") or "").strip(),
            "DATA_HORA_INF": data_hora,
            "VALOR": _valor(inf.get("normalizado_valor_multa") or inf.get("normalizado_valor_total")),
            "VENCIMENTO": str(inf.get("data_vencimento") or "").strip(),
            # O DETRAN nao diz se a multa esta paga. Vazio faz a tela mostrar
            # "Sem informacao"; "NAO_PAGAS_VENCIDAS" seria inventar.
            "SITUACAO": "",
            "DT_IDENT_CONDUTOR": "",
            "DTA_EXEC": dta_exec,
        })
    return linhas


# =============================================================
# GRAVACAO
# =============================================================

def gravar_cadsen(linha):
    # NOT EXISTS por PLACA + DTA_EXEC: a mesma protecao do MEGATRON, para rodar
    # duas vezes no mesmo dia nao duplicar a linha (na produção: INSERT ... SELECT
    # ... WHERE NOT EXISTS no MySQL).
    return bd.inserir("CADSEN", {c: linha[c] for c in COLUNAS_CADSEN}, chave=["PLACA", "DTA_EXEC"])


def gravar_infracoes(linhas):
    """Dedup por PLACA + AUTO_INFRACAO + DTA_EXEC -- a mesma chave do IRONHIDE
    (uma linha por execucao enquanto a multa segue aberta, que e o que mantem o
    historico)."""
    return bd.inserir("TB_RENAINF", linhas, chave=["PLACA", "AUTO_INFRACAO", "DTA_EXEC"])


# =============================================================
# PRINCIPAL
# =============================================================

def main():
    opcoes = argparse.ArgumentParser(description="Foto dos veiculos sem certificado, via DETRAN.")
    opcoes.add_argument("--simular", action="store_true", help="consulta e mostra, sem gravar")
    opcoes.add_argument("--placa", help="roda so essa placa (teste)")
    opcoes.add_argument("--data", help="DTA_EXEC a usar (AAAAMMDD); o padrao e a foto do dia")
    opcoes.add_argument("--json-teste", dest="json_teste",
                        help="usa um JSON salvo no lugar da API -- so para testar formato, nao consulta nada")
    argumentos = opcoes.parse_args()

    garantir_tabela()

    veiculos = veiculos_cadastrados(argumentos.placa)
    if not veiculos:
        print(f"Nenhum veiculo ativo em {TABELA_CADASTRO}. Cadastre uma linha em "
              f"{bd.caminho(TABELA_CADASTRO)} com as colunas")
        print("  PLACA, RENAVAM, UF, CNPJ_EMP, CNPJ_PROP, ATIVO -- por exemplo (ficticio):")
        print("  ('ABC1D23', '00000000019', 'PI', '22222222000122', '22222222000122', 1)")
        return 0

    dta_exec = data_da_rodada(argumentos.data)
    print(f"BUMBLEBEE -- {len(veiculos)} veiculo(s) | DTA_EXEC {dta_exec}"
          + (" | SIMULACAO (nada sera gravado)" if argumentos.simular else ""))
    avisar_empresa_desconhecida(veiculos)

    gravados = pulados = falhas = 0
    infracoes_gravadas = 0
    custo = 0.0

    for veiculo in veiculos:
        placa = veiculo["PLACA"]
        print(f"\n{placa} ({veiculo['UF']})")

        if not argumentos.simular and ja_esta_na_foto(placa, dta_exec):
            print("  ja esta na foto desta DTA_EXEC -- pulando")
            pulados += 1
            continue

        dados, preco, erro = consultar(placa, veiculo["RENAVAM"], veiculo["UF"], argumentos.json_teste)
        custo += preco
        if erro or not dados:
            print(f"  FALHA: {erro or 'resposta sem dados'}")
            falhas += 1
            continue

        linha = linha_do_cadsen(veiculo, dados, preco, dta_exec)
        infracoes = linhas_das_infracoes(placa, dados, dta_exec)
        print(f"  {linha['MODELO']} | {linha['TIPO']} | {linha['ANO_FAB']}/{linha['ANO']} | "
              f"chassi {linha['CHASSI']}")
        print(f"  licenciamento {linha['LICENCIAMENTO']} | multa {linha['MULTA']} | "
              f"debito {linha['DEBITO_DETRAN']} | renajud {linha['RENAJUD'] or '(sem info)'} | "
              f"{len(infracoes)} infracao(oes) | custo {linha['CUSTO_API']}")

        if argumentos.simular:
            continue

        if gravar_cadsen(linha):
            gravados += 1
        else:
            pulados += 1
        infracoes_gravadas += gravar_infracoes(infracoes)

    print(f"\n=== Fim | gravados: {gravados} | pulados: {pulados} | falhas: {falhas} | "
          f"infracoes novas: {infracoes_gravadas} | custo: R$ {custo:.2f} ===")

    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
