"""Camada de armazenamento em Parquet.

Na producao os robos gravam num MySQL/MariaDB (base bd_senatran). Nesta versao
publica cada tabela virou um arquivo dados/<TABELA>.parquet, com as MESMAS
colunas, e os dados que vem no repositorio sao FICTICIOS (gerados por
dados/gerar_dados_ficticios.py).

As operacoes abaixo reproduzem, com pandas, o que o SQL fazia:
  - inserir(..., chave=[...])  ->  INSERT ... WHERE NOT EXISTS (dedup pela chave)
  - upsert(...)                ->  INSERT ... ON DUPLICATE KEY UPDATE
  - atualizar(...)             ->  UPDATE ... WHERE
  - apagar(...)                ->  DELETE ... WHERE
"""

import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

ESQUEMAS = {
    # Foto de cada veiculo por execucao (Senatran + DETRAN + FIPE)
    "CADSEN": [
        "CNPJ_EMP", "UF", "CNPJ_PROP", "PLACA", "TIPO", "MODELO", "ANO_FAB", "ANO",
        "CARROCERIA", "CHASSI", "RENAVAM", "GRAVAME", "GRAVAME_PENDENTE",
        "RESTRICAO_ADM", "RENAJUD", "PROCESSO", "TIPO_RESTRICAO", "TRIBUNAL",
        "ORGAO", "TOTAL_PROCESSOS", "COD_FIPE", "INFO_UF_FIPE", "DEBITO_DETRAN",
        "LICENCIAMENTO", "MULTA", "IPVA", "IPVA_AL_ANT", "CUSTO_API", "DTA_EXEC",
        "TABELA_FIPE", "COMBUSTIVEL", "MESREFERENCIA",
    ],
    # Infracoes (RENAINF) -- uma linha por execucao enquanto a multa segue aberta
    "TB_RENAINF": [
        "PLACA", "ORGAO", "INFRACAO", "AUTO_INFRACAO", "RENAINF", "LOCAL",
        "DATA_HORA_INF", "VALOR", "VENCIMENTO", "SITUACAO", "DT_IDENT_CONDUTOR",
        "DTA_EXEC",
    ],
    # Restricoes judiciais (RENAJUD)
    "TB_RENAJUD": ["PLACA", "TIPO_RESTRICAO", "TRIBUNAL", "ORGAO", "PROCESSO", "DTA_EXEC"],
    # Uma linha por placa consultada no senatran/infracoes (IRONHIDE)
    "TB_CONSULTA_SENATRAN": [
        "PLACA", "CNPJ_EMP", "DTA_EXEC", "CODIGO", "MENSAGEM", "TOTAL_INFRACOES", "DATA_HORA",
    ],
    # Veiculos cujo proprietario nao tem certificado (BUMBLEBEE)
    "TB_VEICULO_SEM_CERT": ["PLACA", "RENAVAM", "UF", "CNPJ_EMP", "CNPJ_PROP", "ATIVO"],
    # Cadastro das empresas (o app resolve o nome por CNPJ_EMP)
    "TB_EMPRESAS": ["CNPJ_EMP", "EMPRESA"],
}

COLUNAS_INTEIRAS = {"TOTAL_PROCESSOS", "CODIGO", "TOTAL_INFRACOES", "ATIVO"}
COLUNAS_DATA = {"DATA_HORA"}


def _nome(tabela):
    return tabela.upper()


def caminho(tabela):
    return os.path.join(PASTA_DADOS, f"{_nome(tabela)}.parquet")


def _vazio(valor):
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def _schema(tabela):
    campos = []
    for coluna in ESQUEMAS[_nome(tabela)]:
        if coluna in COLUNAS_INTEIRAS:
            campos.append(pa.field(coluna, pa.int64()))
        elif coluna in COLUNAS_DATA:
            campos.append(pa.field(coluna, pa.timestamp("us")))
        else:
            campos.append(pa.field(coluna, pa.string()))
    return pa.schema(campos)


def _tipar(df, tabela):
    """Mesmas colunas, na mesma ordem, e tipos estaveis: quase tudo e texto, como
    no banco (VARCHAR) -- inclusive valores como MULTA, que podem vir 'OE'."""
    df = df.reindex(columns=ESQUEMAS[_nome(tabela)]).copy()
    for coluna in df.columns:
        if coluna in COLUNAS_INTEIRAS:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
        elif coluna in COLUNAS_DATA:
            df[coluna] = pd.to_datetime(df[coluna], errors="coerce")
        else:
            df[coluna] = df[coluna].map(lambda v: None if _vazio(v) else str(v)).astype(object)
    return df


def ler(tabela):
    arquivo = caminho(tabela)
    if os.path.exists(arquivo):
        return pd.read_parquet(arquivo)
    return _tipar(pd.DataFrame(columns=ESQUEMAS[_nome(tabela)]), tabela)


def gravar(tabela, df):
    os.makedirs(PASTA_DADOS, exist_ok=True)
    df = _tipar(df, tabela)
    pq.write_table(pa.Table.from_pandas(df, schema=_schema(tabela), preserve_index=False),
                   caminho(tabela))


def garantir(tabela):
    """Equivalente ao CREATE TABLE IF NOT EXISTS: cria o Parquet vazio."""
    if not os.path.exists(caminho(tabela)):
        gravar(tabela, pd.DataFrame(columns=ESQUEMAS[_nome(tabela)]))


def registros(df):
    """DataFrame -> lista de dicts, com nulo virando None (e nao NaN, que e
    'verdadeiro' num `valor or ''`)."""
    return [{k: (None if _vazio(v) else v) for k, v in linha.items()}
            for linha in df.to_dict("records")]


def _texto(valor):
    return "" if _vazio(valor) else str(valor)


def _mascara(df, filtro):
    mascara = pd.Series(True, index=df.index)
    for coluna, valor in filtro.items():
        mascara &= df[coluna].map(lambda v: (not _vazio(v)) and str(v) == str(valor)).astype(bool)
    return mascara


def inserir(tabela, linhas, chave=None):
    """INSERT ... WHERE NOT EXISTS: so entra a linha cuja chave ainda nao existe
    (nem no arquivo nem antes no mesmo lote). Devolve quantas entraram -- o
    `cursor.rowcount` que os robos usavam."""
    if isinstance(linhas, dict):
        linhas = [linhas]
    if not linhas:
        return 0

    atual = ler(tabela)
    novas = []
    if chave:
        vistas = {tuple(_texto(v) for v in linha)
                  for linha in atual[chave].itertuples(index=False, name=None)}
        for linha in linhas:
            k = tuple(_texto(linha.get(c)) for c in chave)
            if k in vistas:
                continue
            vistas.add(k)
            novas.append(linha)
    else:
        novas = list(linhas)

    if novas:
        acrescimo = pd.DataFrame(novas)
        gravar(tabela, pd.concat([atual, acrescimo], ignore_index=True) if len(atual) else acrescimo)
    return len(novas)


def upsert(tabela, linha, chave):
    """INSERT ... ON DUPLICATE KEY UPDATE: vale a linha mais recente."""
    atual = ler(tabela)
    if len(atual):
        atual = atual[~_mascara(atual, {c: linha.get(c) for c in chave})]
    acrescimo = pd.DataFrame([linha])
    gravar(tabela, pd.concat([atual, acrescimo], ignore_index=True) if len(atual) else acrescimo)


def atualizar(tabela, filtro, valores):
    """UPDATE tabela SET <valores> WHERE <filtro>. Devolve quantas linhas mudaram."""
    atual = ler(tabela)
    if not len(atual):
        return 0
    mascara = _mascara(atual, filtro)
    total = int(mascara.sum())
    if total:
        for coluna, valor in valores.items():
            if coluna in COLUNAS_INTEIRAS:
                atual.loc[mascara, coluna] = valor
            else:
                atual.loc[mascara, coluna] = None if _vazio(valor) else str(valor)
        gravar(tabela, atual)
    return total


def apagar(tabela, filtro):
    """DELETE FROM tabela WHERE <filtro>. Devolve quantas linhas sairam."""
    atual = ler(tabela)
    if not len(atual):
        return 0
    mascara = _mascara(atual, filtro)
    total = int(mascara.sum())
    if total:
        gravar(tabela, atual[~mascara])
    return total
