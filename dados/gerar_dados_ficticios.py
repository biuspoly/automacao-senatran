"""Gera as tabelas FICTICIAS em Parquet (dados/<TABELA>.parquet).

Mesmas colunas das tabelas reais do banco bd_senatran, mas com dados
inventados:
  - CNPJs com base de digitos repetidos (11111111..., 22222222...), que nao
    existem na Receita;
  - placas no padrao Mercosul com prefixo TST (de "teste") e a ABC1D23;
  - RENAVAM 0000000001x e chassi "CHASSIFICTICIO0xx";
  - empresas "... EXEMPLO ... LTDA".

Uso:  python dados/gerar_dados_ficticios.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

import armazenamento as bd  # noqa: E402

EMPRESAS = [
    ("11111111000111", "DISTRIBUIDORA EXEMPLO ALFA LTDA", "PE"),
    ("11111111000292", "DISTRIBUIDORA EXEMPLO ALFA LTDA", "MA"),
    ("22222222000122", "DISTRIBUIDORA EXEMPLO BETA LTDA", "PI"),
    ("33333333000133", "LOGISTICA EXEMPLO GAMA LTDA", "RJ"),
    ("44444444000144", "TRANSPORTES EXEMPLO DELTA LTDA", "AL"),
    ("55555555000155", "DISTRIBUIDORA EXEMPLO EPSILON LTDA", "CE"),
    ("66666666000166", "DISTRIBUIDORA EXEMPLO ZETA LTDA", "PB"),
    ("77777777000177", "DISTRIBUIDORA EXEMPLO ETA LTDA", "RN"),
]

# placa, cnpj da empresa, tipo, modelo, ano_fab, ano, carroceria, combustivel, cod_fipe, preco
VEICULOS = [
    ("ABC1D23", "11111111000111", "CAMINHAO", "VW/24.280 CRM 6X2", "2019", "2020", "ABERTA", "DIESEL", "005340-6", "R$ 318.000,00"),
    ("TST1A11", "11111111000111", "UTILITARIO", "FIAT/STRADA ENDURANCE CS", "2022", "2022", "ABERTA", "ALCO/GAS", "001508-3", "R$ 86.500,00"),
    ("TST2B22", "11111111000292", "CAMINHAO", "M.BENZ/ATEGO 1719", "2018", "2018", "FECHADA", "DIESEL", "509154-3", "R$ 265.900,00"),
    ("TST3C33", "33333333000133", "AUTOMOVEL", "CHEVROLET/ONIX 1.0MT LT", "2021", "2022", "NÃO APLICAVEL", "ALCO/GAS", "004461-0", "R$ 71.200,00"),
    ("TST4D44", "44444444000144", "CAMINHAO", "IVECO/TECTOR 240E28", "2020", "2021", "ABERTA", "DIESEL", "511058-0", "R$ 289.400,00"),
    ("TST5E55", "55555555000155", "MOTOCICLETA", "HONDA/CG 160 FAN", "2023", "2023", "NÃO APLICAVEL", "ALCO/GAS", "811148-0", "R$ 15.900,00"),
    ("TST6F66", "66666666000166", "CAMINHAO", "VW/11.180 DRC 4X2", "2017", "2017", "FECHADA", "DIESEL", "509068-7", "R$ 179.300,00"),
    ("TST7G77", "77777777000177", "UTILITARIO", "FIAT/FIORINO ENDURANCE", "2023", "2024", "FECHADA", "ALCO/GAS", "001516-4", "R$ 98.700,00"),
]

# Veiculo de proprietario SEM certificado, coberto pelo BUMBLEBEE (DETRAN-PI)
SEM_CERT = [("TST8H88", "00000000098", "PI", "22222222000122", "22222222000122", 1)]

EXECUCOES = ["20261005", "20261104"]


def renavam(i):
    return f"{i + 10:011d}"


def chassi(i):
    return f"CHASSIFICTICIO{i + 1:03d}"


def gerar():
    bd.gravar("TB_EMPRESAS", pd.DataFrame(
        [{"CNPJ_EMP": c, "EMPRESA": n} for c, n, _ in EMPRESAS]))
    uf_de = {c: uf for c, _, uf in EMPRESAS}

    cadsen = []
    for dta in EXECUCOES:
        for i, (placa, cnpj, tipo, modelo, ano_fab, ano, carroc, comb, fipe, preco) in enumerate(VEICULOS):
            multa = "195.23" if placa in ("ABC1D23", "TST3C33") else "0.0"
            lic = "160.22" if i % 3 == 0 else "0.0"
            debito = f"{float(multa) + float(lic):.2f}"
            cadsen.append({
                "CNPJ_EMP": cnpj, "UF": uf_de[cnpj], "CNPJ_PROP": cnpj, "PLACA": placa,
                "TIPO": tipo, "MODELO": modelo, "ANO_FAB": ano_fab, "ANO": ano,
                "CARROCERIA": carroc, "CHASSI": chassi(i), "RENAVAM": renavam(i),
                "GRAVAME": "Sim" if i % 4 == 0 else "Não", "GRAVAME_PENDENTE": "Não" if uf_de[cnpj] == "PE" else "",
                "RESTRICAO_ADM": "Não", "RENAJUD": "Sim" if placa == "TST2B22" else "Não",
                "PROCESSO": "", "TIPO_RESTRICAO": "", "TRIBUNAL": "", "ORGAO": "",
                "TOTAL_PROCESSOS": 1 if placa == "TST2B22" else 0,
                "COD_FIPE": fipe, "INFO_UF_FIPE": "",
                "DEBITO_DETRAN": debito, "LICENCIAMENTO": lic, "MULTA": multa,
                "IPVA": "0.0", "IPVA_AL_ANT": "0" if uf_de[cnpj] == "AL" else "",
                "CUSTO_API": "0.24", "DTA_EXEC": dta,
                "TABELA_FIPE": preco, "COMBUSTIVEL": comb,
                "MESREFERENCIA": "outubro de 2026" if dta == "20261005" else "novembro de 2026",
            })
    bd.gravar("CADSEN", pd.DataFrame(cadsen))

    renainf = []
    for dta in EXECUCOES:
        renainf.append({
            "PLACA": "ABC1D23", "ORGAO": "000100",
            "INFRACAO": "7455 - TRANSITAR EM VELOCIDADE SUPERIOR A MAXIMA PERMITIDA EM ATE 20%",
            "AUTO_INFRACAO": "X000000001", "RENAINF": "000100X000000001",
            "LOCAL": "RODOVIA EXEMPLO KM 10 - CIDADE EXEMPLO / PE",
            "DATA_HORA_INF": "12/09/2026 14:35:00", "VALOR": "130.16",
            "VENCIMENTO": "20/11/2026", "SITUACAO": "NAO_PAGAS_A_VENCER",
            "DT_IDENT_CONDUTOR": "15/10/2026", "DTA_EXEC": dta,
        })
        renainf.append({
            "PLACA": "TST3C33", "ORGAO": "000200",
            "INFRACAO": "5185 - ESTACIONAR EM DESACORDO COM A REGULAMENTACAO",
            "AUTO_INFRACAO": "Y000000002", "RENAINF": "000200Y000000002",
            "LOCAL": "", "DATA_HORA_INF": "03/08/2026 09:10:00", "VALOR": "195.23",
            "VENCIMENTO": "10/10/2026",
            "SITUACAO": "NAO_PAGAS_VENCIDAS" if dta == "20261005" else "PAGAS",
            "DT_IDENT_CONDUTOR": "", "DTA_EXEC": dta,
        })
    bd.gravar("TB_RENAINF", pd.DataFrame(renainf))

    bd.gravar("TB_RENAJUD", pd.DataFrame([{
        "PLACA": "TST2B22", "TIPO_RESTRICAO": "TRANSFERENCIA",
        "TRIBUNAL": "TRIBUNAL DE JUSTICA EXEMPLO", "ORGAO": "VARA CIVEL EXEMPLO",
        "PROCESSO": "00000000000000000001", "DTA_EXEC": dta,
    } for dta in EXECUCOES]))

    consultas = []
    for dta in EXECUCOES:
        for placa, cnpj, *_ in VEICULOS:
            tem = placa in ("ABC1D23", "TST3C33")
            consultas.append({
                "PLACA": placa, "CNPJ_EMP": cnpj, "DTA_EXEC": dta,
                "CODIGO": 200 if tem or placa != "TST6F66" else 612,
                "MENSAGEM": "A requisição foi processada com sucesso." if tem or placa != "TST6F66"
                            else "A consulta não retornou dados no site ou aplicativo de origem no qual a automação foi executada.",
                "TOTAL_INFRACOES": 1 if tem else 0,
                "DATA_HORA": datetime.strptime(dta + "0830", "%Y%m%d%H%M"),
            })
    bd.gravar("TB_CONSULTA_SENATRAN", pd.DataFrame(consultas))

    bd.gravar("TB_VEICULO_SEM_CERT", pd.DataFrame(
        [dict(zip(("PLACA", "RENAVAM", "UF", "CNPJ_EMP", "CNPJ_PROP", "ATIVO"), v)) for v in SEM_CERT]))

    for tabela in bd.ESQUEMAS:
        print(f"{tabela:<22} {len(bd.ler(tabela)):>3} linha(s) -> {bd.caminho(tabela)}")


if __name__ == "__main__":
    gerar()
