"""Configuracao central dos robos.

Nenhum segredo fica no codigo. Toda credencial (token da API, chave de
criptografia, senhas de certificado, login de portal) e pedida pela funcao
obter_credencial(nome), que e o unico ponto a ligar na fonte de segredos de
quem for usar: variavel de ambiente, cofre de senhas, arquivo protegido etc.

Os CNPJs e nomes de empresa que aparecem aqui como padrao sao FICTICIOS
(bases com digitos repetidos, que nao existem na Receita).
"""

import json
import os


def _json_do_ambiente(nome, padrao):
    texto = os.getenv(nome, "").strip()
    if not texto:
        return padrao
    return json.loads(texto)


# =============================================================
# CREDENCIAIS
# =============================================================

def obter_credencial(nome):
    """Devolve a credencial `nome`.

    Ponto unico de leitura de segredos. Por padrao le a variavel de ambiente
    de mesmo nome; troque o corpo desta funcao para buscar no seu cofre.
    Sem a credencial, devolve "" (o robo falha na chamada da API, nao aqui).

    Nomes usados pelos robos:
        INFOSIMPLES_TOKEN, CHAVE_CRIPTOGRAFIA, SENHA_CERTIFICADO,
        SENHA_CERTIFICADO_<cnpj>, DETRAN_RN_CNPJ, DETRAN_RN_SENHA
    """
    return os.getenv(nome, "")


def senha_do_certificado(caminho_pfx):
    """O nome do .pfx traz o CNPJ; se houver SENHA_CERTIFICADO_<cnpj>, usa ela,
    senao a SENHA_CERTIFICADO padrao."""
    cnpj = "".join(c for c in os.path.basename(caminho_pfx) if c.isdigit())[-14:]
    return obter_credencial(f"SENHA_CERTIFICADO_{cnpj}") or obter_credencial("SENHA_CERTIFICADO")


# =============================================================
# FIPE
# =============================================================

# Webhook que devolve o codigo FIPE a partir de tipo/modelo/ano
FIPE_WEBHOOK_URL = os.getenv("FIPE_WEBHOOK_URL", "https://exemplo.invalid/webhook/veiculos/fipe")


# =============================================================
# FILIAIS (CNPJ -> UF do DETRAN a consultar) -- FICTICIO
# =============================================================

CNPJS_POR_UF = _json_do_ambiente("CNPJS_POR_UF_JSON", {
    "MA": ("11111111000292",),
    "CE": ("55555555000155",),
    "PE": ("11111111000111",),
    "AL": ("44444444000144",),
    "PI": ("22222222000122",),
    "RJ": ("33333333000133",),
    "PB": ("66666666000166",),
    "RN": ("77777777000177",),
})

# "EMPRESA:CNPJ" -> UF, usado pelo TRANSFORMER quando a BrasilAPI nao responde
MAPA_UF_EMPRESA = _json_do_ambiente("MAPA_UF_EMPRESA_JSON", {
    "DISTRIBUIDORA EXEMPLO ALFA LTDA:11111111000111": "PE",
    "DISTRIBUIDORA EXEMPLO ALFA LTDA:11111111000292": "MA",
    "DISTRIBUIDORA EXEMPLO BETA LTDA:22222222000122": "PI",
    "LOGISTICA EXEMPLO GAMA LTDA:33333333000133": "RJ",
    "TRANSPORTES EXEMPLO DELTA LTDA:44444444000144": "AL",
    "DISTRIBUIDORA EXEMPLO EPSILON LTDA:55555555000155": "CE",
    "DISTRIBUIDORA EXEMPLO ZETA LTDA:66666666000166": "PB",
    "DISTRIBUIDORA EXEMPLO ETA LTDA:77777777000177": "RN",
})

# Filiais de MA e PB cuja frota pode estar emplacada em PE: quando o DETRAN do
# estado devolve 'OE' (outro estado), o DETRAN.py tenta o de PE.
CNPJ_MA_PLACAS_PE = os.getenv("CNPJ_MA_PLACAS_PE", "11111111000292")
CNPJ_PB_PLACAS_PE = os.getenv("CNPJ_PB_PLACAS_PE", "66666666000166")

# DETRAN-RN: a consulta exige login (CNPJ + senha do portal) da filial;
# vem de obter_credencial("DETRAN_RN_CNPJ") / obter_credencial("DETRAN_RN_SENHA")


# =============================================================
# FERRAMENTAS LOCAIS (OCR de captcha)
# =============================================================

RSCRIPT_PATH = os.getenv("RSCRIPT_PATH", "Rscript")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
