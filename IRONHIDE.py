import re
import os
import json
import shutil
import base64
import requests
import pandas as pd
import armazenamento as bd
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from AesEverywhere import aes256
from config import obter_credencial, senha_do_certificado

hora_ini = datetime.now()
script_dir = os.path.dirname(os.path.abspath(__name__))
pasta_certificados = os.path.join(script_dir, "Certificados")

# obter_credencial("CHAVE_CRIPTOGRAFIA") e o token da API vêm de obter_credencial() (config.py)
TOKEN = obter_credencial("INFOSIMPLES_TOKEN")
URL_API = "https://api.infosimples.com/api/v2/consultas/senatran/infracoes"
# LOCAL, DATA_HORA_INF e DT_IDENT_CONDUTOR não vêm no /infracoes acima; só existem nesse
# endpoint, que é uma consulta paga à parte (por infração). Por isso só é chamado para
# infração que nunca foi detalhada em nenhuma execução — ver propagar_detalhes_conhecidos.
URL_API_DOWNLOAD = "https://api.infosimples.com/api/v2/consultas/senatran/download-infracao"

# =============================================================
# PARÂMETROS DE TESTE — ajuste aqui antes de rodar
# =============================================================

MODO_TESTE = False          # True = usa configs abaixo; False = roda tudo (produção)

# (Na produção havia aqui a escolha entre banco local e remoto; nesta versão pública
#  as tabelas são arquivos Parquet em dados/ -- ver armazenamento.py.)

# Índice da empresa no DataFrame ordenado (0 = primeira, 1 = segunda, ...)
# Use None para rodar todas as empresas (só vale quando MODO_TESTE = False)
EMPRESA_IDX = 0

# Limite de placas por empresa (None = sem limite)
MAX_PLACAS = None

# Pula a placa que veio com MULTA = 0 no DETRAN (coluna MULTA do CADSEN, gravada pelo
# MEGATRON na execução do TRANSFORMER que roda antes deste script).
# 'OE', vazio e NULL NÃO contam como zero: significam que a consulta ao DETRAN falhou, e aí
# não dá para concluir que a placa não tem multa.
#
# ATENÇÃO ao ligar: o senatran/infracoes é base NACIONAL e enxerga infração que o DETRAN
# estadual não mostra (autuação em outro estado, ou ainda não convertida em débito). Na
# checagem contra o histórico, parte das placas com infração no TB_RENAINF
# vinham MULTA = 0 no CADSEN em TODAS as execuções — essas deixam de ser detectadas, e como
# a placa pulada nunca entra no TB_RENAINF, não há como se corrigir depois.
# Colocar False para voltar a consultar todas as placas.
PULAR_PLACA_SEM_MULTA = False  # desligado: placa com MULTA = 0 no DETRAN chegou a ficar fora de execuções seguidas

# Só pula quando dá para provar que o DETRAN respondeu, olhando CUSTO_API > 0 no CADSEN.
# Necessário porque a maioria das funções debito_* do DETRAN.py devolve multa = 0 TAMBÉM
# quando a consulta falha — o `except` zera tudo (debito_PI, debito_RJ, debito_RN, debito_PE,
# debito_CE_pay e debito_PB fazem isso). Só MA e AL têm caminho 'OE'. Sem esta checagem,
# "não consegui perguntar" vira "não tem multa" e a placa é pulada por engano, o que já
# aconteceu com boa parte das placas zeradas numa mesma execução.
# UF raspada por navegador não tem custo de API e por isso nunca é pulada — conservador de
# propósito. Colocar False para pular por MULTA = 0 puro, aceitando esse risco.
EXIGIR_CUSTO_API_PARA_PULAR = True

# Idade máxima, em dias, da execução do CADSEN que pode servir de base para pular placa.
# O SELECT MAX(DTA_EXEC) da PARTE 4 não filtra idade: se o TRANSFORMER não rodou hoje, ou
# falhou para a empresa, o CADSEN mais recente pode ter meses.
# Pular com base numa multa dessa idade cega a placa para tudo que aconteceu no intervalo.
# Acima deste limite o filtro é desligado para a empresa e todas as placas são consultadas.
MAX_DIAS_CADSEN_PARA_PULAR = 7

# =============================================================

# ########## PASTA DE JSONs — limpa a anterior e cria nova ##########

pasta_json = os.path.join(script_dir, "json_ironhide")
if os.path.exists(pasta_json):
    shutil.rmtree(pasta_json)
os.makedirs(pasta_json)
print(f"Pasta de JSONs: {pasta_json}")

# ########## PARTE 1 - CARREGA CERTIFICADOS ##########

dados = []

for arquivo in os.listdir(pasta_certificados):
    if arquivo.lower().endswith(".pfx"):
        caminho_pfx = os.path.join(pasta_certificados, arquivo)
        senha = senha_do_certificado(caminho_pfx)
        try:
            with open(caminho_pfx, 'rb') as f:
                pfx_data = f.read()

            private_key, cert_obj, additional_certs = pkcs12.load_key_and_certificates(
                pfx_data, senha.encode(), backend=default_backend()
            )

            if cert_obj:
                validade = cert_obj.not_valid_after_utc.replace(tzinfo=timezone.utc)
                agora = datetime.now(timezone.utc)

                if agora < validade:
                    assunto = cert_obj.subject.rfc4514_string()
                    cnpj_match = re.search(r'\d{14}', assunto)
                    empresa_match = re.search(r'=([^=]+?):', assunto)

                    if cnpj_match:
                        cnpj_cert = cnpj_match[0]
                        empresa_nome = empresa_match.group(1).strip() if empresa_match else ''
                        dados.append({
                            'EMPRESA': f"{empresa_nome}:{cnpj_cert}",
                            'CNPJ': cnpj_cert,
                            'cert': caminho_pfx,
                            'senha': senha,
                        })

        except Exception as e:
            print(f"Erro ao processar {arquivo}: {e}")

df = pd.DataFrame(dados)
df = df.sort_values(by=['EMPRESA'], ascending=[True]).reset_index(drop=True)
empresas = df[['EMPRESA', 'CNPJ', 'cert', 'senha']].reset_index(drop=True)
num_empresas = len(empresas)

print(f"Total de empresas com certificado válido: {num_empresas}")

# Arquivo de controle manual próprio do Ironhide (separado do empresas_ativas.csv do
# TRANSFORMER, pois roda em cronograma diferente): marque ATIVO como SIM ou NAO por empresa.
caminho_empresas_ativas = os.path.join(script_dir, "empresas_ativas_ironhide.csv")

def carregar_empresas_ativas(caminho, empresas_padrao):
    if os.path.exists(caminho):
        # Se alguém editar e salvar esse CSV pelo Excel sem escolher "CSV UTF-8", o arquivo
        # vira ANSI (cp1252) e quebra a leitura em utf-8. Tenta os dois antes de desistir.
        try:
            cfg = pd.read_csv(caminho, sep=';', dtype=str, encoding='utf-8-sig')
        except UnicodeDecodeError:
            cfg = pd.read_csv(caminho, sep=';', dtype=str, encoding='cp1252')
        cfg['ATIVO'] = cfg['ATIVO'].str.strip().str.upper()
        mapa = dict(zip(cfg['EMPRESA'], cfg['ATIVO'] == 'SIM'))
        return {empresa: mapa.get(empresa, True) for empresa in empresas_padrao}
    else:
        cfg = pd.DataFrame({'EMPRESA': empresas_padrao, 'ATIVO': 'SIM'})
        cfg.to_csv(caminho, sep=';', index=False)
        return {empresa: True for empresa in empresas_padrao}

empresas_ativas = carregar_empresas_ativas(caminho_empresas_ativas, empresas['EMPRESA'].tolist())

# ########## PARTE 2 - TABELAS (Parquet) ##########
# Na produção: conexão com o MySQL (bd_senatran). Nesta versão pública cada tabela é um
# arquivo dados/<TABELA>.parquet com as mesmas colunas (ver armazenamento.py).

dta_exec = datetime.now().strftime('%Y%m%d')

# Uma linha por placa consultada, com o codigo que a API devolveu. Sem ela, consulta
# 200 sem nenhuma multa e consulta que falhou (603 sem saldo, 612, 609...) nao
# deixam rastro nenhum no TB_RENAINF e ficam iguais. O app (atualiza_frota.py) so'
# considera paga a multa que SUMIU de uma consulta com CODIGO = 200.
# Na produção: CREATE TABLE IF NOT EXISTS TB_CONSULTA_SENATRAN (PLACA, CNPJ_EMP, DTA_EXEC,
# CODIGO, MENSAGEM, TOTAL_INFRACOES, DATA_HORA) com PRIMARY KEY (PLACA, CNPJ_EMP, DTA_EXEC).
bd.garantir("TB_CONSULTA_SENATRAN")


def registrar_consulta(placa, cnpj, codigo, mensagem, total):
    """Rodar de novo no mesmo dia sobrescreve: vale o resultado mais recente
    (na produção: INSERT ... ON DUPLICATE KEY UPDATE)."""
    try:
        bd.upsert("TB_CONSULTA_SENATRAN", {
            'PLACA': placa, 'CNPJ_EMP': cnpj, 'DTA_EXEC': dta_exec, 'CODIGO': codigo,
            'MENSAGEM': (mensagem or '')[:255], 'TOTAL_INFRACOES': total,
            'DATA_HORA': datetime.now(),
        }, chave=['PLACA', 'CNPJ_EMP', 'DTA_EXEC'])
    except Exception as e:
        print(f"    Erro ao registrar a consulta da placa {placa}: {e}")

# ########## PARTE 3 - FUNÇÕES ##########

def consulta_api(placa, cnpj, cert_path, senha_cert):
    try:
        with open(cert_path, 'rb') as f:
            cert_bytes = f.read()

        cert_enc = aes256.encrypt(base64.b64encode(cert_bytes).decode(), obter_credencial("CHAVE_CRIPTOGRAFIA"))
        pass_enc = aes256.encrypt(senha_cert, obter_credencial("CHAVE_CRIPTOGRAFIA"))

        args = {
            "token":       TOKEN,
            "placa":       placa,
            "cnpj":        cnpj,
            "pkcs12_cert": cert_enc,
            "pkcs12_pass": pass_enc,
            "timeout":     300,
        }

        response = requests.post(URL_API, args, timeout=350)
        response_json = response.json()
        response.close()

        nome_arquivo = re.sub(r'[^a-zA-Z0-9_-]', '', f"{placa}_{cnpj}") + ".json"
        with open(os.path.join(pasta_json, nome_arquivo), 'w', encoding='utf-8') as f:
            json.dump(response_json, f, ensure_ascii=False, indent=2)

        return response_json

    except Exception as e:
        print(f"    Erro na requisição para placa {placa}: {e}")
        return None


def _extrair_campos(inf):
    # Sem o escape de aspas que o INSERT montado em texto exigia na produção: aqui não há SQL.
    return {
        'auto_infracao':    str(inf.get('auto_infracao', '')),
        'orgao':            str(inf.get('codigo_orgao_autuador', '')),
        'cod_inf':          str(inf.get('codigo_infracao', '')),
        'descricao':        str(inf.get('descricao', '')),
        'valor':            inf.get('valor_total', 0),
        'vencimento':       str(inf.get('data_vencimento', '')),
        'chave':            str(inf.get('chave_infracao', '')),
        'situacao':         str(inf.get('situacao', '')),
        'local':            str(inf.get('local', '')),
        'datahora':         str(inf.get('datahora', '')),
        'dt_ident_condutor':str(inf.get('data_identificacao_condutor', '')),
    }


def inserir_infracoes(placa, infracoes, dta_exec):
    inseridas = 0
    ignoradas = 0
    novas = []  # infrações que de fato entraram na base agora (candidatas a buscar detalhe)

    for inf in infracoes:
        c = _extrair_campos(inf)
        try:
            # Dedup por PLACA + AUTO_INFRACAO + DTA_EXEC: mesmo auto pode reaparecer em dias
            # diferentes (multa ainda aberta). PLACA entra na chave porque numero de auto nao e
            # unico entre veiculos — sem ela, dois veiculos com o mesmo auto na mesma execucao
            # perdem a segunda linha em silencio.
            # (na produção: INSERT INTO TB_RENAINF ... SELECT ... WHERE NOT EXISTS)
            n = bd.inserir('TB_RENAINF', {
                'PLACA':             placa,
                'ORGAO':             c['orgao'],
                'INFRACAO':          f"{c['cod_inf']} - {c['descricao']}",
                'AUTO_INFRACAO':     c['auto_infracao'],
                'RENAINF':           c['chave'],
                'LOCAL':             c['local'],
                'DATA_HORA_INF':     c['datahora'],
                'VALOR':             c['valor'],
                'VENCIMENTO':        c['vencimento'],
                'SITUACAO':          c['situacao'],
                'DT_IDENT_CONDUTOR': c['dt_ident_condutor'],
                'DTA_EXEC':          dta_exec,
            }, chave=['PLACA', 'AUTO_INFRACAO', 'DTA_EXEC'])
            inseridas += n
            if n == 0:
                ignoradas += 1
            elif c['chave']:
                # daqui para frente a chave vai para a API e o auto vai para a atualização do detalhe.
                novas.append({
                    'auto_infracao':  c['auto_infracao'],
                    'chave_infracao': c['chave'],
                })
        except Exception as e:
            print(f"    Erro ao inserir infração {c['auto_infracao']}: {e}")

    return inseridas, ignoradas, novas


def consultar_detalhe_infracao(chave_infracao, placa, cnpj, cert_path, senha_cert):
    """Chamada paga por infração (download-infracao); só usar para infração nunca detalhada."""
    try:
        with open(cert_path, 'rb') as f:
            cert_bytes = f.read()

        cert_enc = aes256.encrypt(base64.b64encode(cert_bytes).decode(), obter_credencial("CHAVE_CRIPTOGRAFIA"))
        pass_enc = aes256.encrypt(senha_cert, obter_credencial("CHAVE_CRIPTOGRAFIA"))

        args = {
            "token":          TOKEN,
            "chave_infracao": chave_infracao,
            "placa":          placa,
            "cnpj":           cnpj,
            "pkcs12_cert":    cert_enc,
            "pkcs12_pass":    pass_enc,
            "timeout":        300,
        }

        response = requests.post(URL_API_DOWNLOAD, args, timeout=350)
        response_json = response.json()
        response.close()

        nome_arquivo = re.sub(r'[^a-zA-Z0-9_-]', '', f"{placa}_{chave_infracao}") + "_detalhe.json"
        with open(os.path.join(pasta_json, nome_arquivo), 'w', encoding='utf-8') as f:
            json.dump(response_json, f, ensure_ascii=False, indent=2)

        if response_json.get('code') != 200:
            return None

        dados_api = response_json.get('data', [])
        return dados_api[0] if dados_api else None

    except Exception as e:
        print(f"    Erro ao consultar detalhe da infração {chave_infracao}: {e}")
        return None


def _extrair_detalhe(detalhe):
    ldh = detalhe.get('local_data_hora', {}) or {}
    autuacao = detalhe.get('autuacao', {}) or {}

    # 'municipio' já vem como "CIDADE / UF" no retorno da API
    local_infracao = str(ldh.get('local_infracao', '') or '').strip()
    municipio = str(ldh.get('municipio', '') or '').strip()
    if local_infracao and municipio:
        local = f"{local_infracao} - {municipio}"
    else:
        local = local_infracao or municipio

    data_infracao = str(ldh.get('data_infracao', '') or '').strip()
    hora_infracao = str(ldh.get('hora_infracao', '') or '').strip()
    datahora = f"{data_infracao} {hora_infracao}".strip()

    dt_ident_condutor = str(autuacao.get('data_limite_indicacao_infrator', '') or '').strip()

    # Sem escape de aspas: quem consome é o atualizar_detalhe_infracao, que usa query parametrizada.
    return {
        'local':             local,
        'datahora':          datahora,
        'dt_ident_condutor': dt_ident_condutor,
    }


def atualizar_detalhe_infracao(placa, auto_infracao, campos, dta_exec):
    """Recebe valores crus (na produção: UPDATE TB_RENAINF parametrizado)."""
    try:
        return bd.atualizar('TB_RENAINF',
                            {'PLACA': placa, 'AUTO_INFRACAO': auto_infracao, 'DTA_EXEC': dta_exec},
                            {'LOCAL':             campos['local'],
                             'DATA_HORA_INF':     campos['datahora'],
                             'DT_IDENT_CONDUTOR': campos['dt_ident_condutor']})
    except Exception as e:
        print(f"    Erro ao atualizar detalhe da infração {auto_infracao}: {e}")
        return 0


def propagar_detalhes_conhecidos(pendentes, dta_exec):
    """Reaproveita detalhe já pago em execução anterior, em vez de chamar a API de novo.

    A dedup do inserir_infracoes é por AUTO_INFRACAO + DTA_EXEC (proposital, para manter o
    histórico diário enquanto a multa segue aberta). O efeito colateral é que toda infração
    ainda em aberto entra como "nova" todo dia e cairia no download-infracao pago de novo.
    Como LOCAL, DATA_HORA_INF e DT_IDENT_CONDUTOR não mudam depois que a infração é lavrada,
    basta copiar da execução anterior. Devolve só as infrações que nunca foram detalhadas.
    """
    if not pendentes:
        return []

    autos = sorted({p['auto_infracao'] for p in pendentes})

    try:
        # PLACA entra na chave: numero de auto nao e unico entre veiculos (ja houve auto
        # repetido em duas placas na base), e o detalhe de um veiculo nao vale para o outro.
        # (na produção: SELECT ... FROM TB_RENAINF WHERE AUTO_INFRACAO IN (...) AND DTA_EXEC <> hoje
        #  AND algum dos três campos preenchido ORDER BY DTA_EXEC)
        renainf = bd.ler('TB_RENAINF')
        hist = renainf[renainf['AUTO_INFRACAO'].isin(autos) & (renainf['DTA_EXEC'] != dta_exec)]
        tem_detalhe = ((hist['LOCAL'].fillna('') != '') |
                       (hist['DATA_HORA_INF'].fillna('') != '') |
                       (hist['DT_IDENT_CONDUTOR'].fillna('') != ''))
        hist = hist[tem_detalhe].sort_values('DTA_EXEC')
        colunas = ['PLACA', 'AUTO_INFRACAO', 'LOCAL', 'DATA_HORA_INF', 'DT_IDENT_CONDUTOR']
        linhas = [tuple(r[c] for c in colunas) for r in bd.registros(hist[colunas])]
    except Exception as e:
        # Sem o histórico não dá para decidir; segue o fluxo antigo (paga) em vez de perder o dado.
        print(f"  Erro ao consultar histórico de detalhes: {e}")
        return pendentes

    # ORDER BY DTA_EXEC crescente + sobrescrita no dict = fica o detalhe da execução mais recente
    conhecidos = {}
    for placa_hist, auto, local, datahora, dt_ident in linhas:
        conhecidos[(str(placa_hist), auto)] = {
            'local':             str(local or ''),
            'datahora':          str(datahora or ''),
            'dt_ident_condutor': str(dt_ident or ''),
        }

    restantes = []
    reaproveitadas = 0
    for item in pendentes:
        campos = conhecidos.get((str(item['placa']), item['auto_infracao']))
        if campos is None:
            restantes.append(item)
        else:
            atualizar_detalhe_infracao(item['placa'], item['auto_infracao'], campos, dta_exec)
            reaproveitadas += 1

    print(f"  {reaproveitadas} infrações reaproveitadas do histórico (nenhuma chamada paga)")
    return restantes


def _multa_zerada(valor):
    """True só quando o DETRAN devolveu um número igual a zero.

    'OE', vazio, None e qualquer coisa não numérica devolvem False de propósito: são falha de
    consulta ao DETRAN, não confirmação de que a placa está limpa.
    """
    try:
        return float(str(valor).replace(',', '.')) == 0
    except (TypeError, ValueError):
        return False


def _consulta_detran_respondeu(custo_api):
    """True quando dá para afirmar que a consulta ao DETRAN daquela placa retornou de fato.

    CUSTO_API > 0 significa que a Infosimples cobrou, logo respondeu. Custo zero, vazio ou
    não numérico é tratado como resposta não confirmada.
    """
    try:
        return float(str(custo_api).replace(',', '.')) > 0
    except (TypeError, ValueError):
        return False


def _dias_desde(dta_cadsen, dta_hoje):
    """Distância em dias entre duas datas YYYYMMDD. None quando não dá para calcular."""
    try:
        return (datetime.strptime(str(dta_hoje), '%Y%m%d')
                - datetime.strptime(str(dta_cadsen), '%Y%m%d')).days
    except (TypeError, ValueError):
        return None


def placas_sem_certificado():
    """Placas cobertas pelo BUMBLEBEE.py (DETRAN estadual) -- nao podem ir para o
    senatran/infracoes: o proprietario nao tem certificado, entao a consulta seria feita
    com o e-CNPJ de outra empresa, e o Senatran so responde pelo dono do certificado
    (consulta paga que volta vazia). Tabela ausente devolve conjunto vazio: nada muda."""
    try:
        cadastro = bd.ler('tb_veiculo_sem_cert')
        cadastro = cadastro[cadastro['ATIVO'].fillna(0) == 1]
        return {str(p).strip().upper() for p in cadastro['PLACA']}
    except Exception as e:
        print(f"  (tb_veiculo_sem_cert nao consultada: {e})")
        return set()


def selecionar_placas(linhas_cadsen, dias_do_cadsen=0):
    """Decide quais placas vão para o senatran/infracoes (pago por placa).

    Recebe as linhas (PLACA, MULTA, CUSTO_API) do CADSEN da última execução da empresa e
    devolve (a_consultar, puladas). Uma placa pode ter mais de uma linha na mesma execução,
    então só é pulada quando TODAS as linhas dela vierem com multa zerada — e, com
    EXIGIR_CUSTO_API_PARA_PULAR ligado, com a consulta ao DETRAN confirmada.

    dias_do_cadsen é a idade da execução usada. Se o dado for velho demais (ou a idade não
    puder ser calculada), ninguém é pulado: multa antiga não diz nada sobre hoje.
    """
    por_placa = {}
    for placa_cad, multa_cad, custo_cad in linhas_cadsen:
        por_placa.setdefault(str(placa_cad), []).append((multa_cad, custo_cad))

    if not PULAR_PLACA_SEM_MULTA:
        return sorted(por_placa), []

    if dias_do_cadsen is None or dias_do_cadsen > MAX_DIAS_CADSEN_PARA_PULAR:
        return sorted(por_placa), []

    a_consultar, puladas = [], []
    for placa_cad in sorted(por_placa):
        linhas = por_placa[placa_cad]
        pode_pular = all(_multa_zerada(m) for m, _ in linhas)
        if pode_pular and EXIGIR_CUSTO_API_PARA_PULAR:
            pode_pular = all(_consulta_detran_respondeu(c) for _, c in linhas)
        (puladas if pode_pular else a_consultar).append(placa_cad)
    return a_consultar, puladas


def processar_placa(placa, cnpj, cert_path, senha_cert):
    placa = re.sub(r'\s+', '', str(placa))
    response_json = consulta_api(placa, cnpj, cert_path, senha_cert)

    if not response_json:
        return placa, None, 0, None, 'sem resposta da API'

    code = response_json.get('code')
    msg = response_json.get('code_message', 'Sem mensagem')
    if code == 200:
        dados_api = response_json.get('data', [])
        if dados_api:
            infracoes = dados_api[0].get('infracoes', [])
            total = dados_api[0].get('total_infracoes', 0)
            return placa, infracoes, total, code, msg
        return placa, [], 0, code, msg
    else:
        print(f"    [{placa}] Código {code}: {msg}")
        return placa, None, 0, code, msg


# ########## PARTE 4 - LOOP POR EMPRESA ##########

if MODO_TESTE and EMPRESA_IDX is not None:
    intervalo_empresas = range(EMPRESA_IDX, EMPRESA_IDX + 1)
    print(f"\n[MODO TESTE] Empresa: índice {EMPRESA_IDX} | Max placas: {MAX_PLACAS}")
else:
    intervalo_empresas = range(num_empresas)

pendentes_detalhe = []  # infrações novas de hoje: candidatas à busca paga de LOCAL/DATA_HORA_INF/DT_IDENT_CONDUTOR

for loop in intervalo_empresas:

    cnpj = empresas["CNPJ"][loop]
    cert_path = empresas["cert"][loop]
    senha_cert = empresas["senha"][loop]
    empresa_nome = empresas["EMPRESA"][loop]

    # MODO_TESTE já escolhe a empresa explicitamente por índice, então o filtro não se aplica nesse caso.
    if not MODO_TESTE and not empresas_ativas.get(empresa_nome, True):
        print(f"\nEmpresa desmarcada para hoje (empresas_ativas_ironhide.csv): {empresa_nome}")
        continue

    print(f"\nEmpresa {loop + 1} de {num_empresas}: {empresa_nome}")

    # Busca a última DTA_EXEC desta empresa no CADSEN
    cadsen = bd.ler('CADSEN')
    cadsen_emp = cadsen[cadsen['CNPJ_EMP'] == cnpj]
    ultima_dta_exec = cadsen_emp['DTA_EXEC'].dropna().max() if len(cadsen_emp) else None

    if not ultima_dta_exec:
        print(f"  Nenhum registro em CADSEN para CNPJ {cnpj}. Pulando.")
        continue

    print(f"  Última DTA_EXEC: {ultima_dta_exec}")

    # Busca as placas dessa execução com a multa que o DETRAN.py apurou e o custo da consulta
    linhas_cadsen = [(r['PLACA'], r['MULTA'], r['CUSTO_API']) for r in bd.registros(
        cadsen_emp.loc[cadsen_emp['DTA_EXEC'] == ultima_dta_exec, ['PLACA', 'MULTA', 'CUSTO_API']])]
    dias_cadsen = _dias_desde(ultima_dta_exec, dta_exec)
    a_consultar, puladas = selecionar_placas(linhas_cadsen, dias_cadsen)

    # Veiculo de proprietario sem certificado e coberto pelo BUMBLEBEE.py, via DETRAN.
    sem_certificado = placas_sem_certificado()
    fora_do_senatran = [p for p in a_consultar if p.strip().upper() in sem_certificado]
    if fora_do_senatran:
        a_consultar = [p for p in a_consultar if p.strip().upper() not in sem_certificado]
        print(f"  {len(fora_do_senatran)} placa(s) fora do Senatran (proprietario sem certificado, ver BUMBLEBEE.py)")

    placas_df = pd.DataFrame({'PLACA': a_consultar})

    if puladas:
        print(f"  {len(puladas)} placas puladas (MULTA = 0 no DETRAN)")
    elif PULAR_PLACA_SEM_MULTA and (dias_cadsen is None or dias_cadsen > MAX_DIAS_CADSEN_PARA_PULAR):
        print(f"  filtro de multa desligado: CADSEN desta empresa tem {dias_cadsen} dias "
              f"(limite {MAX_DIAS_CADSEN_PARA_PULAR}); consultando todas as placas")

    if len(placas_df) == 0:
        print(f"  Nenhuma placa a consultar. Pulando.")
        continue

    if MODO_TESTE and MAX_PLACAS is not None:
        placas_df = placas_df.head(MAX_PLACAS)

    print(f"  {len(placas_df)} placas a consultar. Consultando API...")

    # Consulta em paralelo, até 10 workers simultâneos
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(processar_placa, row['PLACA'], cnpj, cert_path, senha_cert): row['PLACA']
            for _, row in placas_df.iterrows()
        }

        for i, future in enumerate(as_completed(futures), start=1):
            placa_result, infracoes, total, codigo, mensagem = future.result()
            registrar_consulta(placa_result, cnpj, codigo, mensagem,
                               len(infracoes) if infracoes is not None else None)

            if infracoes:
                inseridas, ignoradas, novas = inserir_infracoes(placa_result, infracoes, dta_exec)
                print(f"  [{i}/{len(placas_df)}] {placa_result}: {total} infrações | inseridas={inseridas} ignoradas={ignoradas}")
                for inf_nova in novas:
                    pendentes_detalhe.append({
                        'placa':          placa_result,
                        'cnpj':           cnpj,
                        'cert_path':      cert_path,
                        'senha_cert':     senha_cert,
                        'auto_infracao':  inf_nova['auto_infracao'],
                        'chave_infracao': inf_nova['chave_infracao'],
                    })
            else:
                print(f"  [{i}/{len(placas_df)}] {placa_result}: {total} infrações")

# ########## PARTE 5 - DETALHAR (LOCAL/DATA_HORA_INF/DT_IDENT_CONDUTOR) AS INFRAÇÕES NOVAS ##########
# Só chama o download-infracao (pago por infração) para infração que nunca foi detalhada.
# As que já apareceram em execução anterior têm o detalhe copiado dali de graça, porque esses
# três campos não mudam. Infrações antigas que já estavam no banco sem esses campos não são tocadas.

print(f"\n--- {len(pendentes_detalhe)} infrações inseridas nesta execução ---")
pendentes_detalhe = propagar_detalhes_conhecidos(pendentes_detalhe, dta_exec)

print(f"--- Buscando detalhes de {len(pendentes_detalhe)} infrações inéditas (chamada paga) ---")
total_detalhadas = 0

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {
        executor.submit(
            consultar_detalhe_infracao,
            item['chave_infracao'], item['placa'], item['cnpj'], item['cert_path'], item['senha_cert']
        ): item
        for item in pendentes_detalhe
    }

    for i, future in enumerate(as_completed(futures), start=1):
        item = futures[future]
        detalhe = future.result()

        if not detalhe:
            print(f"  [{i}/{len(pendentes_detalhe)}] {item['placa']} ({item['auto_infracao']}): sem detalhe retornado")
            continue

        campos = _extrair_detalhe(detalhe)
        n = atualizar_detalhe_infracao(item['placa'], item['auto_infracao'], campos, dta_exec)
        total_detalhadas += n
        print(f"  [{i}/{len(pendentes_detalhe)}] {item['placa']} ({item['auto_infracao']}): atualizado={bool(n)}")

print(f"Total de infrações detalhadas: {total_detalhadas}")

# ########## FIM ##########

# (na produção: cursor.close() / con.close())

hora_fim = datetime.now()
print(f"\nConcluído em {str(hora_fim - hora_ini)}")
