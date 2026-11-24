# Esse script tem como principal função acessar os detrans de cada estado mencionado aqui a partir de um dataframe.
# Vale salientar que em alguns estados não foram feitos testes, então podem precisar de manutenção ou podem funcionar até certo tempo

import asyncio
from pydoll.browser.chrome import Chrome
from pydoll.constants import By as Byp
from pydoll.browser.options import Options as Optionsp
import pyautogui as py
from selenium import webdriver
import time
import pandas as pd
import re
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import openpyxl
import json
import requests
import pytesseract as pt
from PIL import Image
import subprocess
from io import BytesIO
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from AesEverywhere import aes256
import armazenamento as bd
from config import obter_credencial, RSCRIPT_PATH, TESSERACT_CMD, CNPJ_MA_PLACAS_PE, CNPJ_PB_PLACAS_PE


# Para funcionamento total, precisa instalar o tesseract na máquina
try:
    pt.pytesseract.tesseract_cmd = TESSERACT_CMD  # Ajuste no .env conforme o local de instalação
except:
    print("Não foi possível identificar o Tesseract. Verificar o caminho.")
    
# Caminho para o Rscript e o script R, necessário para Detran PI, ES e MS
# Nesses detrans citados, é imprescindível que o R esteja instalado na máquina juntamente com os pacotes necessários. 
# Foi constatado que por ele se torna mais "rápido" a detecção de captcha de texto em alguns casos.

script_dir = os.path.dirname(os.path.abspath(__name__))

rscript_path = RSCRIPT_PATH  # caminho do Rscript (vem de obter_credencial(), em config.py)
r_file_path = os.path.join(script_dir, "image2text.R")

# Acima deste número de placas, PE deixa de usar a API paga (debito_PE, com certificado) e passa
# para o debito_PE_free, que raspa o site com navegador + pyautogui, em blocos de 25 com pausa de
# 60s. O caminho gratuito é bem mais lento e exige sessão de desktop ativa e desbloqueada, então
# só compensa em lote grande.
LIMITE_PLACAS_PE_API = 500

# caminho_extensao=r'<pasta da extensão do Chrome>'


veiculos=pd.DataFrame()
nao_encontrado=pd.DataFrame()

# Lê o dataframe e o valor do loop em qual se encontra (esse ultimo, de Transformer.py, para estados que precisam de certificados, caso continuem a pegar)
async def veic_detran(dados,cert,cursor,senha,loop):
    placas = dados
    veiculos = pd.DataFrame()

    # print(all(placas['UF']=='PE'))

    # PE tem uma condição especial por depender de certificados pra acessar o detran. Caso tenha mais algum estado assim, adicionar do mesmo jeito
    # debito_PE vai receber e retornar um dataframe em vez de um valor único, caso todas as linhas forem do mesmo estado.
    if all(placas['UF']=='PE') and len(placas) < LIMITE_PLACAS_PE_API:
        # dados_pe = placas
        # veiculos = await debito_PE(dados_pe,loop)
        
        veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant', 'Custo','Gravame Pendente'])
        print("Certificado a ser usado: ", cert)

        with ThreadPoolExecutor(max_workers=20) as executor:
            # Enviar todas as tarefas para execução
            futures = {executor.submit(debito_PE, re.sub(r' ', '', placas['Placa'][linha]), cert, senha): linha for linha in range(len(placas))}
            
            for future in as_completed(futures):
                # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                veiculos.loc[futures[future],"Multa"] = future.result()[2]
                veiculos.loc[futures[future],"IPVA"] = future.result()[3]
                veiculos.loc[futures[future],"IPVA Ant"] = ''
                veiculos.loc[futures[future],"Custo"] = future.result()[4]
                veiculos.loc[futures[future],"Gravame Pendente"] = future.result()[5]

    elif all(placas['UF']=='PE') and len(placas) >= LIMITE_PLACAS_PE_API:
        # dados_pe = placas
        # veiculos = await debito_PE_free(dados_pe,loop)
        veiculos = []
    
        # Divide em blocos de n linhas
        n = 25
        for i in range(0, len(placas), n):
            dados_pe = placas.iloc[i:i+n]
            resultado = await debito_PE_free(dados_pe, loop)
            veiculos.append(resultado)
            time.sleep(60)
        
        # Junta todos os blocos em um único DataFrame, mantendo a ordem
        veiculos = pd.concat(veiculos, ignore_index=True)
        
    elif all(placas['UF']=='AL'):
        # Cria um DataFrame veiculos vazio com 6 colunas e o mesmo número de linhas que placas
        veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant', 'Custo','Gravame Pendente'])
        
        with ThreadPoolExecutor(max_workers=40) as executor:
            # Enviar todas as tarefas para execução
            futures = {executor.submit(debito_AL, re.sub(r' ', '', placas['Placa'][linha]), re.sub(r' ', '', placas['Renavam'][linha])): linha for linha in range(len(placas))}
            
            for future in as_completed(futures):
                # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                veiculos.loc[futures[future],"Multa"] = future.result()[2]
                veiculos.loc[futures[future],"IPVA"] = future.result()[3]
                veiculos.loc[futures[future],"IPVA Ant"] = ''
                veiculos.loc[futures[future],"Custo"] = future.result()[4]
                veiculos.loc[futures[future],"Gravame Pendente"] = ''

        # veiculos = await debito_AL_AT(placas, veiculos, cursor)
        
        
    elif all(placas['UF']=='MA'):
            # Cria um DataFrame veiculos vazio com 4 colunas e o mesmo número de linhas que placas
            veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant','Custo','Gravame Pendente'])
        
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Enviar todas as tarefas para execução
                futures = {executor.submit(debito_MA, re.sub(r' ', '', placas['Placa'][linha]), re.sub(r' ', '', placas['Renavam'][linha])): linha for linha in range(len(placas))}
                
                for future in as_completed(futures):
                    # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                    veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                    veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                    veiculos.loc[futures[future],"Multa"] = future.result()[2]
                    veiculos.loc[futures[future],"IPVA"] = future.result()[3]
                    veiculos.loc[futures[future],"IPVA Ant"] = ''
                    veiculos.loc[futures[future],"Custo"] = future.result()[4]
                    veiculos.loc[futures[future],"Gravame Pendente"] = ''
    
    elif all(placas['UF']=='CE'):
            # Cria um DataFrame veiculos vazio com 4 colunas e o mesmo número de linhas que placas
            veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant','Custo','Gravame Pendente'])
        
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Enviar todas as tarefas para execução
                futures = {executor.submit(debito_CE_pay, re.sub(r' ', '', placas['Placa'][linha]), re.sub(r' ', '', placas['Renavam'][linha])): linha for linha in range(len(placas))}
                
                for future in as_completed(futures):
                    # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                    veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                    veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                    veiculos.loc[futures[future],"Multa"] = future.result()[2]
                    veiculos.loc[futures[future],"IPVA"] = ''
                    veiculos.loc[futures[future],"IPVA Ant"] = ''
                    veiculos.loc[futures[future],"Custo"] = future.result()[3]
                    veiculos.loc[futures[future],"Gravame Pendente"] = ''
    

    elif all(placas['UF']=='RJ'):
        # Cria um DataFrame veiculos vazio com 6 colunas e o mesmo número de linhas que placas
        veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant', 'Custo','Gravame Pendente'])
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Enviar todas as tarefas para execução
            futures = {executor.submit(debito_RJ, re.sub(r' ', '', placas['Renavam'][linha]) ,re.sub(r' ', '', placas['CNPJ'][linha])): linha for linha in range(len(placas))}
            
            for future in as_completed(futures):
                # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                veiculos.loc[futures[future],"Multa"] = future.result()[2]
                veiculos.loc[futures[future],"Custo"] = future.result()[3]
                veiculos.loc[futures[future],"Gravame Pendente"] = ''

        # Tenta rodar o debito_RJ_IPVA
        try:
            veiculos = debito_RJ_IPVA(placas, veiculos)
        except Exception as e:
            print("Erro ao rodar debito_RJ_IPVA:", e)
            # Se der erro, preenche colunas IPVA e IPVA Ant com 0
            veiculos["IPVA"] = 0
            veiculos["IPVA Ant"] = 0
    
    elif all(placas['UF']=='RN'):
            # Cria um DataFrame veiculos vazio com 4 colunas e o mesmo número de linhas que placas
            veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant','Custo','Gravame Pendente'])
        
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Enviar todas as tarefas para execução
                futures = {executor.submit(debito_RN, re.sub(r' ', '', placas['Placa'][linha]), re.sub(r' ', '', placas['Renavam'][linha]), re.sub(r' ', '', placas['CNPJ'][linha])): linha for linha in range(len(placas))}
                
                for future in as_completed(futures):
                    # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                    veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                    veiculos.loc[futures[future],"Licenciamento"] = ''
                    veiculos.loc[futures[future],"Multa"] = future.result()[1]
                    veiculos.loc[futures[future],"IPVA"] = future.result()[2]
                    veiculos.loc[futures[future],"IPVA Ant"] = ''
                    veiculos.loc[futures[future],"Custo"] = future.result()[3]
                    veiculos.loc[futures[future],"Gravame Pendente"] = ''
    
    elif all(placas['UF']=='PI'):
            # Cria um DataFrame veiculos vazio com 4 colunas e o mesmo número de linhas que placas
            veiculos = pd.DataFrame('', index=placas.index, columns=['Debito Detran', 'Licenciamento', 'Multa', 'IPVA', 'IPVA Ant','Custo','Gravame Pendente'])
        
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Enviar todas as tarefas para execução
                futures = {executor.submit(debito_PI, re.sub(r' ', '', placas['Placa'][linha]), re.sub(r' ', '', placas['Renavam'][linha])): linha for linha in range(len(placas))}
                
                for future in as_completed(futures):
                    # print(f"Linha: {futures[future]}, com valor {future.result()}.")
                    veiculos.loc[futures[future],"Debito Detran"] = future.result()[0]
                    veiculos.loc[futures[future],"Licenciamento"] = future.result()[1]
                    veiculos.loc[futures[future],"Multa"] = future.result()[2]
                    veiculos.loc[futures[future],"IPVA"] = ''
                    veiculos.loc[futures[future],"IPVA Ant"] = ''
                    veiculos.loc[futures[future],"Custo"] = future.result()[3]
                    veiculos.loc[futures[future],"Gravame Pendente"] = ''
                    
    
    else:
        # O loop irá verificar todas as placas, renavam, estado e cnpj dos veículos
        # Caso queira colocar o estado com base no valor fipe, trocar UF por INFO_UF_FIPE.
        for linha in range(len(placas)):
            print('veiculo ',linha+1,' de ',len(placas))
            placa = re.sub(r' ', '', placas['Placa'][linha])
            renavam = re.sub(r' ', '', placas['Renavam'][linha])
            uf = re.sub(r' ', '', placas['UF'][linha])
            cnpj = re.sub(r'[^0-9]', '', placas['CNPJ'][linha])
            rodou = 0
            tentativas = 0
            max_tentativas = 5

            # Será feita 5 tentativas caso dê erro em algumas das chamadas. Caso não consiga mesmo após atingir o limite, deverá retornar branco
            while rodou == 0 and tentativas < max_tentativas:
                try:
                    if uf=='AL':
                        valores_debito = debito_AL(placa,renavam)
                        debito = valores_debito[0]
                        valor_lic = valores_debito[1]
                        valor_multa = valores_debito[2]
                        ipva = valores_debito[3]
                        custo_api = valores_debito[4]
                        gravame_pen = ''

                        try:
                            dados_al = placas.iloc[[linha]].reset_index(drop=True)
                            ipva_df = pd.DataFrame([[0.0, 0.0, 0.0]], columns=['Debito Detran', 'IPVA', 'IPVA Ant'])

                            valor_ipva = await debito_AL_AT(placas = dados_al, veiculos = ipva_df, cursor = cursor)
                            ipva_ant = valor_ipva['IPVA Ant'].iloc[0]
                        except:
                            ipva_ant = 0
                        
                        # print(f"Ipva de anos anteriores para a placa {placa}: {ipva_ant}")
                        if ipva != '' and ipva != 'OE':
                            ipva = valores_debito[3] + ipva_ant
                            debito = debito + ipva_ant

                    elif uf=='CE':
                        valores_debito = debito_CE(placa,renavam)
                        debito = valores_debito[0]
                        valor_lic = valores_debito[1]
                        valor_multa = valores_debito[2]
                        ipva = valores_debito[3]
                        ipva_ant = valores_debito[4]
                        custo_api = ''
                        gravame_pen = ''

                    elif uf=='ES':
                        debito = debito_ES(placa,renavam, rscript_path, r_file_path)
                    
                    elif uf=='MA':
                        valores_debito = debito_MA(placa,renavam)
                        debito = valores_debito[0]
                        valor_lic = valores_debito[1]
                        valor_multa = valores_debito[2]
                        ipva = valores_debito[3]
                        ipva_ant = ''
                        custo_api = valores_debito[4]
                        gravame_pen = ''

                        if debito == 'OE' and cnpj == CNPJ_MA_PLACAS_PE:
                            dados_pe = placas.iloc[[linha]]
                            valor_pe = await debito_PE_free(dados_pe,loop)
                            debito = valor_pe['Debito Detran'][0]
                            valor_lic = valor_pe['Licenciamento'][0]
                            valor_multa = valor_pe['Multa'][0]
                            ipva = valor_pe['IPVA'][0]
                            ipva_ant = ''
                            gravame_pen = valor_pe['Gravame Pendente'][0]
                            custo_api = ''
                    
                    
                    
                    elif uf=='MG':
                        debito = await debito_MG(renavam)
                    
                    # elif uf=='MS':
                    #     debito = await debito_MS(placa,renavam, rscript_path, r_file_path) # Não foram feitos testes

                    # elif uf=='MT':
                    #     debito = await debito_MT(placa,renavam,cnpj) # Não foram feitos testes

                    ## FUNCIONAL, POREM O CAPTCHA É MUITO DIFÍCIL DE RECONHECER
                    # elif uf=='PA':
                    #     debito = debito_PA(placa, renavam)

                    elif uf=='PB':
                        valor_pb = debito_PB(placa, renavam)
                        debito = valor_pb[0]
                        valor_lic = valor_pb[3]
                        valor_multa = valor_pb[1]
                        ipva = valor_pb[2]
                        ipva_ant = ''
                        custo_api = ''
                        gravame_pen = ''
                        if debito == 'OE' and cnpj == CNPJ_PB_PLACAS_PE:
                            dados_pe = placas.iloc[[linha]]
                            valor_pe = await debito_PE_free(dados_pe,loop)
                            debito = valor_pe['Debito Detran'][0]
                            valor_lic = valor_pe['Licenciamento'][0]
                            valor_multa = valor_pe['Multa'][0]
                            ipva = valor_pe['IPVA'][0]
                            ipva_ant = ''
                            gravame_pen = valor_pe['Gravame Pendente'][0]
                            custo_api = ''
                    

                    # Nesse caso, debito_Pe tá recebendo uma linha como dataframe pra tratar de um único valor
                    elif uf=='PE':
                        # valor_pe = debito_PE(placa, cert)
                        # debito = valor_pe[0]
                        # valor_lic = valor_pe[1]
                        # valor_multa = valor_pe[2]
                        # ipva = valor_pe[3]
                        # ipva_ant = ''
                        # custo_api = valor_pe[4]
                        # gravame_pen = valor_pe[5]
                        dados_pe = placas.iloc[[linha]]
                        valor_pe = await debito_PE_free(dados_pe,loop)
                        debito = valor_pe['Debito Detran'][0]
                        valor_lic = valor_pe['Licenciamento'][0]
                        valor_multa = valor_pe['Multa'][0]
                        ipva = valor_pe['IPVA'][0]
                        ipva_ant = ''
                        gravame_pen = valor_pe['Gravame Pendente'][0]
                        custo_api = ''
                
                    
                    # elif uf=='PI':
                    #     debito = debito_PI(placa,renavam, rscript_path, r_file_path) # Não foram feitos testes

                    elif uf=='RJ':
                        valor_rj = debito_RJ(renavam, cnpj)
                        debito = valor_rj[0]
                        valor_lic = valor_rj[1]
                        valor_multa = valor_rj[2]
                        ipva = valor_rj[3]
                        ipva_ant = valor_rj[4]
                        custo_api = valor_rj[5]
                        gravame_pen = ''

                    elif uf=='RN':
                        valor_rn = debito_RN(placa,renavam,cnpj)
                        debito = valor_rn[0]
                        valor_lic = ''
                        valor_multa = valor_rn[1]
                        ipva = valor_rn[2]
                        ipva_ant = ''
                        custo_api = valor_rn[3]
                        gravame_pen = ''

                    
                    # elif uf=='RR':
                    #     debito = debito_RR(placa, renavam) # Não foram feitos testes

                    elif uf=='SP':
                        valor_sp = await debito_SP(placa, renavam)
                        debito = valor_sp[0]
                        valor_lic = ''
                        valor_multa = valor_sp[1]
                        ipva = ''
                        ipva_ant = ''

                    else:
                        debito = ''
                        valor_lic = ''
                        valor_multa = ''
                        ipva = ''
                        ipva_ant = ''
                        custo_api = ''
                        gravame_pen = ''
                    
                    dados_veic = pd.DataFrame({
                        'Debito Detran': [debito],
                        'Licenciamento': [valor_lic],
                        'Multa': [valor_multa],
                        'IPVA':[ipva],
                        'IPVA Ant': [ipva_ant],
                        'Custo': [custo_api],
                        'Gravame Pendente': [gravame_pen]
                    })
                    veiculos=veiculos._append(dados_veic)
                    rodou = 1  # Sucesso!
                except Exception as e:
                    print(f"Erro na tentativa {tentativas + 1}: {e}")
                    tentativas += 1
                    await asyncio.sleep(2)
            
            if rodou == 0:
                print(f"Falha ao processar placa {placa} após {max_tentativas} tentativas.")
                dados_veic = pd.DataFrame({
                        # 'Chassi': '0',
                        'Debito Detran': [''],
                        'Licenciamento': [''],
                        'Multa': [''],
                        'IPVA': [''],
                        'IPVA Ant': [''],
                        'Custo': [''],
                        'Gravame Pendente': ['']
                    })
                veiculos=veiculos._append(dados_veic)
            # print(veiculos)
    
    time.sleep(3)
    veiculos = veiculos.reset_index(drop=True)
    # print(veiculos)
    # Deverá retornar um dataframe com os dados do débito do Detran
    return veiculos


def debito_MA(placa,renavam):  
    
    # opcao_ipva = '//*[@id="form1:codigoTipoDare"]/option[2]'
    # opcao_imposto = '//*[@id="form1:codigoReceita"]/option[2]'
    # texto_ano = '//*[@id="form1:dadosInscricao"]/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[12]/td[1]'

    # Em caso de teste, deixar as próximas sete linhas como comentário
    url = 'https://api.infosimples.com/api/v2/consultas/detran/ma/licenciamento'
    args = {
    "placa":   placa,
    "renavam": renavam,
    "token":   obter_credencial("INFOSIMPLES_TOKEN"),
    "timeout": 300
    }

    # # Deixar as próximas duas linhas como comentários, em caso de não for teste
    # arquivo_json = open(r"arquivo_ma_teste_ipva.json")
    # response_json = json.load(arquivo_json)

    tentativas = 0
    debito_detran = ''
    licenciamento = ''
    multa = ''
    ipva = ''
    custo_api = 0

    while tentativas < 5:
        print(f'Tentativa {tentativas + 1} para a placa {placa}')
        tentativas += 1

        try:
            response = requests.post(url, args)
            response_json = response.json()
            response.close()
        except Exception as e:
            print(f"Erro ao consultar API ou decodificar JSON: {e}")
            continue

        if response_json.get('code') == 200:
            try:
                debitos = pd.DataFrame(response_json['data'][0]['debitos'])
                if len(debitos) > 0:
                    debito_detran = round(sum(debitos['normalizado_valor_atual']), 2)
                    try:
                        licenciamento = round(sum(debitos[debitos['descricao'].str.contains('LICENCIAMENTO', na=False)]['normalizado_valor_atual']), 2)
                    except:
                        licenciamento = 0
                    multa = round(float(debito_detran) - licenciamento, 2)
                else:
                    debito_detran = 0
                    licenciamento = 0
                    multa = 0

                valor_ipva = pd.DataFrame(response_json['data'][0]['ipva'])
                ipva = sum(valor_ipva['normalizado_saldo_devedor']) if len(valor_ipva) > 0 else 0

                outros_debitos = pd.DataFrame(response_json['data'][0]['outros_debitos_sefaz'])
                outros = sum(outros_debitos['normalizado_saldo_devedor']) if len(outros_debitos) > 0 else 0

                debito_detran = float(debito_detran) + ipva + outros

                custo_api = response_json['header']['price']
            except Exception as e:
                print(f"Erro ao processar dados JSON: {e}")
                continue

            break  # sucesso, sai do while

        elif response_json.get('code') == 608:
            debito_detran = licenciamento = multa = ipva = 'OE'
            try:
                custo_api = response_json['header']['price']
            except:
                custo_api = 'OE'
            break

        elif response_json.get('code') in (606, 607, 611, 612, 620):
            debito_detran = licenciamento = multa = ipva = 0
            try:
                custo_api = response_json['header']['price']
            except:
                custo_api = 0
            break

        else:
            try:
                custo_api = response_json['header']['price']
            except:
                custo_api = 0
            debito_detran = ''
            licenciamento = ''
            multa = ''
            ipva = ''
            # continua tentando

    return debito_detran, licenciamento, multa, ipva, custo_api

def debito_CE(placa,renavam):
    # Configuração do WebDriver
    # options = webdriver.ChromeOptions()
    # options.add_argument(f'load-extension={caminho_extensao}')
    opt = Options()
    opt.add_argument('--headless')
    driver = webdriver.Chrome()

    driver.get('https://sistemas.detran.ce.gov.br/central')
    time.sleep(3)
    driver.find_element('xpath','//*[@id="veiculo"]/div/div/div[1]/div/div[2]/div/a[9]').click()
    time.sleep(1)
    driver.find_element('id','veiculo_placa').send_keys(placa)
    driver.find_element('id','veiculo_renavam_chassi').send_keys(renavam)
    driver.find_element('xpath','//*[@id="submit-veiculo"]').click()
    time.sleep(3)
    try:
        # Veículos de outro estado não possuem o botão de emitir ipva
        botao_ipva = driver.find_element('xpath','/html/body/div[4]/div[1]/div/div[3]/div[2]/div/div[6]') # campo ipva
        try: 

            # Vai interagir com o botao de mostrar o valor do licenciamento, caso nao tenha o botao, vai ser 0
            driver.find_element('xpath','/html/body/div[4]/div[1]/div/div[3]/div[2]/div/div[5]').click()
            time.sleep(3)
            try:
                total = re.sub(r',', '.', re.sub(r'\.', '', re.findall(r'R\$\s+([\d.,]+)', driver.find_element('id','total').text)[0]))
            
                tabela = driver.find_element(By.ID,'emissao-multas').text.strip().split('\n')
                valores = re.findall(r'R\$\s+([\d.,]+)', driver.find_element(By.ID,'emissao-multas').text)[1::2]
            except:
                total = 0

            try:
                licenciamento = re.sub(r',', '.', re.sub(r'\.', '', [re.findall(r'R\$\s+([\d.,]+)', lic)[1] for lic in tabela if 'Licenciamento' in lic][0]))
            except:
                licenciamento = 0
            
        
            try:
                driver.refresh()
                time.sleep(2) 
                botao_multa = driver.find_element(By.CLASS_NAME,'multas').click()
                time.sleep(3)
                valores_multas = re.findall(r'R\$\s+([\d.,]+)', driver.find_element(By.ID,'extrato_multas').text)[1::2]
                multa = sum(float(valor.replace('.','').replace(',','.')) for valor in valores_multas)

                try:
                    # multa_sobrando = re.sub(r',', '.', re.sub(r'\.', '', [valor for valor in valores_multas if valor not in valores][0]))
                    multa_sobrando = sum([float(re.sub(r',', '.', re.sub(r'\.', '', valor))) for valor in valores_multas if valor not in valores])
                except:
                    multa_sobrando = 0
                
            except:
                multa = 0
                multa_sobrando = 0
            
            if total == 0 and multa != 0:
                debito_detran = float(total) + float(multa)
            else:
                debito_detran = float(total) + float(multa_sobrando)

            try:
                driver.get('https://ipva.sefaz.ce.gov.br/#/impostos/emitir-dae')
                time.sleep(6)
                driver.find_element('id','mat-input-1').send_keys(placa)
                driver.find_element('id','mat-input-2').send_keys(renavam)
                driver.find_element('xpath','//*[@id="sidenav-comp"]/mat-sidenav-content/main/app-emitir-dae/div/div/mat-card/div/form/div[1]/div[4]/button[1]').click()
                time.sleep(4)
                tabela_ipva = driver.find_element('xpath','//table').text
                
                ipvas_aberto = re.findall(r'R\$ ([\d\.]+,\d{2})\s+Em aberto',tabela_ipva)
                
                ipva = sum([float(v.replace('.', '').replace(',', '.')) for v in ipvas_aberto])
                
                try:
                    driver.find_element('id','md-tab-label-0-1').click()
                    time.sleep(1)
                    tabela_ipva_ant = driver.find_element('xpath','//table').text
                    ipvas_aberto_ant = re.findall(r'R\$ ([\d\.]+,\d{2})\s+Em aberto',tabela_ipva_ant)
                    
                    ipva_ant = sum([float(v.replace('.', '').replace(',', '.')) for v in ipvas_aberto_ant])
                except:
                    ipva_ant = 0
            except:
                ipva = ''
                ipva_ant = ''
            if ipva != '':
                ipva = ipva + ipva_ant
                debito_detran = debito_detran + ipva
            
        except:
            debito_detran=''
            licenciamento=''
            multa=''
            ipva=''
            ipva_ant=''

    except:
        debito_detran = 'OE'
        licenciamento='OE'
        multa='OE'
        ipva='OE'
        ipva_ant='OE'
    time.sleep(60)

    driver.quit()

    return debito_detran, licenciamento, multa, ipva, ipva_ant

def debito_AL(placa, renavam):
    try:
        url = 'https://api.infosimples.com/api/v2/consultas/detran/al/veiculo'
        url_ipva = 'https://api.infosimples.com/api/v2/consultas/sefaz/al/ipva'
        args = {
            "placa":   placa,
            "renavam": renavam,
            "token":   obter_credencial("INFOSIMPLES_TOKEN"),
            "timeout": 300
        }

        print(f'Verificando dados para {placa}; ')
        response_AL = requests.post(url, args)

        try:
            response_json = response_AL.json()
        except ValueError:
            print("⚠️ Erro ao decodificar JSON da resposta do DETRAN.")
            # print("Conteúdo da resposta:", response_AL.text)
            if response_AL:
                response_AL.close()
            return '', '', '', ''
        response_AL.close()
        
        # arquivo_json = open(r"arquivo_al_semdado.json")
        # response_json = json.load(arquivo_json)

        custo_api = 0
        custo_api_ipva = 0

        if response_json.get('code') == 200:
            try:
                data = response_json.get('data', [])
                if data:
                    debitos = data[0].get('debitos', {})
                    match = re.findall(r'R\$\s+([\d.,]+)', debitos.get('total_debito', ''))
                    if match:
                        debito_detran = re.sub(r',', '.', re.sub(r'\.', '', match[0]))
                        multa = response_json['data'][0]['debitos']['debitos_eventuais']['normalizado_infracoes']
                        licenciamento = sum([
                            valor_lic['normalizado_licenciamento_vistoria']
                            for valor_lic in response_json['data'][0]['debitos']['debitos_anuais']
                            if 'normalizado_licenciamento_vistoria' in valor_lic
                        ])
                        custo_api = response_json['header']['price']
                    else:
                        debito_detran = 0
                        multa = 0
                        licenciamento = 0
                        custo_api = 0
                else:
                    debito_detran = 0
                    multa = 0
                    licenciamento = 0
                    custo_api = 0
                    
            except Exception as e:
                print("⚠️ Erro ao extrair dados do JSON DETRAN")
                debito_detran = 0
                multa = 0
                licenciamento = 0
                try:
                    custo_api = response_json['header']['price']
                except:
                    custo_api = 0

            # arquivo_json_ipva = open(r"arquivo_al_ipva.json")
            # response_json_ipva = json.load(arquivo_json_ipva)
            
            ipva = 0
            custo_api_ipva = 0
            
            # contador = 1
            # while contador <= 1:
                
            #     print(f"Tentativa {contador} de 5 para IPVA atual de {placa}")
            #     try:
            #         response_AL_ipva = requests.post(url_ipva, args)
                    
            #         try:
            #             response_json_ipva = response_AL_ipva.json()
            #         except ValueError:
            #             print("⚠️ Erro ao decodificar JSON do IPVA:")
            #             # print("Resposta:", response_AL_ipva.text)
            #             response_AL_ipva.close()
            #             contador += 1
            #             time.sleep(60)
            #             continue  # tenta novamente
                    
            #         response_AL_ipva.close()

            #         if response_json_ipva.get('code') == 200:
            #             try:
            #                 data_list = response_json_ipva.get('data', [])
            #                 if data_list and data_list[0].get('parcelamento'):
            #                     parcelamento_list = data_list[0]['parcelamento']
            #                     if parcelamento_list:
            #                         ipva = parcelamento_list[0].get('normalizado_valor_total', 0)
            #                 custo_api_ipva = response_json_ipva.get('header', {}).get('price', 0)
            #             except Exception as e:
            #                 print(f"⚠️ Erro ao extrair IPVA: {e}")
            #                 ipva = 0
            #                 custo_api_ipva = 0
            #             break
            #         elif response_json_ipva.get('code') == 612:
            #             ipva = 0
            #             custo_api_ipva = 0
            #             break
            #         elif response_json_ipva.get('code') == 620:
            #             ipva = ''
            #             custo_api_ipva = 0
            #             break
            #         else:
            #             contador += 1
            #             # time.sleep(60)
            #     except Exception as e:
            #         print(f"⚠️ Tentativa {contador} falhou: {e}")
            #         contador += 1
            #         # time.sleep(60)
            # else:
            #     ipva = ''
            #     custo_api_ipva = 0

            # try:
            #     debito_detran = float(debito_detran) + float(ipva)
            # except:
            #     pass

        elif response_json.get('code') == 612:
            debito_detran = 'OE'
            multa = 'OE'
            licenciamento = 'OE'
            ipva = 'OE'
            custo_api_ipva = 0
        else:
            debito_detran = ''
            multa = ''
            licenciamento = ''
            ipva = ''
            custo_api_ipva = 0
        
        try:
            custo_api = float(custo_api) + float(custo_api_ipva)
        except:
            pass
    except:
        debito_detran = 0
        licenciamento = 0
        multa = 0
        ipva = 0
        custo_api = 0

    return debito_detran, licenciamento, multa, ipva, custo_api

def debito_PI(placa,renavam):
    
    licenciamento = 0
    multas = 0
    debito_detran = 0
    custo_api = 0

    try:
    # arquivo_json = open(r"debito_PI.json")
    # response_json = json.load(arquivo_json)
        
        url = 'https://api.infosimples.com/api/v2/consultas/detran/pi/veiculo'
        args = {
            "placa":   placa,
            "renavam": renavam,
            "token":   obter_credencial("INFOSIMPLES_TOKEN"),
            "timeout": 300
        }

        print("tentativa para placa:", placa)
        response = requests.post(url, args)
        response_json = response.json()
        
        if response_json['code'] == 200 and response_json.get('data'):
            
            try:
                licenciamento = sum(
                d['normalizado_total']
                for d in response_json['data'][0]['debitos']
                if any(item['debito'] == 'Taxa de Licenciamento' for item in d['lista']))
            except:
                licenciamento = 0
        
            try:
                multas = sum(
                inf['normalizado_valor_total']
                for inf in response_json['data'][0]['infracoes']
                if 'normalizado_valor_total' in inf)
            except:
                multas = 0
            
            debito_detran = round(float(licenciamento) + float(multas),2)
            
        try:
            custo_api = round(float(response_json['header']['price']),2)
        except:
            custo_api = 0
        
            
    except Exception as e:
        print(f"Erro ao processar JSON: {e}")

    return debito_detran, licenciamento, multas, custo_api

def debito_RJ(renavam,cnpj):
    
    url_multa = 'https://api.infosimples.com/api/v2/consultas/detran/rj/multas-guias'
    args = {
    "renavam": renavam,
    "cnpj":    cnpj,
    "token":   obter_credencial("INFOSIMPLES_TOKEN"),
    "timeout": 300
    }

    # arquivo_json = open(r"arquivo_rj_multa.json")
    # response_RJ_multa_json = json.load(arquivo_json)

    tentativa = 1
    multa = 0
    custo_api_multa = 0
    while tentativa <= 5:
        print(f'Tentativa {tentativa} para multa do renavam {renavam} e empresa {cnpj} ')
        try:

            response = requests.post(url_multa, args)
            response_RJ_multa_json = response.json()
        except ValueError:
            print("⚠️ Erro ao decodificar JSON da resposta do DETRAN.")
            # print("Conteúdo da resposta:", response_AL.text)
            if response:
                response.close()
            multa = 0
            custo_api_multa = 0
            tentativa += 1
            continue
            
        response.close()

        if response_RJ_multa_json.get('code') == 200:
            try:
                multa = sum([item['normalizado_valor'] for item in response_RJ_multa_json['data']])
                custo_api_multa = response_RJ_multa_json['header']['price']
            except:
                multa = 0
                custo_api_multa = 0
            break

        elif response_RJ_multa_json.get('code') in (600, 605, 615):
            tentativa += 1
            time.sleep(60)

        else:
            try:
                custo_api_multa = response_RJ_multa_json['header']['price']
                break
            except:
                custo_api_multa = 0
                break
        
    # arquivo_json = open(r"arquivo_rj_lic.json")
    # response_RJ_lic_json = json.load(arquivo_json)

    url_lic = 'https://api.infosimples.com/api/v2/consultas/detran/rj/grt'

    licenciamento = 0
    custo_api_lic = 0

    tentativa = 1
    while tentativa <= 5:
        print(f'Tentativa {tentativa} para licenciamento do renavam {renavam} e empresa {cnpj}')
        try:

            response = requests.post(url_lic, args)
            response_RJ_lic_json = response.json()
        except ValueError:
            print("⚠️ Erro ao decodificar JSON da resposta do DETRAN.")
            # print("Conteúdo da resposta:", response_AL.text)
            if response:
                response.close()
            licenciamento = 0
            custo_api_lic = 0
            tentativa += 1
            continue
        
        response.close()
        if response_RJ_lic_json.get('code')==200:
            try:
                licenciamento = sum([venc['cotas'][0]['normalizado_total'] for venc in response_RJ_lic_json['data'][0]['exercicios']])
                custo_api_lic = response_RJ_lic_json['header']['price']
            except:
                licenciamento = 0
                custo_api_lic = 0
            break

        elif response_RJ_lic_json.get('code')  in (600, 605, 615):
            tentativa += 1
            time.sleep(60)

        else:
            try:
                custo_api_lic = response_RJ_lic_json['header']['price']
            except:
                custo_api_lic = 0
            break
        
    custo_api = round(float(custo_api_lic)+float(custo_api_multa),2)

    try:
        debito = licenciamento + multa
    except:
        debito = 0


    return debito, licenciamento, multa, custo_api

def debito_ES(placa, renavam, rscript_path, r_file_path):
    
    opt = Options()
    opt.add_argument('--headless')

    driver = webdriver.Chrome(options=opt)
    driver.get('https://publicodetran.es.gov.br/ConsultaVeiculo/NovoConsultaVeiculoES.asp')
    driver.maximize_window()
    rodou = 0

    wait = WebDriverWait(driver, 10)
    time.sleep(5)
    driver.find_element('id','placa').send_keys(placa)

    driver.find_element('id','renavam').send_keys(renavam)

    # Vai ficar tentando o texto do captcha até pegar
    while rodou==0:
        time.sleep(1)
        imagem_captcha = driver.find_element('id','imgCaptcha')
        imagem_captcha.screenshot('captcha.png')
        
        caminho_imagem = "captcha.png"
        # caminho_imagem = 'http://taxas.detran.pi.gov.br/Captcha.jpg?height=40%3Fp=Mon%20Mar%2024%2014%3A20%3A27%20BRT%202025'
        # response = requests.get(url_imagem)
        # imagem = Image.open(BytesIO(response.content))
        
        # Caminho para o Rscript e o script R
        rscript_path = rscript_path
        
        r_file_path = r_file_path

        uf_R='ES'
        
        time.sleep(3)

        #O script R foi definido primeiro aqui porque ele acertou mais rapidamente esse tipo de captcha.
        try:
            print('Indo para o script R')
            result = subprocess.run(
                    [rscript_path, "--vanilla", r_file_path, caminho_imagem, uf_R],  # Passa como lista
                    capture_output=True,
                    text=True,
                    check=True
                )
            result.stdout
            texto = re.findall(r'[a-zA-Z0-9]+',result.stdout)[0]
            print(texto)
        
        except:
            try:
                imagem = Image.open(caminho_imagem)
                print(pt.image_to_string(imagem))
                texto = re.findall(r'[a-zA-Z0-9]+',pt.image_to_string(imagem))[0]
                print(texto)
            except:
                texto = 0

        
        time.sleep(2)
        driver.find_element('id','txtCaptcha').send_keys(texto)
        driver.find_element('id','btnSubmit').click()
        
        # Verifica sucesso ou falha
        
        try:
            # time.sleep(1)
            nenhum_debito = driver.find_element('xpath','//*[@id="div_servicos_03"]/table/tbody/tr/td').text
            if len(nenhum_debito)!=0:
                debito_detran = 0
                rodou = 1  # Sai do loop
            else:
                time.sleep(2)
                botao_debito = driver.find_element('id','span_nome_div_servicos_03').click()
                time.sleep(1)
                debito_detran = re.sub(r',','.',re.sub(r'\.','',re.findall(r'R\$ ([\d.]+,[\d]+)',driver.find_element('id','spanDUA_Integral').text)[0]))
                rodou = 1  # Sai do loop
        except:
            # Aguarda mensagem de erro (indicando falha no CAPTCHA)
            # mensagem_erro = wait.until(EC.presence_of_element_located(('xpath', '/html/body/form/div/p/span')))
            
            rodou = 0  # Repete o loop

    print(debito_detran)
    driver.quit()
    return debito_detran

async def debito_MG(renavam):

    cookie = '//*[@id="__next"]/main/div[2]/div/button[1]'
    campo_renavam = '//*[@id="outlined-basic"]'
    consulta = '//*[@id="__next"]/main/div/div/div/section/form/div/button'

    async def main():
        
        async with Chrome() as browser:
            await browser.start()
            page = await browser.get_page()

            await page.go_to('https://buscar-renavam-ipva-digital.fazenda.mg.gov.br/buscar-renavam/')
            await asyncio.sleep(5)
            
            aceita_cookie = await page.find_element(Byp.XPATH,cookie)
            await aceita_cookie.click()

            consulta_renavam = await page.find_element(Byp.XPATH,campo_renavam)
            await consulta_renavam.click()
            await consulta_renavam.send_keys(renavam)
            
            await asyncio.sleep(5)
            botao_consulta = await page.find_element(Byp.XPATH,consulta)
            await botao_consulta.click()
            await asyncio.sleep(3)

            total = await page.find_element(Byp.ID,'total-disponivel-pagamento')
            valores = await total.get_element_text()
            debito = re.sub(r',', '.', re.sub(r'\.', '', re.findall(r'R\$\s+([\d.,]+)',valores)[0]))

        return debito
    return await main()

async def debito_SP(placa, renavam):

    async def main():
        opt = Optionsp()
        opt.add_argument('--headless')

        async with Chrome() as browser:
            await browser.start()
            page = await browser.get_page()
            
            await page.go_to('https://www.ipva.fazenda.sp.gov.br/ipvanet_consulta/Consulta.aspx')

            await asyncio.sleep(3)

            campo_renavam = await page.find_element(Byp.ID,'conteudoPaginaPlaceHolder_txtRenavam')
            await campo_renavam.click()
            await campo_renavam.send_keys(renavam)

            campo_placa = await page.find_element(Byp.ID,'conteudoPaginaPlaceHolder_txtPlaca')
            await campo_placa.click()
            await campo_placa.send_keys(placa)

            botao_consulta = await page.find_element(Byp.ID, 'conteudoPaginaPlaceHolder_btn_Consultar')
            await botao_consulta.click()

            await asyncio.sleep(3)

            try:
                valores = await page.find_element(Byp.ID,'conteudoPaginaPlaceHolder_txtValorTotalDebitos')
                valor_texto = await valores.get_element_text()

                debito_detran = re.sub(r',','.',re.sub(r'\.','',re.findall(r'([\d.]+,[\d]+)',valor_texto)[0]))
                print(debito_detran)

                try:
                    valor_multa = await page.find_element(Byp.ID, 'conteudoPaginaPlaceHolder_txtVlTotalMultas')
                    multa = await valor_multa.get_element_text()
                    
                    multa = re.sub(r',','.',re.sub(r'\.','',re.findall(r'([\d.]+,[\d]+)',multa)[0]))
                except:
                    multa = 0

                
            except:
                try:
                    nao_encontrado = await page.find_element(Byp.ID,'conteudoPaginaPlaceHolder_lblErro')
                    debito_detran = 'OE'
                    multa = 'OE'
                except:
                    debito_detran = 0
                    multa = 0
            
        return debito_detran, multa
    return await main()

def debito_PA(placa, renavam):

    opt = Options()
    opt.add_argument('--headless')
    driver = webdriver.Chrome(options=opt)
    driver.get('https://www.detran.pa.gov.br/sistransito/detran-web/servicos/b/indexBLicencAnoAtual.jsf')
    time.sleep(3)

    rodou = 0

    driver.find_element('id','indexBoletoAnoAtual:placa1').send_keys(placa)

    while rodou==0:
        time.sleep(1)

        driver.find_element('id','indexBoletoAnoAtual:renavam').send_keys(renavam)

        imagem_captcha = driver.find_element('id','indexBoletoAnoAtual:captcha')
        imagem_captcha.screenshot('captcha.png')

        caminho_imagem = "captcha.png"

        # Caminho para o Rscript e o script R
        rscript_path = RSCRIPT_PATH
        
        r_file_path = os.path.join(script_dir, "image2text.R")
        
        time.sleep(3)
        try:
            print('Indo para o script R')
            result = subprocess.run(
                    [rscript_path, "--vanilla", r_file_path, caminho_imagem],  # Passa como lista
                    capture_output=True,
                    text=True,
                    check=True
                )
            result.stdout
            texto = re.findall(r'[a-zA-Z0-9]+',result.stdout)[0]
            print(texto)
        
        except:
            try:
                imagem = Image.open(caminho_imagem)
                texto = re.findall(r'[a-zA-Z0-9]+',pt.image_to_string(imagem))[0]
                print(texto)
            except:
                texto = 0

    
        time.sleep(2)
        driver.find_element('id','indexBoletoAnoAtual:senha').send_keys(texto)
        driver.find_element('id','indexBoletoAnoAtual:confirma').click()
        
        # Verifica sucesso ou falha
        
        try:
            time.sleep(1)
            driver.find_element('id','confirma').click()
            time.sleep(5)
            valores = driver.find_element('xpath','//*[@id="confirmacaoBoletoAnoAtual"]/table[1]/tbody/tr[2]/td/table[5]/tbody/tr[3]/td/span').text
            debito_detran = re.sub(r',','.',re.sub(r'\.','',re.findall(r'R\$ ([\d.]+,[\d]+)',valores)[0]))
            rodou = 1

        except:  
            try:
                texto_erro = driver.find_element('xpath','//*[@id="erroPadrao:j_idt18"]/table/tbody/tr/td/div/ul/li').text

                if 'não encontrado' in texto_erro:
                    debito_detran = 'OE'
                    rodou = 1
                else:
                    driver.find_element('xpath','//*[@id="erroPadrao:j_idt18"]/table/tbody/tr/td/table/tbody/tr[1]/td/input').click()
                    rodou = 0  # Repete o loop
            except:
                debito_detran = 0
                rodou = 1
    driver.quit()
    return(debito_detran)

async def debito_MT(placa, renavam, cnpj):

    botao_consulta = '//*[@id="formVeiculo"]/div[4]/input[2]'
    fecha_popup = '//*[@id="mtSitesPopup"]/div/div/div[1]/button'
    campo_cnpj = '/html/body/center/div/form/table/tbody/tr[3]/td[2]/input'
    botao_consulta2 = '/html/body/center/div/form/table/tbody/tr[4]/td/input'
    msg_aviso = '/html/body/center/div/table/tbody/tr/td'

    async def main():
        opt = Optionsp()
        opt.add_argument('--headless')

        async with Chrome(options=opt) as browser:
            await browser.start()
            page = await browser.get_page()

            await page.go_to('https://www.detran.mt.gov.br/')
            await asyncio.sleep(5)

            popup = await page.find_element(Byp.XPATH,fecha_popup)
            await popup.click()
            await asyncio.sleep(2)

            campo_placa = await page.find_element(Byp.ID,'input_placa')
            await campo_placa.click()
            await campo_placa.send_keys(placa)

            campo_renavam = await page.find_element(Byp.ID,'input_renavam')
            await campo_renavam.click()
            await campo_renavam.send_keys(renavam)
            await asyncio.sleep(2)

            consulta = await page.find_element(Byp.XPATH,botao_consulta)
            await consulta.click()
            await asyncio.sleep(3)

            menu_paginas = await browser.get_targets()
            pages = [target for target in menu_paginas if target['type'] == 'page']
            pagina_alvo = pages[0]['targetId']

            page = await browser.get_page_by_id(pagina_alvo)

            cnpj_texto = await page.find_element(Byp.XPATH,campo_cnpj)
            await cnpj_texto.click()
            await cnpj_texto.send_keys(cnpj)

            consulta2 = await page.find_element(Byp.XPATH,botao_consulta2)
            await consulta2.click()

            await asyncio.sleep(3)

            try:
                aviso = await page.find_element(Byp.XPATH,msg_aviso)
                debito_detran = 'OE'
            except:
                debito_detran = 0
        return debito_detran
    return await main()

def debito_PB(placa, renavam):

    opt = Options()
    # opt.add_argument('--headless')

    # Iniciar o navegador
    driver = webdriver.Chrome()

    # Navegar até a URL
    driver.get('https://wsdetran.pb.gov.br/detran-portal-servicos/servlet/easynat-app?op=S30')

    # Aguardar 5 segundos para a página carregar
    time.sleep(5)

    driver.switch_to.frame(2)

    # Encontrar e preencher o campo da placa
    campo_placa = driver.find_element('id', 'F_40')
    campo_placa.click()
    campo_placa.send_keys(placa)

    # Encontrar e preencher o campo do RENAVAM
    campo_renavam = driver.find_element('id', 'F_45')
    campo_renavam.click()
    campo_renavam.send_keys(webdriver.Keys.BACKSPACE)  # Corrigido o envio do texto completo
    campo_renavam.send_keys(renavam)  # Corrigido o envio do texto completo

    # Encontrar e clicar no botão de pesquisa
    botao_pesquisa = driver.find_element('id', 'B_48')
    botao_pesquisa.click()

    # Opcional: Aguardar um pouco para ver o resultado (remova se não necessário)
    time.sleep(20)

    # Valores padrão
    debito = 0
    multa = 0
    ipva = 0
    licenciamento = 0

    driver.switch_to.default_content()
    driver.switch_to.frame(0)

    try:
        multa = re.sub(r',','.',re.sub(r'\.','',re.findall(r'\d+,\d+',driver.find_element(By.ID,'F_117').get_attribute('value'))[0]))
    except:
        multa = 0
    try:
        licenciamento = re.sub(r',','.',re.sub(r'\.','',re.findall(r'\d+,\d+',driver.find_element(By.ID,'F_105').get_attribute('value'))[0]))
    except:
        licenciamento = 0
    try:
        ipva = re.sub(r',','.',re.sub(r'\.','',re.findall(r'\d+,\d+',driver.find_element(By.ID,'F_101').get_attribute('value'))[0]))
    except:
        ipva = 0
    try:
        debito = re.sub(r',','.',re.sub(r'\.','',re.findall(r'\d+,\d+',driver.find_element(By.ID,'F_121').get_attribute('value'))[0]))
    except:
        debito = 0
    
    driver.switch_to.default_content()
    driver.switch_to.frame(2)

    
    try:
        status = driver.find_element('id','STATUSBAR54').text
        if 'não cadastrada' in status:
            debito = 'OE'
            multa = 'OE'
            licenciamento = 'OE'
            ipva = 'OE'

    except Exception as e:
        print('Erro', e)
    # Fechar o navegador
    driver.quit()
    time.sleep(60)
    return debito, multa, ipva, licenciamento

def debito_RR(placa, renavam):
    driver = webdriver.Chrome()

    # Navegar até a URL
    driver.get('https://www.rr.getran.com.br/site/apps/veiculo/filtroplacarenavam-consultaveiculo.jsp')

    # Aguardar 5 segundos para a página carregar
    time.sleep(5)

    # Encontrar e preencher o campo da placa
    campo_placa = driver.find_element('xpath', "//input[@title='Placa']")
    campo_placa.send_keys(placa)

    # Encontrar e preencher o campo do RENAVAM
    campo_renavam = driver.find_element('xpath', "//input[@title='Renavam']")
    campo_renavam.send_keys(renavam)

    # Encontrar e clicar no botão de pesquisa
    botao_pesquisa = driver.find_element('id', 'submeter')
    botao_pesquisa.click()

    time.sleep(5)

    try:
        status = driver.switch_to.alert.text
        if 'cadastrado' in status:
            debito_detran = 'OE'

    except:
        debito_detran = 0

    driver.quit()
    return debito_detran

def debito_MS(placa, renavam, rscript_path, r_file_path):

    botao_consulta = '//*[@id="main_table_form"]/tbody/tr/td/div/table/tbody/tr[4]/td/table/tbody/tr/td/table/tbody/tr/td[2]'
    imagem_captcha = '//*[@id="main_table_form"]/tbody/tr/td/div/table/tbody/tr[3]/td/table/tbody/tr[2]/td/input'

    # Configurar o driver do Chrome
    driver = webdriver.Chrome()

    # Acessar a página inicial

    # Esperar a página carregar
    rodou = 0
    while rodou==0:
        url = "https://www.meudetran.ms.gov.br/principal-portal/principal-portal.php?opcao_menu_ssn=DEBITO"
        driver.get(url)

        time.sleep(5)  # Ajuste conforme necessário

        # Mudar para o iframe onde o formulário está
        # iframe = driver.find_element(By.ID, "ifrm-pdr-portal")
        # driver.switch_to.frame(iframe)

        # Localizar os campos (substitua pelos IDs/nomes reais após inspecionar)

        placa_field = driver.find_element(By.ID, "id_read_off_placa")  # Exemplo de ID, ajuste conforme o HTML real
        renavam_field = driver.find_element(By.ID, "id_read_off_renavam")  # Exemplo de ID
        # Preencher os campos
        placa_field.click()

        py.write(placa)  # Substitua pela placa real
        renavam_field.click()
        py.write(renavam)  # Substitua pelo RENAVAM real

        captcha_field = driver.find_element(By.ID, "id_captcha_img")  # Exemplo de ID
        captcha_field.screenshot("captcha2.png")

        caminho_imagem = "captcha2.png"
        rscript_path = rscript_path
                
        r_file_path = r_file_path

        uf_R='MS'

        time.sleep(3)
        try:
            print('Indo para o script R')
            result = subprocess.run(
                    [rscript_path, "--vanilla", r_file_path, caminho_imagem, uf_R],  # Passa como lista
                    capture_output=True,
                    text=True,
                    check=True
                )
            result.stdout
            texto = re.findall(r'[a-zA-Z0-9]+',result.stdout)[0]
            print(texto)

        except:
            try:
                imagem = Image.open(caminho_imagem)
                print(pt.image_to_string(imagem))
                texto = re.findall(r'[a-zA-Z0-9]+',pt.image_to_string(imagem))[0]
                print(texto)
            except:
                texto = '0'
        cap = driver.find_element('xpath',imagem_captcha)
        cap.click()
        if len(texto)>0:
            py.write(texto)

        botao = driver.find_element('xpath',botao_consulta).click()
        time.sleep(1)

        try:
            notif = driver.find_element('xpath','//*[@id="notifications"]/div').text
            if 'CAPTCHA' in notif:
                rodou = 0
            elif 'MS' in notif:
                rodou = 0
                debito_detran = 'OE'
                print(debito_detran)
        except:
            debito_detran = 1

    return debito_detran

async def debito_AL_AT(placas, veiculos ,cursor):
    
    async def main():
        opt = Optionsp()
        opt.add_argument('--headless')
        opt.add_argument('--incognito')
        
        async with Chrome() as browser:
            await browser.start()
            
            page = await browser.get_page()
            
            for linha_al in range(len(placas)):
                placa = placas['Placa'][linha_al]
                renavam = placas['Renavam'][linha_al]

                # --- Consulta à base (CADSEN) para verificar IPVA_AL_ANT > 0 ---
                # Na produção era um SELECT no MySQL: execuções deste ano, desta placa,
                # com IPVA_AL_ANT diferente de '0' ou nulo.
                cadsen = bd.ler("CADSEN")
                ipva_al_ant = cadsen["IPVA_AL_ANT"]
                bd_ipva_ant = cadsen[(cadsen["DTA_EXEC"].fillna("").str[:4] == datetime.now().strftime('%Y')) &
                                     (cadsen["PLACA"] == placa) &
                                     (ipva_al_ant.isna() | (ipva_al_ant.fillna("") != '0'))]

                if len(bd_ipva_ant.dropna(how='all'))==0:
                    veiculos.loc[linha_al,"IPVA Ant"] = 0
                    continue  # Não tem IPVA de anos anteriores → ignora a automação

                await page.go_to('https://contribuinte.sefaz.al.gov.br/parcelamento/#/')

                rodou = 0
                tentativa = 1
                while rodou == 0 and tentativa <= 10:
                    try:
                        await asyncio.sleep(5)

                        try:
                            botao_sair = await page.find_element(Byp.ID, 'logout')
                            await botao_sair.click()
                            await asyncio.sleep(10)
                        except:
                            pass

                        botao_ipva = await page.find_element(Byp.ID,'btnVeiculoDebitosIPVA')
                        await botao_ipva.click()

                        campo_placa = await page.find_element(Byp.ID,'placa')
                        await campo_placa.click()
                        await campo_placa.send_keys(placa)

                        campo_renavam = await page.find_element(Byp.ID,'renavam')
                        await campo_renavam.click()
                        await campo_renavam.send_keys(renavam)

                        botao_acessa = await page.find_element(Byp.XPATH,'//*[@id="loginForm"]/button')
                        await botao_acessa.click()
                        await asyncio.sleep(1)
                        await botao_acessa.click()

                        await asyncio.sleep(13)
                        await page.find_element(Byp.XPATH, "//a[@routerlink='parcelamento']")  # validação de login
                        rodou = 1

                        # SEGUNDO BLOCO
                        rodou2 = 0
                        tentativa2 = 1
                        while rodou2 == 0 and tentativa2 <= 10:
                            try:
                                await asyncio.sleep(5)
                                botao_debito = await page.find_element(Byp.XPATH, '/html/body/jhi-main/div[2]/div/jhi-home/div/div/div/div/p/a[1]')
                                await botao_debito.click()
                                rodou2 = 1

                                
                                # TERCEIRO BLOCO
                                rodou3 = 0
                                tentativa3 = 1
                                while rodou3 == 0 and tentativa3 <= 10:
                                    try:
                                        # FECHAR ALERTA
                                        try:
                                            fecha_mensagem = await page.find_element(Byp.XPATH,'/html/body/ngb-modal-window[2]/div/div/jhi-mensagem-alerta/div[1]/button')
                                            await asyncio.sleep(10)
                                            await fecha_mensagem.click()
                                            fecha_mensagem = await page.find_element(Byp.XPATH,'/html/body/ngb-modal-window/div/div/jhi-mensagem-alerta/div[1]/button')
                                            await fecha_mensagem.click()
                                        except:
                                            pass

                                        await asyncio.sleep(7)
                                        tabela_valores = await page.find_element(Byp.ID,'tab-selecionar-Sefaz-panel')
                                        tabela_valores = await tabela_valores.get_element_text()
                                        
                                        valores = re.findall(r'(?:[\d.]+)?,\d{2}', tabela_valores)
                                        
                                        valores = round(sum([float(numero.replace('.', '').replace(',', '.')) for numero in valores]), 2)

                                        botao_sair = await page.find_element(Byp.ID, 'logout')
                                        await botao_sair.click()

                                        rodou3 = 1
                                    except:
                                        print(f"Tentativa {tentativa3} de 10, na terceira pag, para placa {placa}")
                                        tentativa3 += 1
                                        await page.refresh()
                                else:
                                    if rodou3 == 0:
                                        valores = 0

                            except:
                                print(f"Tentativa {tentativa2} de 10, na segunda pag, para placa {placa}")
                                tentativa2 += 1
                                await page.refresh()
                        else:
                            if rodou2 == 0:
                                valores = 0

                    except:
                        print(f"Tentativa {tentativa} de 10, na primeira pag, para placa {placa}")
                        tentativa += 1
                        await page.refresh()
                else:
                    if rodou == 0:
                        valores = ''

                # Atualiza DataFrame
                if valores != '':
                    veiculos.loc[linha_al,"IPVA Ant"] = valores
                    try:
                        ipva_atual = float(veiculos.loc[linha_al,"IPVA"])
                    except:
                        ipva_atual = 0.0

                    try:
                        debito_atual = float(veiculos.loc[linha_al,"Debito Detran"])
                    except:
                        debito_atual = 0.0

                    veiculos.loc[linha_al,"IPVA"] = ipva_atual + valores
                    veiculos.loc[linha_al,"Debito Detran"] = debito_atual + valores


            return veiculos

    return await main()

def debito_RJ_IPVA(placas, veiculos):

    ### IPVA ###
    driver = webdriver.Chrome()

    
    for linha_rj in range(len(placas)):
        
        renavam = placas['Renavam'][linha_rj]


        # Navegar até a URL
        driver.get(f'https://darj-ipva-web.fazenda.rj.gov.br/darj-ipva-web/#/resultado/{renavam}')
        driver.refresh()

        # Aguardar 5 segundos para a página carregar
        time.sleep(5)
        
        # campo_renavam = driver.find_element(By.ID,'renavam').send_keys(renavam)

        # bt_consulta = driver.find_element(By.XPATH,'/html/body/app-root/app-main/main/div/app-formulario-consulta-v2/app-form-page/div/p-card/div/div/div/div/div/form/div/div/div[2]/button[1]/span').click()

        # time.sleep(5)

        ipva_ant = 0
        ipva = 0  # valor do IPVA do ano atual (caso exista)
        ano_atual = str(datetime.now().year)


        try:
            anos = driver.find_element(By.CLASS_NAME,'p-tabview-nav').text
            qtd_ano = len(re.findall(r'\d+',anos))
            
            for num_ano in range(qtd_ano):
                driver.find_element(By.ID, f'p-tabpanel-{num_ano}-label').click()
                id_num = 5 + (num_ano * 2)
                time.sleep(2)
            
                try:
                    tabela = driver.find_element(By.ID, f'pr_id_{id_num}-table').text
                    valores_ipva = re.findall(r'\nR\$\s+(\d+,\d+)', tabela)
                    valor = round(sum(float(v.replace(',', '.')) for v in valores_ipva[4::5]), 2)
                except:
                    valor = 0
            
                if ano_atual not in anos:
                    # Ano atual não está: soma tudo em ipva_ant, ipva deve continuar 0
                    ipva_ant += valor
                else:
                    if num_ano < qtd_ano - 1:
                        # Anos anteriores ao atual
                        ipva_ant += valor
                    else:
                        # Último ano (ano atual): salvar separado
                        ipva = valor
            
                time.sleep(2)

        except:
            pass

        try:
            ipva = ipva + ipva_ant
        except:
            pass
        # print("IPVA anos anteriores:", ipva_ant)
        # print("IPVA ano atual:", ipva)
        
        veiculos.loc[linha_rj,"IPVA"] = ipva
        veiculos.loc[linha_rj,"IPVA Ant"] = ipva_ant
    
        try:
            debito_atual = float(veiculos.loc[linha_rj,"Debito Detran"])
        except:
            debito_atual = 0.0

        veiculos.loc[linha_rj,"IPVA"] = ipva
        veiculos.loc[linha_rj,"Debito Detran"] = debito_atual + ipva


    driver.quit()

    return veiculos

def debito_RN(placa, renavam, cnpj):

    # Login do portal do DETRAN-RN vem de obter_credencial() (config.py)
    if obter_credencial("DETRAN_RN_CNPJ") and cnpj in (obter_credencial("DETRAN_RN_CNPJ")):
        senha_api = obter_credencial("DETRAN_RN_SENHA")
        cnpj_api = cnpj
    else:
        senha_api = ''
        cnpj_api = ''

    url = 'https://api.infosimples.com/api/v2/consultas/detran/rn/veiculo'
    args = {
    "login_cpf":   cnpj_api,
    "login_senha": senha_api,
    "placa":       placa,
    "renavam":     renavam,
    "token":       obter_credencial("INFOSIMPLES_TOKEN"),
    "timeout":     300
    }

    # arquivo_json = open(r"arquivo_rn.json")
    # response_json_RN = json.load(arquivo_json)


    if cnpj_api != '' and senha_api != '':
    
        tentativas = 0
        ipva = 0
        multa = 0
        custo_api = 0

        while tentativas < 5:
            print(f'Tentativa {tentativas+1} para a placa {placa}')
            tentativas += 1

            response = requests.post(url, args)

            try:
                response_json_RN = response.json()
            except Exception as e:
                print(f"Erro ao decodificar JSON: {e}")
                print(f"Status code: {response.status_code}")
                response.close()
                continue

            response.close()

            if response_json_RN.get('code') == 200:
                try:
                    ipva = response_json_RN['data'][0]['valor_ipva']
                except:
                    ipva = 0

                try:
                    multa = response_json_RN['data'][0]['valor_multas']
                except:
                    multa = 0

                try:
                    custo_api = response_json_RN['header']['price']
                except:
                    custo_api = 0

                break

            elif response_json_RN.get('code') in (606, 607, 608, 611, 612, 620):
                try:
                    custo_api = response_json_RN['header']['price']
                except:
                    custo_api = 0
                ipva = 0
                multa = 0
                break

            else:
                try:
                    custo_api = response_json_RN['header']['price']
                except:
                    custo_api = 0
                ipva = 0
                multa = 0

    else:
        print('Cnpj ou senha não correspondem')
        ipva = 0
        multa = 0
        custo_api = 0



    debito = ipva + multa

    return debito, multa, ipva, custo_api

async def debito_PE_free(dados_pe,loop):
    
    # vai usar o selenium, enquanto tiver funcionando
    fecha_notif = '//*[@id="notification-wrapper"]/li/div/div/button'
    

    async def main():
        valores_pe=pd.DataFrame()
        mensagem_aviso = '/html/body/div/div[2]/div/div/div/div/div/div/div/div[2]/div[2]/dd/div'

        async with Chrome() as browser:
            await browser.start()
            
            page = await browser.get_page()
            
            await page.go_to('https://www.detran.pe.gov.br/')
            await browser.set_window_maximized()

            await asyncio.sleep(5)

            try:
                botao_fecha_notif = await page.find_element(Byp.XPATH,fecha_notif)
                await botao_fecha_notif.click()
            except:
                pass
            
            botao_consulta_placa = await page.find_element(Byp.ID,'btnGov-placa')
            await botao_consulta_placa.click()

            # await page.go_to('https://sso.acesso.gov.br/login?client_id=online8.detran.pe.gov.br&authorization_id=...')
        
            await asyncio.sleep(10)

            # graças ao valor do loop de Transformer.py, ele deverá ir para o mesmo certificado do loop/empresa atual.
            py.press('up')
            py.press('enter')

            for qtd_baixo in range(loop+1):
                py.press('down')

            for qtd_tab in range(0,2):
                py.press('tab')
            py.press('enter')

            await asyncio.sleep(10)

            # pagina_gov = await page.current_url

            # while 'online' not in pagina_gov:
            #     time.sleep(10)

            for qtd_tab in range(0,4):
                py.press('tab')
            py.press('enter')

            button = await page.find_element(Byp.ID, 'login-certificate')
            await button.click()

            await asyncio.sleep(7)

            py.press('up')
            py.press('enter')

            for qtd_baixo in range(loop+1):
                py.press('down')

            for qtd_tab in range(0,2):
                py.press('tab')
            py.press('enter')

            await asyncio.sleep(10)

            # pagina_detran = await page.current_url
            

            # while 'ConsultarPlaca' not in pagina_detran:
            #     time.sleep(10)

            # Foi acrescentado o loop para percorrer todas as placas do dataframe
            # O certificado é selecionado apenas uma vez para verificar todas as placas. 
            for linha_placas_pe in range(len(dados_pe)):
                placa_pe = dados_pe.iloc[[linha_placas_pe]]
                
                aviso=1
                avancar = False

                # loop para caso de surgir mensagem de erro entre a confecção de placas. Assim a página recarrega novamente
                while aviso==1:
                    # await page.go_to('https://online5.detran.pe.gov.br/ServicosWeb/VeiculoMVC/ConsultaPlaca/ConsultarPlaca')
                    # await asyncio.sleep(3)

                    # url_erro = await page.current_url

                    # if 'Erro' in url_erro:
                        
                    #     await page.go_to('https://www.detran.pe.gov.br/')
                    #     await browser.set_window_maximized()

                    #     await asyncio.sleep(5)

                    #     try:
                    #         botao_fecha_notif = await page.find_element(Byp.XPATH,fecha_notif)
                    #         await botao_fecha_notif.click()
                    #     except:
                    #         pass
                        
                    #     botao_consulta_placa = await page.find_element(Byp.ID,'btnGov-placa')
                    #     await botao_consulta_placa.click()
                    #     await asyncio.sleep(3)

                    await page.go_to('https://www.detran.pe.gov.br/')
                    await browser.set_window_maximized()

                    await asyncio.sleep(5)

                    try:
                        botao_fecha_notif = await page.find_element(Byp.XPATH,fecha_notif)
                        await botao_fecha_notif.click()
                    except:
                        pass
                    
                    botao_consulta_placa = await page.find_element(Byp.ID,'btnGov-placa')
                    await botao_consulta_placa.click()
                    await asyncio.sleep(3)

                    try:
                        botao_gov = await page.find_element(Byp.ID,'btnGov')    
                        await botao_gov.click()   
                        aviso = 1
                        await page.refresh()
                    except:
                        pass

                    try:
                        msg_aviso = await page.find_element(Byp.XPATH, mensagem_aviso)
                        mensagem = await msg_aviso.get_element_text()
                        print('tem mensagem de aviso: ', mensagem)
                        aviso = 1
                        await page.refresh()
                    except:
                        pass
                    
                    try:
                        busca_placa = await page.find_element(Byp.ID,'buscar-placa')
                        await busca_placa.click()
                        await busca_placa.send_keys(placa_pe['Placa'].iloc[0])
                        
                        await asyncio.sleep(2)
                        botao_pesquisa = await page.find_element(Byp.ID,'botao-busca-placa')
                        await botao_pesquisa.click()
                        await asyncio.sleep(3)
                        
                        try:
                            botao_gov = await page.find_element(Byp.ID,'btnGov')    
                            await botao_gov.click()   
                            aviso = 1
                            await page.refresh()
                        except:
                            pass
                        
                        try:
                            msg_aviso = await page.find_element(Byp.XPATH, mensagem_aviso)
                            mensagem = await msg_aviso.get_element_text()
                            print('mostrou mensagem de erro: ', mensagem)
                            if 'não pertence' in mensagem or 'CNPJ' in mensagem or '808' in mensagem:
                                # aviso = 0
                                debito_detran = 'OE'
                                licenciamento = 'OE'
                                multa = 'OE'
                                ipva = 'OE'
                                ipva_ant = 'OE'
                                custo_api = 0
                                gravame_pen = 'OE'
                                
                                avancar = True
                                break
                            else:
                                aviso = 1
                        except:
                            aviso = 0
                            await asyncio.sleep(3)
                    except:
                        aviso = 1
                        await page.refresh()
                if avancar:
                    rodou = 1
                
                # caso só retorne uma mensagem dizendo que não existe placa para PE, o codigo abaixo não irá funcionar, resultando no valor atribuido a outro estado
                
                rodou = 0
                while rodou==0:
                    
                    try:
                        await page.refresh()
                        await asyncio.sleep(3)

                        try:
                            consulta_debito = await page.find_element(Byp.ID,'consultar-debitos')
                            # print(consulta_debito)
                            await consulta_debito.click()

                            await asyncio.sleep(4)

                            try:
                                botao_gov = await page.find_element(Byp.ID,'btnGov')    
                                await botao_gov.click()   
                                rodou = 0
                                await page.go_to('https://online5.detran.pe.gov.br/ServicosWeb/VeiculoMVC/ConsultaPlaca/ConsultarPlaca')
                                
                            except:
                                pass
                        except:
                            pass

                        # try:
                        #     msg_licenciamento = await page.find_element(Byp.CLASS_NAME,'table-responsive px-2')
                        #     sim_nada = await msg_licenciamento.get_element_text()
                        #     print(sim_nada)
                        # except:
                        #     print("tem valor")

                        try:
                            # rodou = 0
                            # tentativas = 1
                            # while rodou == 0 and tentativas <= 3:
                            #     try:
                            #         guia_pagamento = await page.find_element(Byp.ID, 'emissao-tab')
                            #     except:
                            await page.refresh()
                            await asyncio.sleep(3)
                            
                            try:
                                valores_debito = await page.find_element(Byp.ID,'licenciamento')
                                debitos = await valores_debito.get_element_text()
                                valores_ipva = re.findall(r'(IPVA)(\d{4})(ÚNICA)(\d{2}/\d{2}/\d{4})([\d.]+,\d{2})',debitos)
                                ipva = round(sum(float(valor.replace('.', '').replace(',', '.')) for *_, valor in valores_ipva),2)

                                valores_lic = re.findall(r'(LICENCIAMENTO)(\d{4})(ÚNICA)(\d{2}/\d{2}/\d{4})([\d.]+,\d{2})',debitos)
                                licenciamento = round(sum(float(valor.replace('.', '').replace(',', '.')) for *_, valor in valores_lic),2)

                            except:
                                ipva = 0
                                licenciamento = 0

                            try:
                                valores_total = await page.find_element(Byp.XPATH,"//comment()[contains(., 'Início totalização')]/following::div[contains(@class, 'card-dtl-debitos')]")
                                totalizacao = await valores_total.get_element_text()
                                debito_detran = re.sub(r',', '.', re.sub(r'\.', '', re.findall(r'R\$\s+([\d.,]+)Total',totalizacao)[0]))
                            except:
                                debito_detran = 0
                            
                            try:
                                multas = await page.find_element(Byp.XPATH,"//comment()[contains(., 'Início débitos')]/following::div[contains(@class, 'card-dtl-debitos')]")
                                valores_multas = await multas.get_element_text()

                                multa = round(sum(float(valor.replace(',', '.')) for valor in re.findall(r'R\$\s*:\s*([\d.,]+)Lote',valores_multas)),2)
                            except:
                                multa = 0
                            # debito_detran = licenciamento + multa + ipva
                            ipva_ant = ''
                            custo_api = 0

                            try:
                                restricao = await page.find_element(Byp.ID,'Restricao')
                                mensagem_rest = await restricao.get_element_text()
                                if 'GRAVAME PENDENTE' in mensagem_rest:
                                    gravame_pen = "Sim"
                                else:
                                    gravame_pen = "Não"
                            except:
                                gravame_pen = "Não"

                            rodou = 1
                            
                        except:
                            debito_detran = 0
                            licenciamento = 0
                            multa = 0
                            ipva = 0
                            ipva_ant = ''
                            custo_api = 0
                            gravame_pen = "Não"
                            rodou = 1
                    except:
                        # debito_detran = 'OE'
                        # licenciamento = 'OE'
                        # multa = 'OE'
                        # ipva = 'OE'
                        # ipva_ant = ''

                        rodou = 0



                # print(debito)
                debito_detran_pe = pd.DataFrame({
                    'Debito Detran': [debito_detran],
                    'Licenciamento': [licenciamento],
                    'Multa': [multa],
                    'IPVA': [ipva],
                    'IPVA Ant': [ipva_ant],
                    'Custo': [custo_api],
                    'Gravame Pendente': [gravame_pen]

                })

                valores_pe = valores_pe._append(debito_detran_pe)
                
        return valores_pe
        
    return await main()
    
def debito_PE(placa, cert, senha):
    # obter_credencial("CHAVE_CRIPTOGRAFIA") vem de obter_credencial() (config.py)

    url = 'https://api.infosimples.com/api/v2/consultas/detran/pe/veiculo'
    args = {
    "pkcs12_cert": aes256.encrypt(base64.b64encode(open(cert, "rb").read()).decode(), obter_credencial("CHAVE_CRIPTOGRAFIA")),
    "pkcs12_pass": aes256.encrypt(senha, obter_credencial("CHAVE_CRIPTOGRAFIA")),
    "placa":       placa,
    "token":       obter_credencial("INFOSIMPLES_TOKEN"),
    "timeout":     300
    }

    response = requests.post(url, args)
    response_PE_json = response.json()
    response.close()

    if not response_PE_json.get('data'):
        return 0, 0, 0, 0, 0, 'Não'

    # # Deixar as próximas duas linhas como comentários, em caso de não for teste
    # arquivo_json = open(r"senatran_teste_veiculo_detran.json")
    # response_PE_json = json.load(arquivo_json)

    # ta pegando caso nao tenha informações
    #codigo 612 quando é de outro estado
    try:
        debito_detran = response_PE_json['data'][0]['debitos']['valor_total_normalizado']
    except:
        debito_detran = 0
    try:
        multa = round(sum([valor['valor_normalizado'] for valor in response_PE_json['data'][0]['debitos']['multas']]),2)
    except:
        multa = 0
    try:
        licenciamento = round(sum([valor['valor_normalizado'] for valor in response_PE_json['data'][0]['debitos']['licenciamento'] if valor['debito'] == 'LICENCIAMENTO']),2)
    except:
        licenciamento = 0
    try:
        ipva = round(sum([valor['valor_normalizado'] for valor in response_PE_json['data'][0]['debitos']['licenciamento'] if valor['debito'] == 'IPVA' and valor['cota'] == 'ÚNICA']),2)
    except:
        ipva = 0
    try:
        gravame_pen = 'Sim' if any('GRAVAME PENDENTE' in restricao for restricao in response_PE_json['data'][0]['restricoes']) else 'Não'
    except:
        gravame_pen = 'Não'
    try:
        custo_api = response_PE_json['header']['price']
    except:
        custo_api = 0

    return debito_detran, licenciamento, multa, ipva, custo_api, gravame_pen

def debito_CE_pay(placa, renavam):
    url = 'https://api.infosimples.com/api/v2/consultas/detran/ce/licenciamento'
    url2 = 'https://api.infosimples.com/api/v2/consultas/detran/ce/multas'
    args = {
    "placa":       placa,
    "renavam":     renavam,
    "token":       obter_credencial("INFOSIMPLES_TOKEN"),
    "timeout":     300
    }

    response = requests.post(url, args)
    response_CE_json = response.json()
    response.close()

    multa = 0
    licenciamento = 0
    custo_api_mul = 0
    custo_api_lic = 0

    if response_CE_json['code'] == 200 and response_CE_json.get('data'):
        try:
            licenciamento = response_CE_json['data'][0]['dados_licenciamento']['normalizado_valor']
        except:
            licenciamento = 0
        
        try:
            custo_api_lic = round(float(response_CE_json['header']['price']),2)
        except:
            custo_api_lic = 0
    # 
    # arquivo = open("senatran_teste_veiculo_detran.json", "w", encoding="utf-8")
    # json.dump(response_PE_json, arquivo, ensure_ascii=False, indent=2)
    # arquivo.close()

    response = requests.post(url2, args)
    response_CE2_json = response.json()
    response.close()

    if response_CE2_json['code'] == 200 and response_CE2_json.get('data'):
        try:
            multa = round(sum([valor['normalizado_valor'] for valor in response_CE2_json['data'][0]['multas']]),2)
        except:
            multa = 0
        
        try:
            custo_api_mul = round(float(response_CE2_json['header']['price']),2)
        except:
            custo_api_mul = 0

    debito_detran = multa + licenciamento
    custo_api = custo_api_mul + custo_api_lic

    return debito_detran, licenciamento, multa, custo_api