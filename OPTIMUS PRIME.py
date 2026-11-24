import asyncio
from pydoll.browser.chrome import Chrome
from pydoll.constants import By
import time
import pyautogui as py
from pydoll.browser.options import Options
import re
import pandas as pd
import os
import pdfplumber as pdf
from datetime import datetime
from glob import glob
from DETRAN import veic_detran
# from busca_imagem import buscar_primeira_imagem  # fora do repositório público (o uso abaixo já estava desligado)
from API_FIPE import fipe_webhook
import openpyxl
import sys
import armazenamento as bd
import json
import requests
from tkinter import messagebox


print('Executando Optimus Prime.py')


hora_ini2 = datetime.now()
caminho_salvar=f"{os.getcwd()}\\senatran"

# Na produção: conexão MySQL (bd_senatran). Nesta versão pública as tabelas são
# arquivos Parquet em dados/ (ver armazenamento.py).
from config import CNPJS_POR_UF

# num_empresas = 2

##### BOTOES DAS PAGINAS #####

tabela_dados='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[3]/div'
botao_pag_volta='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[3]/div/table/tfoot/tr/td[1]/pagination/ul/li[2]/a'
botao_pag_ida='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[3]/div/table/tfoot/tr/td[1]/pagination/ul/li[8]/a'
botao_pag_men4='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[3]/div/table/tfoot/tr/td[1]/pagination/ul/li[6]/a'
botao_pag_igual4='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[3]/div/table/tfoot/tr/td[1]/pagination/ul/li[7]/a'
dados_veic='//*[@id="header-small"]/br-tab-set/div/nav/br-tab[1]'
sit_veic='//*[@id="header-small"]/br-tab-set/div/nav/br-tab[2]'
botao_sit='//*[@id="header-small"]/br-tab-set/div/nav/ul/li[2]/button'
fecha_pup='/html/body/modal-container/div/div/div[3]/div/button'
download_veic='//*[@id="header-small"]/br-tab-set/div/nav/br-tab[1]/div/app-veiculo-dados/div/div/table/tbody/tr[2]/td/a'
fecha_cookie='//*[@id="cookiebar"]/div[1]/div/div/div/div[2]/button[2]'         
caixa_selecao='/html/body/modal-container/div/div/div[2]/div/div/label'
nao_adere='/html/body/modal-container/div/div/div[3]/div/button[2]'
botao_sim_renainf='//*[@id="header-small"]/br-tab-set/div/nav/br-tab[2]/div/app-veiculo-indicadores/div/div/table/tbody/tr[8]/td/a'
botao_sim_renajud='//*[@id="header-small"]/br-tab-set/div/nav/br-tab[2]/div/app-veiculo-indicadores/div/div/table/tbody/tr[7]/td/a'
chassi_renajud='/html/body/modal-container/div/div/div[2]/app-veiculo-modal-renajud/table/tbody/tr[2]/td[2]/span'
prox_pag_renajud='//*[@id="btn-next-page"]/i'
prox_pag_renainf='//*[@id="btn-next-page"]/i'
tab_multa='/html/body/modal-container/div/div/div[2]/app-veiculo-modal-renainf/div/div/br-table/div/ngx-datatable/div'
fecha_multa='/html/body/modal-container/div/div/div[1]/div/a'
tabela_processos='/html/body/modal-container/div/div/div[2]/app-veiculo-modal-renajud/div/div/br-table/div/ngx-datatable/div/datatable-body'
num_proc='/html/body/modal-container/div/div/div[2]/app-veiculo-modal-renajud/div/div/br-table/div/ngx-datatable/div/datatable-body/datatable-selection/datatable-scroller/datatable-summary-row/datatable-body-row/div[2]/datatable-body-cell[3]/div/span'
msg_atencao='/html/body/app-root/form/br-main-layout/div/div/main/app-veiculo/app-veiculos-list/div/div/div[2]/form/br-tab-set/div/nav/br-tab/div/div[1]/div/div/div[2]/div'

cnpj = [cnpj]
cert = cert
senha = senha
# loop=0
opt = Options()
# opt.add_argument('--ssl-client-certificate-file=Certificados/EMPRESA EXEMPLO ALFA 11111111000111.pfx')
# opt.add_argument('--incognito')

async def main():
    
    async with Chrome() as browser:
        await browser.start()
        
        page = await browser.get_page()
        
        await page.go_to('https://portalservicos.senatran.serpro.gov.br/#/veiculos/meus-veiculos')
        # messagebox.showinfo("Title", "This is a message!")
        await asyncio.sleep(10)

        # Loop feito para escolher a opção de localização que aparece na página. 
        for qtd_tab in range(0,3):
            py.press('tab')
        py.press('enter')
        
        # Seleção do botão para inserir o certificado
        button = await page.find_element(By.ID, 'login-certificate')
        await button.click()
        await asyncio.sleep(7)

        
        await asyncio.sleep(10)
        
        # Loop feito para escolher a opção de certificado que aparece na página. O valor de 'loop' atribuído aqui é referente à ordem da empresa colocada em Transformer.py
        py.press('up')
        py.press('enter')

        for qtd_baixo in range(loop+1):
            py.press('down')

        # Loop feito para escolher a opção de certificado que aparece na página. 
        for qtd_tab in range(0,2):
            py.press('tab')
        py.press('enter')

        try:
            await asyncio.sleep(5)
            
            button_fecha_cookie = await page.find_element(By.XPATH,fecha_cookie)
            await button_fecha_cookie.click()
            
            await asyncio.sleep(2)
            button_fecha_aviso = await page.find_element(By.XPATH,fecha_pup)
            await button_fecha_aviso.click()
        
            await asyncio.sleep(4)
            button_caixa = await page.find_element(By.XPATH,caixa_selecao)
            await button_caixa.click()
            
            button_aderir = await page.find_element(By.XPATH,nao_adere)
            await button_aderir.click()
            
            await asyncio.sleep(3)
        except:
            await asyncio.sleep(3)
    #     await coleta(page,browser)

    # async def coleta(page,browser):

        try:
            mensagem_atencao = await page.find_element(By.XPATH,msg_atencao)
            mensagem_atencao = await mensagem_atencao.get_element_text()
            if 'Nenhum registro encontrado' in mensagem_atencao:
                return
        except:
            pass

        renavam=[]
        placa=[]

        achou=0

        # Enquanto não achar a tabela de cards com veículos, ficará atualizando a página. 
        while achou==0:

            try:
                tab = await page.find_element(By.XPATH,tabela_dados)
                tab = await tab.get_element_text()
                achou=1
            except:
                await page.refresh()
                await asyncio.sleep(5)

        
        # print(re.findall(r'Total de veículos:\s*(\d+)',tab))

        num_veic=int(re.findall(r'veículos:\s*(\d+)P',tab)[0])
             
        # num_pag=round(num_veic/12+0.5) # Sao 12 cards por pagina. Logo o total de veículos dividido por 12 + 0.5 dará o número de páginas.
        
        if num_veic % 12 == 0:
            num_pag = num_veic // 12
        else:
            num_pag = round(num_veic / 12 + 0.5)

        print('Numero de veiculos: ',num_veic)
        print('Numero de paginas: ',num_pag)
        
        if num_pag == 4:
            botao_ida = await page.find_element(By.XPATH,botao_pag_igual4)
        elif num_pag < 4 and num_pag > 1:
            botao_ida = await page.find_element(By.XPATH,botao_pag_men4)
        elif num_pag > 4:    
            botao_ida = await page.find_element(By.XPATH,botao_pag_ida)
        # botao_volta = await page.find_element(By.XPATH,botao_pag_volta)

        # O loop irá percorrer página por página coletando as placas e renavans dos veículos
        for pag in range(1,num_pag +1 ):
        # for pag in range(0,1):
            tab = await page.find_element(By.XPATH,tabela_dados)
            tab = await tab.get_element_text()
            
            placa_renavam = re.findall(r'([a-zA-Z0-9]{7})(\d{11})[a-zA-Z\s«]',tab)

            for item in placa_renavam:
                renavam.append(item[1])
                placa.append(item[0])
            
            if num_pag > 1:
                await botao_ida.click()
                

            await asyncio.sleep(8)
        # print(len(placa))

    #     await principal(page,renavam,placa,num_veic,browser)

    # async def principal(page,renavam,placa,num_veic,browser):

        # print(placa, renavam)
        planilhao=pd.DataFrame()

        # Depois de coletadas, o loop seguinte irá percorrer todas as linhas de placas e renavam. Depois disso, irá coletar os dados de cada veículo disponível no link 

        for num in range(0,len(placa)):
        
        # if len(placa)>6:
        #     placa_teste = 3
        # else:
        #     placa_teste = len(placa)
        
        # for num in range(0,placa_teste):

        # for num in range(0,2):
            placa_num=placa[num]
            # placa_num='ABC1D23'
            renav_num=renavam[num]
            # renav_num='00000000019'
            if renav_num != '00000000000':
                # Anter de coletar os dados, deverá ser verificado se a placa e data de execução do script constam na base de 
                # verifica_placa = cursor.execute(f"SELECT * FROM CADSEN WHERE PLACA = '{placa_num}' AND DTA_EXEC = strftime('%Y%m%d',date('now'))") # sqlite

                cadsen = bd.ler("CADSEN")
                bd_completo_placa = cadsen[(cadsen["PLACA"] == placa_num) &
                                           (cadsen["DTA_EXEC"] == datetime.now().strftime('%Y%m%d'))]
                
                # Caso não tenha dados, seguir em frente para a coleta. Caso contrário, o próximo veículo será verificado.
                if len(bd_completo_placa)==0:
                    print(placa_num)
                    await page.go_to(f'https://portalservicos.senatran.serpro.gov.br/#/veiculos/meus-veiculos/detalhes/{placa_num}/{renav_num}/false')
                    await page.refresh()
                    await asyncio.sleep(5)

                    try:
                        button_fecha_aviso = await page.find_element(By.XPATH,fecha_pup)
                        await button_fecha_aviso.click()
                    except:
                        await page.refresh()

                    achou=0

                    # Enquanto não achar a tabela de dados do veículo, ficará atualizando a página. 
                    while achou==0:
                        try:
                            await asyncio.sleep(1)
                            veiculo = await page.find_element(By.XPATH,dados_veic) # tabela de dados
                            veiculo = await veiculo.get_element_text()
                            
                            # download = await page.find_element(By.XPATH,download_veic)
                            # await download.click()

                            cnpj_prop=re.findall(r'Proprietário:(.+?)Nome',veiculo)
                            
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
                            
                            tipo=re.findall(r'Tipo:(.+?)Espécie',veiculo)
                            modelo=re.findall(r'Modelo:(.+?)Ano F',veiculo)
                            fabricacao=re.findall(r'Ano Fabricação:(.+?)Ano M',veiculo)
                            ano=re.findall(r'Ano Modelo:(.+?)Cor',veiculo)
                            carroceria=re.findall(r'Carroceria:(.+?)Categoria',veiculo)

                            await asyncio.sleep(1)
                            botao_situacao = await page.find_element(By.XPATH,botao_sit)
                            await botao_situacao.click()

                            situacao = await page.find_element(By.XPATH,sit_veic)
                            situacao = await situacao.get_element_text()

                            # print(situacao)
                            RADM = re.findall(r'1:(.+?)Restrição-2',situacao) # Estou focando na restrição 1, pois nenhum veículo retornou mais de uma.
                            
                            await asyncio.sleep(1)
                            # RENAINF
                            # try:
                            #     renainf_element = await page.find_element(By.XPATH, botao_sim_renainf)
                            #     await asyncio.sleep(3)
                            #     await renainf_element.click()
                            #     RINF='Sim'
                            #     await asyncio.sleep(3)
                            #     multas = await page.find_element(By.XPATH, tab_multa)
                            #     multas = await multas.get_element_text()
                            #     print(multas)
                            #     multas = re.findall(r'R\$\s+([\d.]+,\d{2})', multas)
                            #     total = sum(float(valor.replace('.', '').replace(',', '.')) for valor in multas)
                            #     print(total)
                                
                            #     button_fecha_multa = await page.find_element(By.XPATH, fecha_multa)
                            #     await button_fecha_multa.click()
                            # except:
                            #     RINF='Não'
                            
                            # RENAJUD

                            # Essa parte do script verifica se veículo tem Renajud interagindo com o botão da página. Se o botão não estiver presente, retornará 'Não' e o restante dos campos estará em branco
                            # importante ressaltar que essa parte funciona com 1 processo por veículo, pois não vi veículos com mais que isso.
                            try:
                                renajud_element = await page.find_element(By.XPATH, botao_sim_renajud)
                                await asyncio.sleep(3)
                                await renajud_element.click()
                                RJUD='Sim'
                                await asyncio.sleep(6)

                                cod_chassi = await page.find_element(By.XPATH, chassi_renajud)
                                chassi = await cod_chassi.get_element_text()

                                processos = await page.find_element(By.XPATH, tabela_processos)
                                processos = await processos.get_element_text()
                                
                                total_proc = re.findall(r'Total de Processos:\s*(\d+)',processos)
                                total_proc = total_proc[0]
                                
                                if int(total_proc)>=1:

                                    pag_renajud = round(int(total_proc)/10+0.5)

                                    bd.apagar("TB_RENAJUD", {"DTA_EXEC": datetime.now().strftime('%Y%m%d'),
                                                             "PLACA": placa_num})

                                    for pagina in range(0,pag_renajud):
                                        
                                        processos = await page.find_element(By.XPATH, tabela_processos)
                                        processos = await processos.get_element_text()
                                        dados_proc = re.findall(r'(.+?)\d+/\d+/\d+\s+-\s+\d+:\d+:\d+(.*?(?:AS|AO|UCO|EIRO))(.+?)(\d{20})', processos)
                                        
                                        for item in dados_proc:

                                            tipo_rest = item[0]
                                            tribunal = item[1]
                                            orgao = item[2]
                                            processo = item[3]

                                            bd.inserir("TB_RENAJUD", {"PLACA": placa_num,
                                                                      "TIPO_RESTRICAO": tipo_rest,
                                                                      "TRIBUNAL": tribunal,
                                                                      "ORGAO": orgao,
                                                                      "PROCESSO": processo,
                                                                      "DTA_EXEC": datetime.now().strftime('%Y%m%d')})
                                        prox_pag = await page.find_element(By.XPATH,prox_pag_renajud)

                                        await prox_pag.click()
                                else:
                                    tipo_rest = ''
                                    tribunal = ''
                                    orgao = ''
                                    processo = ''


                                button_fecha_multa = await page.find_element(By.XPATH, fecha_multa)
                                await button_fecha_multa.click()
                            except:
                                
                                await page.execute_script(f'''
                                                          document.evaluate(
                                                                '{botao_sim_renajud}',
                                                                document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                                                            ).singleNodeValue.removeAttribute('hidden')
                                                        ''')
                                renajud_element = await page.find_element(By.XPATH, botao_sim_renajud)

                                # print(renajud_element)
                                await renajud_element.click()
                                
                                await asyncio.sleep(3)
                                # # await renajud_element.click()
                                cod_chassi = await page.find_element(By.XPATH, chassi_renajud)
                                chassi = await cod_chassi.get_element_text()
                                print(chassi)

                                RJUD='Não'
                                total_proc='0'
                                tipo_rest = ''
                                tribunal = ''
                                orgao = ''
                                processo = ''
                            
                            # verificar se fez download antes de colocar os dados
                            # pdf_path = glob(os.path.join(os.path.expanduser("~"), "Downloads", f"*{placa_num}*.pdf"))[0]

                            # Junta os dados em um DataFrame
                            try:
                                veiculo_dados= {
                                'Placa': [placa_num],
                                'Renavam': [renav_num],
                                'CNPJ': cnpj,
                                'CNPJ_PROP': [re.sub(r'[./-]', '', cnpj_prop[0])],
                                'UF': uf,
                                'Tipo': tipo,
                                'Modelo': modelo,
                                'Ano': ano,
                                'Ano Fabricação': fabricacao,
                                'Carroceria': carroceria,
                                'Chassi': chassi,
                                'Gravame': RADM,
                                'Restricao Adm': RADM,
                                'RENAJUD': RJUD,
                                # 'Processo': processo,
                                # 'Tipo Restricao': tipo_rest,
                                # 'Tribunal': tribunal,
                                # 'Orgao': orgao,
                                'Processo': '',
                                'Tipo Restricao': '',
                                'Tribunal': '',
                                'Orgao': '',
                                'Total de Processos': total_proc,
                                'Data execucao': datetime.now().strftime('%Y%m%d')
                                
                                }
                                
                                for campo, valor in veiculo_dados.items():
                                    if isinstance(valor, list):
                                        veiculo_dados[campo] = [valor[0] if valor else '']
                                    else:
                                        veiculo_dados[campo] = [valor]

                            except Exception as e:
                                print("o erro ta aqui")
                                print(e)
                            
                            # print("veiculo_dados gerado:", veiculo_dados)


                            planilha=pd.DataFrame(veiculo_dados)
                            # await asyncio.sleep(3)
                            #await asyncio.sleep(60)
                            achou=1
                            print("veiculo ", num+1," de ",len(placa))
                        except:
                            try:
                                await page.refresh()
                                await asyncio.sleep(5)
                            
                                button_fecha_aviso = await page.find_element(By.XPATH,fecha_pup)
                                await button_fecha_aviso.click()
                            except:
                                await page.refresh()
                                await asyncio.sleep(5)
                    
                    # Os dados vão sendo adicionados à um dataframe externa que funcionará para o restante do script
                    planilhao=planilhao._append(planilha,ignore_index=True)

        # Caso nao tenha dados no dataframe, essa parte do código nao roda
        if len(planilhao)>0:
            planilhao.loc[~planilhao['Restricao Adm'].str.contains('ADM', na=False), 'Restricao Adm'] = 'Não'
            planilhao.loc[planilhao['Restricao Adm'].str.contains('ADM', na=False), 'Restricao Adm'] = 'Sim'
            # planilhao.loc[~planilhao['Gravame'].str.contains('ADM|Não', na=False), 'Gravame'] = 'Sim'
            # planilhao.loc[planilhao['Gravame'].str.contains('ADM|Não', na=False), 'Gravame'] = 'Não'
            planilhao.loc[planilhao['Gravame'].isna() | (planilhao['Gravame'] == '') | planilhao['Gravame'].str.contains('ADM|Não', na=False), 'Gravame'] = 'Não'
            planilhao.loc[~(planilhao['Gravame'].isna() | (planilhao['Gravame'] == '') | planilhao['Gravame'].str.contains('ADM|Não', na=False)), 'Gravame'] = 'Sim'

            # planilhao.to_excel(caminho_salvar + re.sub(r'\W+', '', planilhao['CNPJ'][0]) + '.xlsx',index=False)

            
            # await pdfs(planilhao,page)


        # async def pdfs(planilhao,page):
            # tabela_uf=pd.DataFrame(columns=['UF'])
            # tabela_chassi=pd.DataFrame(columns=['Chassi'])

            # ############# LER ARQUIVO PDF ##############

            # for placa_fipe in planilhao['Placa'].values:
            #     # Lista para armazenar os nomes dos arquivos que contêm o padrão
            #     # Encontre o arquivo PDF
            #     placa_fipe=re.sub(' ','',placa_fipe)
                
            #     try:
            #         # pdf_path = [file for file in glob(os.path.join(os.path.expanduser("~"), "Downloads", "*.pdf")) if placa_fipe in file][0]
            #         pdf_path = glob(os.path.join(os.path.expanduser("~"), "Downloads", f"*{placa_fipe}*.pdf"))[0]
                    
            #         # Abra o arquivo PDF
            #         with pdf.open(pdf_path) as arquivo_pdf:
            #             # Extraia o texto da primeira página
            #             texto = arquivo_pdf.pages[0].extract_text()
                        
            #         # Encontre e divida as informações
            #         chassi = re.findall(f'{placa_fipe}/(.+?)\n', texto)[0].split(' ')[1]
            #         uf = re.findall(r'([A-Za-z]{2})\s\d{2}/', texto)[0]
                    
            #         # Remova o arquivo PDF
            #         os.remove(pdf_path)
            #     except:
            #         uf=''
            #         chassi=''
                    
            #     tabela_uf = tabela_uf._append({'UF': uf}, ignore_index=True)
            #     tabela_chassi = tabela_chassi._append({'Chassi': chassi}, ignore_index=True)

            # planilhao=pd.concat([planilhao,tabela_uf,tabela_chassi],axis=1)

            
            #print(planilhao)

        #     await fipe(planilhao,page,browser)

        # async def fipe(planilhao,page,browser):

            

            tabela_fipe=pd.DataFrame(columns=['Tabela FIPE'])
            INFO_UF_FIPE=pd.DataFrame(columns=['INFO_UF_FIPE'])
            
            # O loop irá percorrer todas as placas contidas no Dataframe, e assim utilizando no site abaixo.
            
            for placa_fipe in planilhao['Placa'].values:
                
                # Antes de coletar os FIPEs, o script verificará se o mesmo já existe na base.
                # Como tem vezes que os cod fipe são diferentes, será retornado os que se repetem pelo menos 5 vezes dentro da base de dados
                # (na produção: SELECT PLACA, COD_FIPE, INFO_UF_FIPE, COUNT(COD_FIPE) ... GROUP BY ... HAVING COUNT(COD_FIPE) >= 5)
                cadsen = bd.ler("CADSEN")
                cadsen_placa = cadsen[(cadsen['PLACA'] == placa_fipe) & (cadsen['INFO_UF_FIPE'].fillna('') != '')]
                fipe_base = (cadsen_placa.groupby(['PLACA', 'COD_FIPE', 'INFO_UF_FIPE']).size()
                                         .reset_index(name='CONTAGEM'))
                fipe_base = fipe_base[fipe_base['CONTAGEM'] >= 5].reset_index(drop=True)
                
                if len(fipe_base)==1 and fipe_base['COD_FIPE'][0] != '0':
                    cod_fipe = fipe_base['COD_FIPE'][0]
                    cidade_uf = fipe_base['INFO_UF_FIPE'][0]

                else:
                    # await page.go_to('https://placafipe.com.br/')
                    # await asyncio.sleep(1)
                    # achou=0
                    # tentativas=1

                    # # Esse loop só irá rodar até 3 vezes por placa, caso presencie algum tipo de erro. Caso ultrapasse isso, Cod Fipe será 0
                    # while achou==0 and tentativas<=3:
                    #     try:
                    #         try:
                    #             banner_close = await page.find_element(
                    #                 By.XPATH,
                    #                 "//div[contains(@id,'sticky') and contains(@id,'close')]"
                    #             )
                    #             await banner_close.click()
                    #         except:
                    #             pass

                    #         campo_placa = await page.find_element(By.CSS_SELECTOR,'input')
                    #         await campo_placa.send_keys(re.sub(' ','',placa_fipe))
                    #         await asyncio.sleep(4)
                    #         button_pesquisa = await page.find_element(By.XPATH,'//*[@id="q-app"]/div/div[4]/main/div[1]/div[2]/div[2]/div[6]/button/span[2]')
                    #         await button_pesquisa.click()
                    #         await asyncio.sleep(5)

                    #         try:
                    #             # caso surja veículos que não são dos mesmos estados das empresas, esse campo deverá servir como pontapé inicial.
                    #             cidade_uf = await page.find_element(By.XPATH,'//*[@id="veiculo"]/div/div/div/div[1]/p[5]')
                    #             cidade_uf = await cidade_uf.get_element_text()
                                
                    #             cidade_uf = re.findall(r'-\s*([A-Z]{2})',cidade_uf)[0]
                    #             print(cidade_uf)
                    #         except:
                    #             cidade_uf = ''

                    #         cod_fipe = await page.find_element(By.XPATH,'//*[@id="valores"]/div/div/p[3]')
                    #         cod_fipe = await cod_fipe.get_element_text()
                    #         print(cod_fipe)
                    #         cod_fipe = re.findall(r'Cód. Fipe: (\d+-\d+)',cod_fipe)[0]
                            
                    #         achou=1

                    #     except:
                    #         tentativas+=1
                    #         if tentativas==3:
                    #             cod_fipe='0'
                    #         await page.refresh()
                    #         await asyncio.sleep(5)
                    linha_placa = planilhao.loc[planilhao['Placa'] == placa_fipe]

                    if linha_placa.empty:
                        continue

                    # cursor.execute(f''' SELECT DISTINCT C.MODELO, C.ANO, F.codeFipe FROM 
                    #                     (
                    #                     SELECT DISTINCT
                    #                         CASE 
                    #                             WHEN TIPO LIKE '%CAMINHAO%' THEN 'CAMINHAO'
                    #                             WHEN TIPO LIKE '%CAMIONETA%' THEN 'AUTOMOVEL'
                    #                             WHEN TIPO = 'UTILITARIO' THEN 'AUTOMOVEL'
                    #                             WHEN TIPO = 'CAMINHONETE' THEN 'AUTOMOVEL'
                    #                             ELSE TIPO
                    #                         END AS TIPO,
                                        
                    #                         REPLACE(
                    #                             CASE 
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'VW' AND TIPO LIKE '%CAMINHAO%' THEN 'VOLKSWAGEN' 
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'VW' AND TIPO NOT LIKE '%CAMINHAO%' THEN 'VW - VOLKSWAGEN'
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'CHEVROLET' AND TIPO IN ('AUTOMOVEL', 'UTILITARIO', 'CAMINHONETE') THEN 'GM - CHEVROLET'
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'CHEV' AND TIPO IN ('AUTOMOVEL', 'UTILITARIO', 'CAMINHONETE') THEN 'GM - CHEVROLET'
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'I' THEN SUBSTRING_INDEX(MODELO, ' ', 1)
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'M.BENZ' THEN 'MERCEDES-BENZ' 
                    #                                 WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'CITROEN' THEN 'CITROËN' 
                    #                                 ELSE SUBSTRING_INDEX(MODELO, '/', 1) 
                    #                             END,
                    #                             'I/', ''
                    #                         ) AS MARCA,
                                        
                    #                         CASE 
                    #                             WHEN MODELO_FIPE LIKE '%CONSTELLATION%'
                    #                             THEN REPLACE(MODELO_FIPE, '.', '-')
                    #                             ELSE MODELO_FIPE
                    #                         END AS MODELO,
                    #                         MODELO_FIPE,
                    #                         ANO
                                        
                    #                     FROM (
                    #                         SELECT
                    #                             TIPO,
                    #                             MODELO,
                    #                             ANO,
                                        
                    #                             REPLACE(
                    #                                 REPLACE(
                    #                                     CASE
                    #                                         WHEN SUBSTRING_INDEX(MODELO, '/', 1) = 'I' 
                    #                                             THEN SUBSTRING(MODELO, LOCATE(' ', MODELO) + 1)
                    #                                         ELSE SUBSTRING_INDEX(MODELO, '/', -1)
                    #                                     END,
                    #                                     'CNM',
                    #                                     'CONSTEL'
                    #                                 ),
                    #                                 'CRM',
                    #                                 'CONSTEL'
                    #                             ) AS MODELO_FIPE
                                        
                    #                         FROM cadsen
                    #                         WHERE TIPO NOT LIKE '%REBOQUE%'
                    #                     ) x) C
                    #                     LEFT JOIN TB_FIPE_CADSEN F ON F.TIPO = C.TIPO AND F.MARCA = C.MARCA AND F.MODELO = C.MODELO_FIPE
                    #                     WHERE REPLACE(C.MODELO, ' ', '')  LIKE REPLACE('{linha_placa['Modelo'].iloc[0]}', ' ', '') AND
                    #                           C.ANO =  {int(linha_placa['Ano'].iloc[0])}

                    #             ''')
                    
                    # col_fipe = pd.DataFrame(cursor.description)[0]
                    # fipe_base = pd.DataFrame(cursor.fetchall(),columns = col_fipe)

                    # if len(fipe_base) >= 1:
                    #     cod_fipe = fipe_base['codeFipe'][0]
                    #     cidade_uf = ''
                    # else:
                    #     cod_fipe = 0
                    #     cidade_uf = ''

                try:
                    cod_fipe = fipe_webhook(
                        linha_placa['Tipo'].iloc[0],
                        linha_placa['Modelo'].iloc[0],
                        linha_placa['Ano'].iloc[0]
                    )
                except Exception as e:
                    print(f"Erro ao consultar FIPE: {e}")
                    cod_fipe = None


                if(cod_fipe is None):
                    cod_fipe = 0
                    cidade_uf = ''
                else:
                    cidade_uf = ''

                tabela_fipe = tabela_fipe._append({'Tabela FIPE': cod_fipe}, ignore_index=True)
                INFO_UF_FIPE = INFO_UF_FIPE._append({'INFO_UF_FIPE': cidade_uf}, ignore_index=True)

            planilhao=pd.concat([planilhao,tabela_fipe,INFO_UF_FIPE],axis=1)
            # planilhao.to_excel(caminho_salvar + re.sub(r'\W+', '', planilhao['CNPJ'][0]) + '.xlsx',index=False)

            print(planilhao)
        
            # Essa parte do código deverá rodar o script DETRAN.py, que deve estar no mesmo diretório desse aqui.
            veiculos = await veic_detran(planilhao,cert,None,senha,loop)  # 3º parâmetro era o cursor do MySQL

            # veiculos = veiculos.reset_index(drop=True)
            print(veiculos)
            planilhao=pd.concat([planilhao,veiculos],axis=1)

            planilhao=planilhao[['CNPJ','UF','CNPJ_PROP','Placa','Tipo','Modelo','Ano Fabricação','Ano','Renavam','Carroceria','Chassi', 'Gravame','Gravame Pendente','Restricao Adm','RENAJUD',
                                'Processo','Tipo Restricao','Tribunal','Orgao','Total de Processos','Tabela FIPE',
                                'INFO_UF_FIPE','Debito Detran','Licenciamento','Multa','IPVA', 'IPVA Ant','Custo','Data execucao']]
            
            # planilhao.to_excel(caminho_salvar + re.sub(r'\W+', '', planilhao['CNPJ'][0]) + '.xlsx',index=False)
            
            
            # ALTERACOES NO BANCO DE DADOS
            
            # try:
            #     buscar_primeira_imagem(planilhao)
            # except:
            #     pass

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
                        "COD_FIPE": planilhao["Tabela FIPE"][linha],
                        "INFO_UF_FIPE": planilhao["INFO_UF_FIPE"][linha],
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
            # (na produção: cursor.close() / con.close())
            # if loop == num_empresas-1:
            #     browser.stop()
                # py.hotkey('alt','f4')

        hora_fim2 = datetime.now()

        print(str(hora_fim2-hora_ini2))

        
        await asyncio.sleep(5)
        # sys.exit()
# Executa o script

asyncio.run(main())
