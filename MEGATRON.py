import json
import pandas as pd
from datetime import datetime
import asyncio
from pydoll.browser.chrome import Chrome
from pydoll.constants import By
import pyautogui as py
import re
from DETRAN import veic_detran
import os
import requests
from pydoll.browser.options import Options as Optionsp
import base64
from AesEverywhere import aes256
import time
import armazenamento as bd
from API_FIPE import fipe_webhook
from config import obter_credencial, CNPJS_POR_UF

print('Executando Megatron.py')


loop = 1
script_dir = os.path.dirname(os.path.abspath(__name__))

caminho_salvar=f"{script_dir}\\senatran_"
# Na produção: engine SQLAlchemy -> MySQL (bd_senatran). Nesta versão pública as tabelas
# são arquivos Parquet em dados/ (ver armazenamento.py).
con = None  # o DETRAN.py ainda recebe este parâmetro; quem lê/grava agora é o módulo bd



# variáveis que vêm de Transformer.py
cnpj = [cnpj]
# cnpj = ['11111111000111']  # teste (CNPJ fictício)
# obter_credencial("CHAVE_CRIPTOGRAFIA") vem de obter_credencial() (config.py)
# cert = os.path.join(script_dir, 'Certificados', 'EMPRESA EXEMPLO ALFA 11111111000111.pfx')  # teste
cert = cert
senha = senha


planilhao=pd.DataFrame()
nao_encontrado=pd.DataFrame()

listagem_nao_encontrada=pd.DataFrame()

pag = 1
num_pag = 100 #Foi atribuído um número "grande" de páginas só para ser alterado depois

# O loop deverá rodar até o número total de páginas que é retornada pela API
while pag <= num_pag:
  
    url = 'https://api.infosimples.com/api/v2/consultas/senatran/meus-veiculos-posse'
    args = {
        "cnpj":        cnpj,
        "pagina":      f'{pag}',
        "pkcs12_cert": aes256.encrypt(base64.b64encode(open(cert, "rb").read()).decode(), obter_credencial("CHAVE_CRIPTOGRAFIA")),
        "pkcs12_pass": aes256.encrypt(senha, obter_credencial("CHAVE_CRIPTOGRAFIA")),
        "token":       obter_credencial("INFOSIMPLES_TOKEN"),
        "timeout":     600
    }
    # time.sleep(15)
    response = requests.post(url, args)
    # time.sleep(15)
    response_json = response.json()
    response.close()
    
    # arquivo = open("senatran_teste_veiculo.json", "w", encoding="utf-8")
    # json.dump(response_json, arquivo, ensure_ascii=False, indent=2)
    # arquivo.close()
    
    
    print('Requisicao de posse de veiculos: ', response_json['code'])

    # arquivo = open(r"senatran_teste.json", encoding="utf-8")
    # response_json = json.load(arquivo)

    # Se a api funcionar, todo o restante do loop deverá funcionar, caso contrário, será feito um xlsx com os dados que não conseguiram ser consultados
    if response_json['code']==200:
        veiculos = pd.DataFrame(response_json['data'][0]['veiculos']) # Retornará todas informações dos "cards", como placa e renavam.
        # veiculos = pd.read_excel("senatran_nao_encontrado.xlsx",dtype='str') 
        

        num_veic = len(veiculos)
        # num_veic = 2
        num_pag = int(response_json['data'][0]['total_paginas']) # Nova atribuição para o total de páginas que deverá funcionar no loop
        # num_pag = 1

        
        # O loop seguinte irá percorrer todas as linhas de placas e renavam. Depois disso, irá coletar os dados de cada veículo disponível na API
        for num in range(0,num_veic):
            placa_num = veiculos['placa'][num]
            renav_num = veiculos['renavam'][num]

            # Anter de coletar os dados, deverá ser verificado se a placa e data de execução do script constam na base de dados
            # verifica_placa = cursor.execute(f"SELECT * FROM CADSEN WHERE PLACA = '{placa_num}' AND DTA_EXEC = strftime('%Y%m%d',date('now'))") # sqlite

            # Equivale ao SELECT * FROM CADSEN WHERE PLACA = :placa AND DTA_EXEC = hoje (MySQL)
            cadsen = bd.ler("CADSEN")
            bd_completo_placa = cadsen[(cadsen["PLACA"] == placa_num) &
                                       (cadsen["DTA_EXEC"] == datetime.now().strftime('%Y%m%d'))]

            # Caso não tenha dados, seguir em frente para a coleta. Caso contrário, o próximo veículo será verificado.
            if len(bd_completo_placa)==0:
            
                url = 'https://api.infosimples.com/api/v2/consultas/senatran/meus-veiculos-comp'
                args = {
                "renavam":     renav_num,
                "placa":       placa_num,
                "cnpj":        cnpj,
                "pkcs12_cert": aes256.encrypt(base64.b64encode(open(cert, "rb").read()).decode(), obter_credencial("CHAVE_CRIPTOGRAFIA")),
                "pkcs12_pass": aes256.encrypt(senha, obter_credencial("CHAVE_CRIPTOGRAFIA")),
                "token":       obter_credencial("INFOSIMPLES_TOKEN"),
                "timeout":     600
                }
                
                print(placa_num)
                tentativas_veic = 0
                while tentativas_veic < 5:
                    response = requests.post(url, args)
                    response_json = response.json()
                    response.close()
                    print('Requisicao de veiculo: ', response_json['code'])
                    if response_json['code'] == 200:
                        break
                    tentativas_veic += 1
                    if tentativas_veic < 5:
                        print(f'Tentativa {tentativas_veic} falhou (code {response_json["code"]}). Aguardando para tentar novamente...')
                        time.sleep(10)


                # arquivo = open(r"senatran_teste_veiculo.json", encoding="utf-8")
                # response_json = json.load(arquivo)
                
                # Se a api funcionar, todo o restante do loop deverá funcionar, caso contrário, será feito um xlsx com os dados que não conseguiram ser consultados
                if response_json['code']==200:
                    dados=pd.DataFrame([response_json['data'][0]])
                    
                    # cnpj = [dados['normalizado_arrendatario_cnpj'].astype('str').iloc[0]]
                    
                    # CNPJ da filial -> UF do DETRAN a consultar (lista real fica fora do repositório; ver config.py)
                    if cnpj[0] in CNPJS_POR_UF['MA']:
                        uf=['MA']
                    elif cnpj[0] in CNPJS_POR_UF['CE']:
                        uf=['CE']
                    elif cnpj[0] in CNPJS_POR_UF['PE']:
                        uf=['PE']
                    elif cnpj[0] in CNPJS_POR_UF['AL']:
                        uf=['AL']
                    elif cnpj[0] in CNPJS_POR_UF['PI']:
                        uf=['PI']
                    elif cnpj[0] in CNPJS_POR_UF['RJ']:
                        uf=['RJ']
                    elif cnpj[0] in CNPJS_POR_UF['PB']:
                        uf=['PB']
                    elif cnpj[0] in CNPJS_POR_UF['RN']:
                        uf=['RN']
                    else:
                        uf = ''
                    
                    
                    placa = [placa_num]
                    cnpj_prop = dados['cnpj'].astype('str').iloc[0]
                    tipo = [dados['tipo'].astype('str').iloc[0]]
                    modelo = [dados['marca_modelo'].astype('str').iloc[0]]
                    fabricacao = [dados['ano_fabricacao'].astype('str').iloc[0]]
                    ano = [dados['ano_modelo'].astype('str').iloc[0]]
                    carroceria = [dados['carroceria'].astype('str').iloc[0]]
                    chassi = [dados['chassi'].astype('str').iloc[0]]
                    renavam = [renav_num]
                    RADM = [dados['restricao_1'].astype('str').iloc[0]]
                    RJUD = [dados['existe_renajud'].astype('str').iloc[0]]
                    
                    # importante ressaltar que essa parte funciona com 1 processo por veículo, pois não vi veículos com mais que isso.
                    if RJUD[0] == 'True':
    
                        lista = dados['renajud_detalhes'][0]['lista']
                        total_proc = dados['renajud_detalhes'][0]['quantidade']
                        
                        linhas = []
                    
                        for proc in lista:
                            numero_processo = proc['numero_processo']
                            tribunal = proc['tribunal_nome']
                            orgao = proc['orgao_nome']
                            
                            # pode ter mais de uma restrição por processo
                            for restr in proc['restricoes_judiciais']:
                                tipo_rest = restr['restricao_descricao']
                                
                                linhas.append({
                                    'placa': placa_num,
                                    'processo': numero_processo,
                                    'tribunal': tribunal,
                                    'orgao': orgao,
                                    'tipo_restricao': tipo_rest,
                                    'dta_exec': datetime.now().strftime('%Y%m%d')
                                })
                        # Equivale ao DELETE + INSERT em TB_RENAJUD do MySQL: limpa os processos da placa no dia e grava os atuais
                        bd.apagar("TB_RENAJUD", {"PLACA": placa_num, "DTA_EXEC": datetime.now().strftime('%Y%m%d')})
                        bd.inserir("TB_RENAJUD", [{
                            "PLACA": l["placa"], "TIPO_RESTRICAO": l["tipo_restricao"],
                            "TRIBUNAL": l["tribunal"], "ORGAO": l["orgao"],
                            "PROCESSO": l["processo"], "DTA_EXEC": l["dta_exec"],
                        } for l in linhas])

                        df_rjud = pd.DataFrame(linhas)
                        RJUD = 'Sim'
                    else:
                        df_rjud = pd.DataFrame()
                        RJUD = 'Não'
                        total_proc = 0
                    
                    # Junta os dados em um DataFrame
                    veiculo_dados= {
                        'Placa': [placa_num],
                        'Renavam': [renav_num],
                        'CNPJ': cnpj,
                        'UF': uf,
                        'CNPJ_PROP': cnpj_prop,
                        'Tipo': tipo,
                        'Modelo': modelo,
                        'Ano': ano,
                        'Ano Fabricação': fabricacao,
                        'Carroceria': carroceria,
                        'Chassi': chassi,
                        'Gravame': RADM,
                        'Restricao Adm': RADM,
                        'RENAJUD': RJUD,
                        'Processo': '',
                        'Tipo Restricao': '',
                        'Tribunal': '',
                        'Orgao': '',
                        'Total de Processos': total_proc,
                        'Data execucao': datetime.now().strftime('%Y%m%d')
                        
                    }
                    
                    planilha=pd.DataFrame(veiculo_dados)

                    # Os dados vão sendo adicionados à um dataframe externa que funcionará para o restante do script
                    planilhao=pd.concat([planilhao, planilha], ignore_index=True)
                    time.sleep(20)
                    
                    
                else:
                    dados_nao_encontrados = {
                        'Placa': [placa_num],
                        'Renavam': [renav_num],
                        'Status requisicao': response.status_code,
                        'Status json': response_json['code'],
                        'Preco': response_json['header']['price'],
                        'Data/Hora req.': response_json['header']['requested_at'],
                        'API': response_json['header']['service'],
                        'IP remoto': response_json['header']['remote_ip'],
                        'Assinatura': response_json['header']['signature']
                        
                    }
                    sem_requisicao = pd.DataFrame(dados_nao_encontrados)
                    nao_encontrado = pd.concat([nao_encontrado,sem_requisicao],ignore_index=True)
                    time.sleep(20)
        print(planilhao)
    else:
        dados_listagem_nao_encontrados = {
                    'Cnpj': cnpj,
                    'Pagina': pag,
                    'Status requisicao': response.status_code,
                    'Status json': response_json['code'],
                    'Preco': response_json['header']['price'],
                    'Data/Hora req.': response_json['header']['requested_at'],
                    'API': response_json['header']['service'],
                    'IP remoto': response_json['header']['remote_ip'],
                    'Assinatura': response_json['header']['signature']
                    
                }
        listagem_sem_requisicao = pd.DataFrame(dados_listagem_nao_encontrados)
        listagem_nao_encontrada = pd.concat([listagem_nao_encontrada,listagem_sem_requisicao],ignore_index=True)
        num_pag=1           
    pag += 1

# Caso a primeira api nao funcione. O arquivo será gerado a partir daqui 
if len(listagem_nao_encontrada)>0:
  listagem_nao_encontrada.to_excel(caminho_salvar + 'listagem_nao_encontrada.xlsx',index=False)
  
# Caso a segunda api nao funcione. O arquivo será gerado a partir daqui
if len(nao_encontrado)>0:
  nao_encontrado.to_excel(caminho_salvar + 'nao_encontrado.xlsx',index=False)

    # num_pag = 10
# print(response_json['code'])

# Caso nao tenha dados no dataframe, essa parte do código nao roda
if len(planilhao)>0:
    planilhao.loc[~planilhao['Restricao Adm'].str.contains('ADM', na=False), 'Restricao Adm'] = 'Não'
    planilhao.loc[planilhao['Restricao Adm'].str.contains('ADM', na=False), 'Restricao Adm'] = 'Sim'
    planilhao.loc[planilhao['Gravame'].isna() | (planilhao['Gravame'] == '') | planilhao['Gravame'].str.contains('ADM|Não|SEM RESTRICAO', na=False), 'Gravame'] = 'Não'
    planilhao.loc[~(planilhao['Gravame'].isna() | (planilhao['Gravame'] == '') | planilhao['Gravame'].str.contains('ADM|Não|SEM RESTRICAO', na=False)), 'Gravame'] = 'Sim'


    tabela_fipe=pd.DataFrame(columns=['Tabela FIPE'])
    INFO_UF_FIPE=pd.DataFrame(columns=['INFO_UF_FIPE'])
    
    for placa_fipe in planilhao['Placa'].values:
        linha_placa = planilhao.loc[planilhao['Placa'] == placa_fipe]

    try:
        cod_fipe = fipe_webhook(
            linha_placa['Tipo'].iloc[0],
            linha_placa['Modelo'].iloc[0],
            linha_placa['Ano'].iloc[0])
        
    except Exception as e:
        print(f"Erro ao consultar FIPE: {e}")
        cod_fipe = None


    if not cod_fipe or pd.isna(cod_fipe):
        cod_fipe = 0
        cidade_uf = ''
    else:
        cidade_uf = ''

    tabela_fipe = tabela_fipe._append({'Tabela FIPE': cod_fipe}, ignore_index=True)
    INFO_UF_FIPE = INFO_UF_FIPE._append({'INFO_UF_FIPE': cidade_uf}, ignore_index=True)
    
    planilhao=pd.concat([planilhao,tabela_fipe,INFO_UF_FIPE],axis=1)

    
    print(planilhao)

    # Essa parte do código deverá rodar o script DETRAN.py, que deve estar no mesmo diretório desse aqui.
    async def main():
        veiculos = await veic_detran(planilhao, cert, con, senha, loop)
        return veiculos
    veiculos = asyncio.run(main())

    # veiculos = veiculos.reset_index(drop=True)
    print(veiculos)
    planilhao=pd.concat([planilhao,veiculos],axis=1)

    planilhao=planilhao[['CNPJ','UF','CNPJ_PROP','Placa','Tipo','Modelo','Ano Fabricação','Ano','Renavam','Carroceria','Chassi', 'Gravame','Gravame Pendente','Restricao Adm','RENAJUD',
                                'Processo','Tipo Restricao','Tribunal','Orgao','Total de Processos','Tabela FIPE',
                                'INFO_UF_FIPE','Debito Detran','Licenciamento','Multa','IPVA', 'IPVA Ant','Custo','Data execucao']]

    # planilhao.to_excel(caminho_salvar + re.sub(r'\W+', '', planilhao['CNPJ'][0]) + '.xlsx',index=False)


    # ALTERACOES NO BANCO DE DADOS


    colunas_fipe = ['valor', 'combustivel', 'mesReferencia', 'siglaCombustivel', 'dataConsulta']

    # Esse loop servirá para fazer requisições do FIPE de cada veículo do Dataframe, afim de coletar as os valores da linha acima
    for linha in range(0,len(planilhao)):
        
        codigoFipe = planilhao["Tabela FIPE"][linha]
        ano = planilhao["Ano"][linha]
        
        url = f'https://brasilapi.com.br/api/fipe/preco/v1/{codigoFipe}'
                    
        try:
            dados = requests.get(url)
            response = pd.DataFrame(dados.json())
            resultado = response[colunas_fipe][response['anoModelo'].astype(str)==ano]
            resultado = resultado.reset_index(drop=True)
            
            valor, combustivel, mesReferencia, siglaCombustivel, dataConsulta = resultado['valor'][0],resultado['combustivel'][0],resultado['mesReferencia'][0],resultado['siglaCombustivel'][0],resultado['dataConsulta'][0]
            
        except:
            valor, combustivel, mesReferencia, siglaCombustivel, dataConsulta = '','','','',''
        
        # Novamente, se por acaso a placa e data de execução do script constar na base de dados, ele não irá adicionar os dados à mesma.
        # Equivale ao SELECT * FROM CADSEN WHERE PLACA = :placa AND DTA_EXEC = hoje (MySQL)
        cadsen = bd.ler("CADSEN")
        bd_completo = cadsen[(cadsen["PLACA"] == planilhao["Placa"][linha]) &
                             (cadsen["DTA_EXEC"] == datetime.now().strftime('%Y%m%d'))]

        if len(bd_completo)==0:
            # Equivale ao INSERT INTO CADSEN (...) VALUES (...) do MySQL
            bd.inserir("CADSEN", {
                "CNPJ_EMP": planilhao["CNPJ"][linha],
                "UF": planilhao["UF"][linha],
                "CNPJ_PROP": planilhao["CNPJ_PROP"][linha],
                "PLACA": planilhao["Placa"][linha],
                "TIPO": planilhao["Tipo"][linha],
                "MODELO": planilhao["Modelo"][linha],
                "ANO_FAB": planilhao["Ano Fabricação"][linha],
                "ANO": planilhao["Ano"][linha],
                "CARROCERIA": planilhao["Carroceria"][linha],
                "CHASSI": planilhao["Chassi"][linha],
                "RENAVAM": planilhao["Renavam"][linha],
                "GRAVAME": planilhao["Gravame"][linha],
                "GRAVAME_PENDENTE": planilhao["Gravame Pendente"][linha],
                "RESTRICAO_ADM": planilhao["Restricao Adm"][linha],
                "RENAJUD": planilhao["RENAJUD"][linha],
                "PROCESSO": planilhao["Processo"][linha],
                "TIPO_RESTRICAO": planilhao["Tipo Restricao"][linha],
                "TRIBUNAL": planilhao["Tribunal"][linha],
                "ORGAO": planilhao["Orgao"][linha],
                "TOTAL_PROCESSOS": planilhao["Total de Processos"][linha],
                "COD_FIPE": '' if pd.isna(planilhao["Tabela FIPE"][linha]) else planilhao["Tabela FIPE"][linha],
                "INFO_UF_FIPE": '' if pd.isna(planilhao["INFO_UF_FIPE"][linha]) else planilhao["INFO_UF_FIPE"][linha],
                "DEBITO_DETRAN": planilhao["Debito Detran"][linha],
                "LICENCIAMENTO": planilhao["Licenciamento"][linha],
                "MULTA": planilhao["Multa"][linha],
                "IPVA": planilhao["IPVA"][linha],
                "IPVA_AL_ANT": planilhao["IPVA Ant"][linha],
                "CUSTO_API": planilhao["Custo"][linha],
                "DTA_EXEC": planilhao["Data execucao"][linha],
                "TABELA_FIPE": valor,
                "COMBUSTIVEL": combustivel,
                "MESREFERENCIA": mesReferencia
            }, chave=["PLACA", "DTA_EXEC"])


    # (na produção: con.close())

