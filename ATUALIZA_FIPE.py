import requests
from datetime import datetime

import armazenamento as bd
from config import FIPE_WEBHOOK_URL

# =====================================================
# 1️⃣ PADRONIZAÇÃO DO TIPO
# =====================================================

def padronizar_tipo(tipo):
    tipo_upper = tipo.upper()

    if "CAMINHAO" in tipo_upper:
        return "CAMINHAO"
    elif "CAMIONETA" in tipo_upper:
        return "AUTOMOVEL"
    elif tipo_upper in ["UTILITARIO", "CAMINHONETE"]:
        return "AUTOMOVEL"
    else:
        return tipo_upper


# =====================================================
# 2️⃣ CONSUMIR API FIPE
# =====================================================

def fipe_webhook(tipo, modelo, ano):

    tipo_padronizado = padronizar_tipo(tipo)

    url = (
        FIPE_WEBHOOK_URL +
        f"?tipo={tipo_padronizado}&modelo={modelo}&ano={ano}"
    )

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        dados = data.get("dados")

        # ✅ Se for lista válida
        if isinstance(dados, list) and len(dados) > 0 and isinstance(dados[0], dict):
            item = dados[0]

            return {
                "codeFipe": item.get("codeFipe", 0),
                "referenceMonth": item.get("referenceMonth", ""),
                "price": item.get("price", "")
            }

        # ❌ Se não for lista ou estiver vazio
        return {
            "codeFipe": 0,
            "referenceMonth": "",
            "price": ""
        }

    except Exception as e:
        print(f"Erro na requisição: {e}")
        return {
            "codeFipe": 0,
            "referenceMonth": "",
            "price": ""
        }

# =====================================================
# 3️⃣ BASE (na produção: conexão com o MySQL bd_senatran;
#     nesta versão pública: arquivos Parquet em dados/, ver armazenamento.py)
# =====================================================


# =====================================================
# 4️⃣ BUSCAR REGISTROS DA TABELA CADSEN
# =====================================================

dta_exec = datetime.now().strftime('%Y%m%d')

# Equivale a: SELECT MODELO, ANO, TIPO FROM CADSEN WHERE DTA_EXEC = %s
cadsen = bd.ler("CADSEN")
registros = bd.registros(cadsen.loc[cadsen["DTA_EXEC"] == dta_exec, ["MODELO", "ANO", "TIPO"]])


# =====================================================
# 5️⃣ PROCESSAR CADA REGISTRO E DAR UPDATE
# =====================================================

for row in registros:
    modelo = row["MODELO"]
    ano = row["ANO"]
    tipo = row["TIPO"]

    print(f"Consultando: {tipo} | {modelo} | {ano}")

    resultado = fipe_webhook(tipo, modelo, ano)

    if resultado:
        # Equivale a: UPDATE CADSEN SET COD_FIPE, MESREFERENCIA, TABELA_FIPE
        #             WHERE MODELO = %s AND ANO = %s AND TIPO = %s AND DTA_EXEC = %s
        bd.atualizar(
            "CADSEN",
            {"MODELO": modelo, "ANO": ano, "TIPO": tipo, "DTA_EXEC": dta_exec},
            {
                "COD_FIPE": resultado["codeFipe"],
                "MESREFERENCIA": resultado["referenceMonth"],
                "TABELA_FIPE": resultado["price"],
            }
        )

        print("[OK] Atualizado com sucesso")

    else:
        print("[X] Não encontrado na FIPE")


print("Processo finalizado.")
