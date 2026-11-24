
import time
from datetime import datetime
import pandas as pd
import os
from datetime import timezone
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
import requests
import re
from config import obter_credencial, MAPA_UF_EMPRESA, senha_do_certificado

    
hora_ini = datetime.now()
script_dir = os.path.dirname(os.path.abspath(__name__))
pasta_certificados = os.path.join(script_dir, "Certificados")

# Criando os dados
# Para o funcionamento completo dos dois códigos, a ordem das empresas deve ser a mesma ordem das opções de certificados instalados na máquina
senha = obter_credencial("SENHA_CERTIFICADO")  # senha padrão (vem de obter_credencial(), em config.py)

dados = []
max_socios = 0

# Mapa EMPRESA:CNPJ -> UF, usado quando a BrasilAPI não responde. Na produção é a lista
# das filiais do grupo; aqui vem do config.py, com empresas e CNPJs FICTÍCIOS.
mapa_uf = MAPA_UF_EMPRESA


for arquivo in os.listdir(pasta_certificados):
    if arquivo.lower().endswith(".pfx"):
        caminho_pfx = os.path.join(pasta_certificados, arquivo)
        senha = senha_do_certificado(caminho_pfx)
        try:
            with open(caminho_pfx, 'rb') as f:
                pfx_data = f.read()
            
            
            private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                pfx_data, senha.encode(), backend=default_backend()
            )

            if cert:
                validade = cert.not_valid_after_utc.replace(tzinfo=timezone.utc)
                agora = datetime.now(timezone.utc)

                if agora < validade:  # Só considera certificados ainda válidos
                    assunto = cert.subject.rfc4514_string()

                    # Extrair CNPJ
                    cnpj = re.search(r'\d{14}', assunto)[0]
                    
                    # Extrair empresa (primeiro = até ":")
                    empresa = re.search(r'=([^=]+?):', assunto)
                    
                    # Consultar UF via API
                    uf = ''
                    if cnpj:
                        url = f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}'
                        try:
                            response = requests.get(url, timeout=60)
                            dados_api = response.json()
                            
                            # socios_pf = [
                            #     socio["nome_socio"]
                            #     for socio in dados_api.get("qsa", [])
                            #     if not socio["cnpj_cpf_do_socio"].isdigit() or len(socio["cnpj_cpf_do_socio"]) != 14
                            # ]
                            
                            uf = dados_api.get('uf', '')
                        except:
                            uf = mapa_uf.get(f"{empresa.group(1).strip() if empresa else ''}:{cnpj}",'')
                    # Concatenar empresa - uf
                    # empresa_uf = f"{empresa.group(1).strip() if empresa else ''} - {uf}"
                    registro = {
                        'EMPRESA': f"{empresa.group(1).strip() if empresa else ''}:{cnpj}",
                        'CNPJ': cnpj or '',
                        'UF': uf,
                        'cert': caminho_pfx,
                        'validade': validade,
                        'validade_restante': validade - agora,
                    }
                    
                    # if len(socios_pf) > max_socios:
                    #     max_socios = len(socios_pf)
                        
                    # for i, socio in enumerate(socios_pf, start=1):
                    #     registro[f'socio_{i}'] = socio
                        
                    dados.append(registro)

        except Exception as e:
            print(f"Erro ao processar {arquivo}: {e}")


# Criar e ordenar DataFrame
df = pd.DataFrame(dados)
df = df.sort_values(by=['EMPRESA'], ascending=[True]).reset_index(drop=True)

# Criando o DataFrame
# empresas = pd.DataFrame(empresas)
empresas = df[['EMPRESA', 'UF', 'CNPJ', 'cert'] + [c for c in df.columns if c.startswith("socio")]]
print(empresas)

num_empresas = len(empresas) # O número de empresas serve para quantas vezes os códigos Optimus ou Megatron vão rodar

# Arquivo de controle manual: marque ATIVO como SIM ou NAO para cada empresa antes de rodar.
# Empresas que rodam 1x/mês ficam marcadas NAO na maioria dos dias; as de 2x/mês, SIM com mais frequência.
caminho_empresas_ativas = os.path.join(script_dir, "empresas_ativas.csv")

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
        # Empresa nova (certificado adicionado depois da última edição do CSV) entra como ativa por padrão
        return {empresa: mapa.get(empresa, True) for empresa in empresas_padrao}
    else:
        cfg = pd.DataFrame({'EMPRESA': empresas_padrao, 'ATIVO': 'SIM'})
        cfg.to_csv(caminho, sep=';', index=False)
        return {empresa: True for empresa in empresas_padrao}

empresas_ativas = carregar_empresas_ativas(caminho_empresas_ativas, empresas['EMPRESA'].tolist())

pos_empresa = 0
for loop in range(pos_empresa, num_empresas):
    # if empresas['UF'][loop] not in ('AL', 'MA', 'RJ', 'RN'):
    uf = empresas['UF'][loop]
    empresa_atual = empresas['EMPRESA'][loop]

    # 'loop' é a posição do certificado no seletor do navegador (Optimus/Megatron navegam por ela).
    # Por isso pulamos com 'continue' em vez de filtrar o DataFrame, para não deslocar os índices das demais empresas.
    if not empresas_ativas.get(empresa_atual, True):
        print(f"Empresa desmarcada para hoje (empresas_ativas.csv): {empresa_atual}")
        continue

    if isinstance(uf, str) and len(uf) == 2:
        print("Empresa ",loop+1, " de ",num_empresas)
        print(f'{empresas["EMPRESA"][loop]} - {empresas["UF"][loop]}')
        rodou=0
        cnpj = empresas["CNPJ"][loop]
        cert = empresas["cert"][loop]
        senha = senha_do_certificado(cert)

        # MEGATRON é o principal. OPTIMUS PRIME está desativado (comentado) por enquanto;
        # se ele voltar a ser necessário, é só descomentar o bloco abaixo.
        while rodou==0:
            try:
                with open(os.path.join(script_dir, "MEGATRON.py"), encoding='utf-8') as codigo_principal:
                    decepticon = codigo_principal.read()
                    exec(decepticon)
                    rodou=1
                    time.sleep(5)
            except Exception as e:
                print(f"Megatron deu erro: {e}")
                # try:
                #     with open(os.path.join(script_dir, "OPTIMUS PRIME.py"), encoding='utf-8') as codigo_principal:
                #         decepticon = codigo_principal.read()
                #         exec(decepticon)
                #         rodou=1
                #         time.sleep(5)
                # except Exception as e2:
                #     print(f"Optimus Prime deu erro: {e2}")
                #     rodou = 1
                #     time.sleep(5)
                rodou = 1
                time.sleep(5)

hora_fim = datetime.now()

print(str(hora_fim-hora_ini))
