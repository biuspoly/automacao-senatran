import requests
import json

from config import FIPE_WEBHOOK_URL

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


def fipe_webhook(tipo, modelo, ano):

    tipo_padronizado = padronizar_tipo(tipo)

    # Webhook interno (URL no .env) que casa tipo/modelo/ano com a tabela FIPE
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

            return item.get("codeFipe", 0)

        # ❌ Se não for lista ou estiver vazio
        return 0

    except Exception as e:
        print(f"Erro na requisição: {e}")
        return 0
