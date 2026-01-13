import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, date
import time
import os
import random
import urllib.parse
import warnings
import urllib3
import json
from groq import Groq

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="ELOFLOW", layout="wide", page_icon="🦅")

# Ignorar avisos de SSL
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "false"

# --- 2. CSS VISUAL ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    .stApp { background-color: #050505; color: #E5E7EB; font-family: 'Inter', sans-serif; }
    div.stButton > button { background-color: #E31937; color: white; border: none; border-radius: 6px; font-weight: bold; }
    div.stButton > button:hover { background-color: #C2132F; border-color: #C2132F; }
    
    .metric-card {
        background-color: #151515; border: 1px solid #333; padding: 15px; 
        border-radius: 8px; border-left: 4px solid #E31937; margin-bottom: 10px;
    }
    .metric-card h3 { color: #888; font-size: 14px; margin: 0; }
    .metric-card h1 { color: #FFF; margin: 5px 0 0 0; }
    
    .foco-card {
        background-color: #151515 !important; padding: 20px; border-radius: 12px;
        border: 1px solid #333; border-left: 6px solid #E31937; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .foco-grid { display: flex; flex-direction: column; gap: 10px; margin-top: 15px; font-size: 14px; }
    .foco-item {
        background-color: #252525 !important; color: #FFFFFF !important; padding: 10px 14px;
        border-radius: 6px; border: 1px solid #3a3a3a; display: flex; justify-content: space-between;
    }
    .foco-item b { color: #E31937 !important; margin-right: 10px; min-width: 80px; text-transform: uppercase; font-size: 11px; }
    
    .script-box {
        background-color: #2A1015 !important; padding: 12px; border-radius: 8px; margin-top: 15px;
        border: 1px solid #333; border-left: 4px solid #E31937; color: #E0E0E0 !important; font-style: italic; font-size: 13px;
    }
    .sugestao-box {
        background-color: #2D2006 !important; border: 1px solid #B45309; border-radius: 8px;
        padding: 12px; margin-top: 15px;
    }
    .sku-item {
        background-color: rgba(251, 191, 36, 0.15); color: #FCD34D !important;
        padding: 4px 8px; border-radius: 4px; margin-bottom: 4px; font-size: 13px;
        border: 1px solid rgba(251, 191, 36, 0.2);
    }
    span[data-baseweb="tag"] { background-color: #333 !important; }
    
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. VARIÁVEIS DE AMBIENTE ---
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://elo-flow-eloflowdirectus-a9lluh-7f4d22-152-53-165-62.traefik.me")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") 

# Configuração do Cliente Groq
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        st.error(f"Erro ao configurar Groq: {e}")

# =========================================================
#  FUNÇÕES AUXILIARES E DE NEGÓCIO
# =========================================================

def limpar_telefone(phone):
    if pd.isna(phone): return None
    return "".join(filter(str.isdigit, str(phone)))

def gerar_sugestoes_elo_brindes(area_atuacao):
    if not groq_client:
        return ["🎁 Kit Boas Vindas Personalizado", "🎁 Caneta Metal Premium", "🎁 Caderno Moleskine com Logo"], "Sugestão Padrão (Sem IA)"
    
    try:
        prompt = f"""
        Você é um consultor especialista da Elo Brindes (www.elobrindes.com.br).
        O cliente atua na área: '{area_atuacao}'.
        Sugira 3 brindes corporativos personalizados do catálogo da Elo Brindes que façam sentido para este ramo.
        Responda EXATAMENTE no formato: Produto A|Produto B|Produto C
        Não use introduções, apenas os nomes dos produtos.
        """
        
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        
        texto = chat_completion.choices[0].message.content.strip()
        
        if "|" in texto:
            produtos = texto.split("|")
            produtos_fmt = [f"📦 {p.strip().replace('📦', '')}" for p in produtos[:3]]
            return produtos_fmt, f"Sugestão IA (Baseada em {area_atuacao})"
        else:
            return [f"📦 {texto}"], "Sugestão IA"
    except Exception:
        return ["🎁 Garrafa Térmica Personalizada", "🎁 Mochila Executiva", "🎁 Kit Tecnológico (Powerbank)"], "Sugestão Geral (Erro IA)"

# =========================================================
#  FUNÇÕES DE BACKEND
# =========================================================

def validar_token_existente(token):
    """Verifica se um token salvo ainda é válido"""
    base_url = DIRECTUS_URL.rstrip('/')
    try:
        r = requests.get(
            f"{base_url}/users/me", 
            headers={"Authorization": f"Bearer {token}"}, 
            timeout=5, 
            verify=False
        )
        if r.status_code == 200:
            return r.json()['data']
    except: pass
    return None

def login_directus_debug(email, password):
    base_url = DIRECTUS_URL.rstrip('/')
    try:
        response = requests.post(
            f"{base_url}/auth/login", 
            json={"email": email, "password": password}, 
            timeout=15, 
            verify=False 
        )
    except Exception as e:
        st.error(f"❌ Erro de Conexão: {e}")
        return None, None

    if response.status_code == 401:
        st.error("🔒 E-mail ou Senha incorretos.")
        return None, None
    
    if response.status_code == 200:
        token = response.json()['data']['access_token']
        try:
            user_resp = requests.get(
                f"{base_url}/users/me", 
                headers={"Authorization": f"Bearer {token}"}, 
                timeout=10, 
                verify=False
            )
            if user_resp.status_code == 200:
                return token, user_resp.json()['data']
        except: pass
        return token, {} 
    
    st.error(f"❌ Erro: {response.text}")
    return None, None

def alterar_senha_directus(token, nova_senha):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.patch(
            f"{base_url}/users/me",
            json={"password": nova_senha},
            headers=headers,
            verify=False
        )
        if r.status_code == 200:
            return True, "Senha alterada com sucesso."
        else:
            return False, f"Erro Directus: {r.text}"
    except Exception as e:
        return False, str(e)

def carregar_clientes(token):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}"}
    
    # CAMPOS COMPLETOS
    fields_full = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj,tentativa_1,tentativa_2,tentativa_3,status_prospect,email_2,representante_nome,representante_email"
    fields_safe = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj,status_prospect,email_2,representante_nome,representante_email"
    
    df = pd.DataFrame()
    colunas_faltantes = False

    try:
        url = f"{base_url}/items/clientes?limit=-1&fields={fields_full}"
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        
        if r.status_code == 200:
            df = pd.DataFrame(r.json()['data'])
        else:
            colunas_faltantes = True
            url_safe = f"{base_url}/items/clientes?limit=-1&fields={fields_safe}"
            r_safe = requests.get(url_safe, headers=headers, timeout=10, verify=False)
            if r_safe.status_code == 200:
                df = pd.DataFrame(r_safe.json()['data'])
                df['tentativa_1'] = None
                df['tentativa_2'] = None
                df['tentativa_3'] = None

        if not df.empty:
            df['data_temp'] = pd.to_datetime(df['data_ultima_compra'], errors='coerce')
            df['Ultima_Compra'] = df['data_temp'].dt.strftime('%d/%m/%Y').fillna("-")
            hoje = pd.Timestamp.now()
            df['dias_sem_compra'] = (hoje - df['data_temp']).dt.days.fillna(9999).astype(int)
            
            if 'status_prospect' not in df.columns:
                df['status_prospect'] = None
            
            # Garantir colunas novas
            for col_nova in ['email_2', 'representante_nome', 'representante_email']:
                if col_nova not in df.columns:
                    df[col_nova] = None
            
            def definir_cat(row):
                if 'status_carteira' in row and row['status_carteira']: return row['status_carteira']
                dias = row['dias_sem_compra']
                if dias > 365: return "Crítico"
                if dias > 180: return "Inativo"
                return "Ativo"
            
            df['Categoria_Cliente'] = df.apply(definir_cat, axis=1)
            df['GAP (dias)'] = df['dias_sem_compra']
            
            for col in ['tentativa_1', 'tentativa_2', 'tentativa_3']:
                df[col] = df[col].fillna("")

            if colunas_faltantes:
                st.toast("⚠️ Aviso: Colunas de 'Tentativa' não encontradas no Directus.", icon="⚠️")
                
            return df
            
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        
    return pd.DataFrame()

def atualizar_cliente_directus(token, id_cliente, dados_atualizados):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.patch(
            f"{base_url}/items/clientes/{id_cliente}",
            json=dados_atualizados,
            headers=headers,
            verify=False
        )
        return r.status_code == 200
    except:
        return False

def carregar_campanha_ativa(token):
    try:
        base_url = DIRECTUS_URL.rstrip('/')
        r = requests.get(
            f"{base_url}/items/campanhas_vendas?filter[ativa][_eq]=true&limit=1", 
            headers={"Authorization": f"Bearer {token}"}, 
            verify=False
        )
        if r.status_code == 200 and r.json()['data']:
            return r.json()['data'][0]
    except: pass
    return None

def config_smtp_crud(token, user_email, payload=None):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # URL BASE e URL COM FILTRO PELO E-MAIL DO VENDEDOR
    # Isso evita sobrescrever a config de outro usuário
    url_base = f"{base_url}/items/config_smtp"
    url_filter = f"{url_base}?filter[vendedor_email][_eq]={user_email}"

    if payload:
        # 1. Tenta achar se já existe config para este vendedor
        try:
            check = requests.get(url_filter, headers=headers, verify=False)
        except Exception as e:
            st.error(f"❌ Erro de conexão com Directus: {e}")
            return False

        if check.status_code != 200:
            st.error(f"❌ Erro ao acessar configurações no banco: {check.text}")
            return False

        data = check.json().get('data', [])
        
        if len(data) > 0:
            # ATUALIZAR (PATCH) no ID específico
            id_item = data[0]['id']
            r = requests.patch(f"{url_base}/{id_item}", json=payload, headers=headers, verify=False)
            if r.status_code == 200:
                return True
            else:
                st.error(f"❌ Erro ao salvar (PATCH). O Directus recusou: {r.text}")
                return False
        else:
            # CRIAR (POST) vinculando ao email
            payload['vendedor_email'] = user_email
            r = requests.post(url_base, json=payload, headers=headers, verify=False)
            if r.status_code == 200:
                return True
            else:
                st.error(f"❌ Erro ao criar (POST). O Directus recusou: {r.text}")
                return False
    else:
        # LEITURA
        try:
            r = requests.get(url_filter, headers=headers, verify=False)
            if r.status_code == 200 and r.json().get('data'): 
                return r.json()['data'][0]
        except: pass
        return None

def enviar_email_smtp(token, destinatario, assunto, mensagem_html, conf_smtp, arquivo_anexo=None):
    if not conf_smtp: return False, "SMTP não configurado"
    try:
        msg = MIMEMultipart()
        msg['From'] = conf_smtp['smtp_user']
        msg['To'] = destinatario
        msg['Subject'] = assunto
        
        if "<div" in mensagem_html or "<html" in mensagem_html or "<span" in mensagem_html or "<table" in mensagem_html or "<a href" in mensagem_html:
            corpo_completo = mensagem_html
        else:
            corpo_completo = mensagem_html.replace("\n", "<br>")
            
        if conf_smtp.get('assinatura_html') and "</body>" not in corpo_completo:
            corpo_completo += f"<br><br>{conf_smtp['assinatura_html']}"
            
        msg.attach(MIMEText(corpo_completo, 'html'))
        
        # --- LOGICA DE ANEXO ---
        if arquivo_anexo is not None:
            # Cria a parte do anexo
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(arquivo_anexo.getvalue()) # Le os bytes do arquivo
            encoders.encode_base64(part) # Codifica
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{arquivo_anexo.name}"'
            )
            msg.attach(part)
        
        server = smtplib.SMTP(conf_smtp['smtp_host'], conf_smtp['smtp_port'])
        server.starttls()
        server.login(conf_smtp['smtp_user'], conf_smtp['smtp_pass_app'])
        server.sendmail(conf_smtp['smtp_user'], destinatario, msg.as_string())
        server.quit()
        return True, "Enviado"
    except Exception as e:
        return False, str(e)

def registrar_log(token, pj_id, assunto, corpo, status):
    try:
        base_url = DIRECTUS_URL.rstrip('/')
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        # CORREÇÃO: Usar formato de data simples para compatibilidade com Directus
        data_formatada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        payload = {
            "cliente_pj_id": str(pj_id), 
            "assunto_gerado": assunto, 
            "corpo_email": corpo, 
            "status_envio": status, 
            "data_envio": data_formatada
        }
        requests.post(f"{base_url}/items/historico_envios", json=payload, headers=headers, verify=False)
    except: pass

def contar_envios_hoje_directus(token):
    """
    Conta quantos registros existem na tabela 'historico_envios' com a data de hoje.
    Usado para garantir a cota de segurança e evitar spam.
    """
    try:
        base_url = DIRECTUS_URL.rstrip('/')
        hoje_str = datetime.now().strftime("%Y-%m-%d")
        
        # CORREÇÃO: Usar _starts_with em vez de _contains para garantir que datas com hora sejam contadas
        url = f"{base_url}/items/historico_envios?filter[data_envio][_starts_with]={hoje_str}&aggregate[count]=*"
        
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, verify=False)
        
        if r.status_code == 200:
            data = r.json()['data']
            # O Directus retorna agregação como uma lista de objetos
            if isinstance(data, list) and len(data) > 0:
                return int(data[0].get('count', 0))
            return 0
    except Exception as e:
        return 0
    return 0

def gerar_email_ia(nome_destinatario, ramo, data_compra, campanha, usuario_nome, usuario_cargo):
    if not groq_client: return "Erro IA", "Sem Chave API configurada"
    camp_nome = campanha.get('nome_campanha', 'Retomada') if campanha else 'Contato'
    
    # PROMPT ATUALIZADO PARA HUMANO + 3 BRINDES + LINKS
    prompt = f"""
    Aja como {usuario_nome}, da Elo Brindes.
    Escreva um e-mail curto e direto para {nome_destinatario} (Setor: {ramo}).
    
    Contexto: Cliente inativo desde {data_compra}.
    Objetivo: Mostrar novidades e levar para o site.

    REGRAS DE TOM DE VOZ (HUMANO):
    1. Seja casual, mas profissional. Evite "Prezado(a)" ou linguagem muito formal. Use "Olá".
    2. Seja breve. Ninguém lê e-mails longos.
    3. Nada de robótico. Escreva como se estivesse falando com um colega.

    CONTEÚDO OBRIGATÓRIO:
    1. Diga que estava revisando a carteira e lembrou deles.
    2. Sugira 3 categorias de brindes ESPECÍFICAS para o setor de {ramo}. 
    3. Para cada sugestão, tente inventar um link de busca simples no formato: (www.elobrindes.com.br/?s=produto)
    4. Encerre com um CTA leve: "Dá uma olhada no site ou me chama aqui se precisar de algo."
    
    SAÍDA ESPERADA:
    Assunto: Ideias para a {ramo}|||Olá {nome_destinatario}, tudo bem?

    Estava aqui revisando alguns parceiros antigos e lembrei de vocês. Faz um tempo que não nos falamos!

    Separei algumas novidades que têm saído muito para o setor de {ramo}:

    - [Sugestão 1] (Link: www.elobrindes.com.br/?s=sugestao1)
    - [Sugestão 2] (Link: www.elobrindes.com.br/?s=sugestao2)
    - [Sugestão 3] (Link: www.elobrindes.com.br/?s=sugestao3)

    Se precisar de cotação ou quiser ver mais opções, é só me chamar.

    Abraço,
    """
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        
        txt = chat_completion.choices[0].message.content.strip()
        
        assunto = "Contato Elo Brindes"
        corpo = txt
        
        if "|||" in txt:
            partes = txt.split("|||", 1)
            assunto = partes[0].replace("Assunto:", "").strip()
            corpo = partes[1].strip()
            
        return assunto, corpo
    except Exception as e: return "Erro", str(e)

# =========================================================
#  INTERFACE (STREAMLIT)
# =========================================================

# --- TENTATIVA DE RECUPERAR SESSÃO (F5 / REFRESH) ---
if 'token' not in st.session_state:
    try:
        token_url = st.query_params.get("token")
        
        if token_url:
            user_data = validar_token_existente(token_url)
            if user_data:
                st.session_state['token'] = token_url
                st.session_state['user'] = user_data
            else:
                st.query_params.clear()
    except: pass

# --- GARANTIA DE PERSISTÊNCIA NA URL ---
if 'token' in st.session_state:
    st.query_params["token"] = st.session_state['token']

if 'token' not in st.session_state:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br><h1 style='text-align:center; color:#E31937'>🦅 ELOFLOW</h1>", unsafe_allow_html=True)
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        if st.button("ENTRAR", use_container_width=True):
            token, user = login_directus_debug(email, senha)
            if token:
                st.session_state['token'] = token
                st.session_state['user'] = user
                st.query_params["token"] = token
                st.rerun()
    st.stop()

token = st.session_state['token']
user = st.session_state['user']

nome_usuario = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
primeiro_nome = user.get('first_name', '').strip().lower()
cargo_usuario = "Vendedora" if primeiro_nome.endswith("a") else "Vendedor"
user_email = user.get('email', '')

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"<h2 style='color: #E31937; text-align: center;'>🦅 ELO FLOW</h2>", unsafe_allow_html=True)
    st.write(f"👤 **{nome_usuario}**")
    st.caption(f"💼 {cargo_usuario}")
    if st.button("Sair"):
        st.session_state.clear()
        st.query_params.clear() 
        st.rerun()
    
    st.divider()

    with st.expander("🔐 Alterar Senha", expanded=False):
        form_senha = st.form("form_change_pw")
        with form_senha:
            nova_pw1 = st.text_input("Nova Senha", type="password")
            nova_pw2 = st.text_input("Confirmar Nova Senha", type="password")
            btn_salvar_senha = st.form_submit_button("Atualizar Senha", use_container_width=True)
        
        if btn_salvar_senha:
            if not nova_pw1 or not nova_pw2:
                st.error("Preencha os campos.")
            elif nova_pw1 != nova_pw2:
                st.error("As senhas não conferem.")
            elif len(nova_pw1) < 5:
                st.error("A senha deve ter no mínimo 5 caracteres.")
            else:
                ok_pw, msg_pw = alterar_senha_directus(token, nova_pw1)
                if ok_pw:
                    st.success("✅ Senha alterada! Faça login novamente.")
                    time.sleep(2)
                    st.session_state.clear()
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error(f"Erro: {msg_pw}")

    st.divider()

    with st.expander("📘 MANUAL DE USO (Leia Antes)", expanded=False):
        st.markdown("""
        ### 🎯 Resumo do ELOFLOW
        Este sistema foi desenhado para **vendas de precisão** e **disparos seguros**.

        #### 1. 📢 Disparo em Massa (Modo Sniper)
        Para evitar que o Google bloqueie seu e-mail:
        * **Limite:** 100 e-mails por dia (Cota da Equipe).
        * **Lentidão Proposital:** O sistema espera **15 a 45 segundos** aleatoriamente entre cada envio. Isso "engana" o Google para parecer um humano.
        * **Recomendação:** Selecione no máximo **20 clientes** por vez e deixe a aba aberta trabalhando.

        #### 2. 🚀 Modo de Ataque (Um a Um)
        * Ideal para recuperar clientes inativos.
        * **IA Mágica:** Gera um e-mail ultra-personalizado baseado no Ramo e na última compra.
        * **WhatsApp:** Gera link direto com script de abordagem.

        #### 3. 📋 Edição Rápida
        * A tabela no final da página funciona como Excel.
        * Edite o "Status Prospecção" ou "Obs" e clique fora. O sistema salva sozinho (aparece um aviso ✅).
        * Selecione quais colunas quer ver no filtro acima da tabela.

        #### ⚠️ Configuração Obrigatória
        Antes de enviar e-mails, vá em **⚙️ Configurar E-mail** abaixo e coloque sua **Senha de Aplicativo** (Não é a senha do email normal!).
        """)
    
    st.divider()
    
    with st.expander("⚙️ Configurar E-mail (SMTP)"):
        st.info("Necessário para o DISPARO EM MASSA.")
        conf = config_smtp_crud(token, user_email)
        
        h = st.text_input("Host", value=conf['smtp_host'] if conf else "smtp.gmail.com")
        p = st.number_input("Porta", value=conf['smtp_port'] if conf else 587)
        u = st.text_input("Email", value=conf['smtp_user'] if conf else "")
        
        pw_val = conf['smtp_pass_app'] if conf else ""
        pw = st.text_input("Senha App (Não use senha de login)", type="password", value=pw_val, help="Para Gmail, crie uma Senha de App.")
        
        ass = st.text_area("Assinatura HTML", value=conf['assinatura_html'] if conf else "")
        
        if st.button("Salvar Configuração", type="primary"):
            if not u or not pw:
                st.warning("Preencha E-mail e Senha.")
            else:
                payload = {
                    "smtp_host": h, 
                    "smtp_port": int(p), 
                    "smtp_user": u, 
                    "smtp_pass_app": pw, 
                    "assinatura_html": ass
                }
                salvou = config_smtp_crud(token, user_email, payload)
                if salvou:
                    st.success("✅ Salvo com sucesso! Recarregando...")
                    time.sleep(1.5)
                    st.rerun()

# --- CORPO PRINCIPAL ---

df = carregar_clientes(token)
campanha = carregar_campanha_ativa(token)

if df.empty:
    st.warning("⚠️ Sua carteira está vazia ou falha ao carregar.")
    st.stop()

st.title(f"Visão Geral - {nome_usuario}")
k1, k2, k3 = st.columns(3)
k1.markdown(f"<div class='metric-card'><h3>Total Clientes</h3><h1>{len(df)}</h1></div>", unsafe_allow_html=True)
inativos = len(df[df['Categoria_Cliente'].astype(str).str.contains('Inativo|Frio|Crítico', case=False)])
k2.markdown(f"<div class='metric-card'><h3>Oportunidades (Inativos/Crít.)</h3><h1 style='color:#E31937'>{inativos}</h1></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='metric-card'><h3>Campanha</h3><h4>{campanha['nome_campanha'] if campanha else 'Nenhuma'}</h4></div>", unsafe_allow_html=True)

# --- FILTROS GLOBAIS ---
st.markdown("### 🔍 Filtros Globais")
c_f1, c_f2 = st.columns(2)
with c_f1:
    opcoes_status = sorted(list(df['Categoria_Cliente'].unique()))
    todos_status = st.checkbox("Todos os Status", value=True)
    if todos_status:
        filtro_status = st.multiselect("Filtrar por Status (Carteira):", options=opcoes_status, default=opcoes_status)
    else:
        filtro_status = st.multiselect("Filtrar por Status (Carteira):", options=opcoes_status)

with c_f2:
    opcoes_area = sorted([str(x) for x in df['area_atuacao'].unique() if x is not None])
    todas_areas = st.checkbox("Todas as Áreas", value=True)
    if todas_areas:
        filtro_area = st.multiselect("Filtrar por Área de Atuação:", options=opcoes_area, default=opcoes_area)
    else:
        filtro_area = st.multiselect("Filtrar por Área de Atuação:", options=opcoes_area)

df_filtrado = df.copy()
if filtro_status:
    df_filtrado = df_filtrado[df_filtrado['Categoria_Cliente'].isin(filtro_status)]
if filtro_area:
    df_filtrado = df_filtrado[df_filtrado['area_atuacao'].astype(str).isin(filtro_area)]

if not df_filtrado.empty:
    df_filtrado['label_select'] = df_filtrado['razao_social'] + " (" + df_filtrado['Ultima_Compra'] + ")"

# --- GATILHO DE SELEÇÃO PELA TABELA ---
if "editor_dados" in st.session_state:
    changes = st.session_state["editor_dados"]["edited_rows"]
    for idx, val in changes.items():
        if val.get("Ação") is True:
            try:
                cliente_alvo = df_filtrado.iloc[int(idx)]['label_select']
                if st.session_state.get("sb_principal") != cliente_alvo:
                    st.session_state["sb_principal"] = cliente_alvo
            except Exception: pass

st.divider()

# --- BLOCO: DISPARO EM MASSA SEGURO ---
with st.expander("📢 Disparo em Massa (Modo Sniper 🎯)", expanded=False):
    st.markdown("⚠️ **Regras de Segurança:** O sistema envia 1 e-mail a cada **15~45 segundos** para evitar bloqueios do Google.")
    
    # 1. VERIFICAÇÃO DE COTA DIÁRIA (COM ATUALIZAÇÃO VISUAL)
    cota_maxima = 100
    envios_hoje = contar_envios_hoje_directus(token)
    
    # Placeholder para permitir atualização da cota em tempo real
    cota_container = st.empty()
    
    def render_cota(enviados_sessao=0):
        total_real = envios_hoje + enviados_sessao
        saldo_real = cota_maxima - total_real
        with cota_container.container():
            col_cota1, col_cota2 = st.columns([3, 1])
            with col_cota1:
                st.progress(min(total_real / cota_maxima, 1.0), text=f"Cota Diária da Equipe: {total_real}/{cota_maxima} envios hoje")
            with col_cota2:
                if saldo_real <= 0:
                    st.error("⛔ Cota Atingida!")
                else:
                    st.success(f"✅ {saldo_real} livres")
    
    # Renderiza estado inicial
    render_cota(0)

    st.divider()

    col_m1, col_m2 = st.columns([1, 1])
    
    with col_m1:
        st.subheader("1. Selecione os Clientes")
        
        # Filtra empresas com e-mail válido
        mask_email = (
            df_filtrado['email_1'].str.contains('@', na=False) | 
            df_filtrado['email_2'].str.contains('@', na=False) | 
            df_filtrado['representante_email'].str.contains('@', na=False)
        )
        df_com_email = df_filtrado[mask_email].copy()
        lista_clientes_validos = df_com_email['label_select'].tolist()
        
        container_botoes = st.container()
        col_b1, col_b2 = container_botoes.columns(2)
        
        # Botões de seleção rápida
        if col_b1.button("Selecionar Próximos 20"):
            if 'status_prospect' in df_com_email.columns:
                pendentes = df_com_email[df_com_email['status_prospect'] != 'Contato Feito']
                if pendentes.empty:
                    candidatos = lista_clientes_validos
                else:
                    candidatos = pendentes['label_select'].tolist()
            else:
                candidatos = lista_clientes_validos
                
            st.session_state['selected_bulk'] = candidatos[:20]

        if col_b2.button("Limpar Seleção"):
            st.session_state['selected_bulk'] = []
            
        selecionados_bulk = st.multiselect(
            "Clientes Destinatários:", 
            options=lista_clientes_validos,
            key='selected_bulk'
        )
        
        qtd_selecionada = len(selecionados_bulk)
        saldo_atual = cota_maxima - envios_hoje
        
        st.caption(f"Selecionados: {qtd_selecionada} empresas")

        # Alertas de quantidade
        if qtd_selecionada > 20:
            st.error("⛔ Limite de 20 envios por vez. Reduza a seleção.")
        elif qtd_selecionada > saldo_atual:
            st.error(f"⛔ Você selecionou {qtd_selecionada}, mas só tem {saldo_atual} envios restantes hoje.")

    with col_m2:
        st.subheader("2. Defina a Mensagem")
        assunto_padrao = st.text_input("Assunto do E-mail", value=f"Novidades Elo Brindes - {campanha['nome_campanha'] if campanha else 'Especial'}")
        
        st.info("💡 Dica: Use a tabela HTML simples para evitar quebras no Outlook.")
        corpo_padrao = st.text_area("Mensagem ou Código HTML", height=300, value=f"Olá,\n\nGostaria de apresentar as novidades da Elo Brindes para sua empresa.\n\nAguardo seu retorno.")
        
        # --- CAMPO DE ANEXO (NOVO) ---
        arquivo_para_anexo = st.file_uploader("Anexar Arquivo (Opcional)", type=['png', 'jpg', 'jpeg', 'pdf'])
        
        # TRAVA O BOTÃO SE ESTIVER SEM SALDO OU ACIMA DE 20
        botao_disabled = (saldo_atual <= 0) or (qtd_selecionada == 0) or (qtd_selecionada > saldo_atual) or (qtd_selecionada > 20)
        
        if st.button("🚀 INICIAR DISPARO SEGURO", type="primary", use_container_width=True, disabled=botao_disabled):
            conf_smtp = config_smtp_crud(token, user_email)
            
            if not conf_smtp or not conf_smtp.get('smtp_pass_app'):
                st.error("🚨 Configure o SMTP na barra lateral primeiro!")
            else:
                st.write("---")
                status_box = st.status("🦅 Iniciando sequência de envio...", expanded=True)
                bar = st.progress(0)
                
                enviados = 0
                erros = 0
                log_erros = []
                total_empresas = len(selecionados_bulk)
                
                for i, nome_cliente in enumerate(selecionados_bulk):
                    # --- PAUSA DE SEGURANÇA (RANDOMICA) ---
                    # Pula o delay no primeiro email, aplica nos seguintes
                    if i > 0:
                        tempo_espera = random.randint(15, 45) # ENTRE 15 e 45 SEGUNDOS
                        status_box.update(label=f"⏳ Aguardando {tempo_espera}s para parecer humano (Google Anti-Spam)...", state="running")
                        time.sleep(tempo_espera)
                    
                    # --- PREPARAÇÃO DO EMAIL ---
                    cli_row = df_com_email[df_com_email['label_select'] == nome_cliente].iloc[0]
                    
                    # Formatação de Nome
                    nome_base = str(cli_row['razao_social'])
                    if cli_row.get('representante_nome') and str(cli_row.get('representante_nome')).lower() not in ['none', '', 'nan']:
                        nome_base = str(cli_row['representante_nome'])
                    primeiro_nome_formatado = nome_base.split()[0].title() if nome_base else ""
                    
                    # Substituição no texto
                    msg_final = corpo_padrao.replace("{cliente}", primeiro_nome_formatado)
                    
                    # Coleta destinatários
                    destinatarios = []
                    if cli_row['representante_email'] and "@" in str(cli_row['representante_email']):
                        destinatarios.append({'email': cli_row['representante_email'], 'tipo': 'Representante'})
                    if cli_row['email_1'] and "@" in str(cli_row['email_1']):
                         destinatarios.append({'email': cli_row['email_1'], 'tipo': 'Principal'})
                    if cli_row['email_2'] and "@" in str(cli_row['email_2']):
                        destinatarios.append({'email': cli_row['email_2'], 'tipo': 'Secundário'})

                    # --- ENVIO ---
                    status_box.write(f"📤 Enviando para **{cli_row['razao_social']}**...")
                    
                    email_enviado_para_cliente = False # Flag para saber se enviou pelo menos 1
                    
                    for dest in destinatarios:
                        # Passa o anexo se existir
                        sucesso, msg_log = enviar_email_smtp(token, dest['email'], assunto_padrao, msg_final, conf_smtp, arquivo_anexo=arquivo_para_anexo)
                        
                        # LOG NO DIRECTUS (CRÍTICO PARA CONTAGEM)
                        status_envio_db = "Enviado" if sucesso else f"Erro: {msg_log}"
                        registrar_log(token, cli_row['pj_id'], assunto_padrao, f"Para: {dest['email']}", status_envio_db)

                        if sucesso:
                            email_enviado_para_cliente = True
                            enviados += 1
                            # ATUALIZA A BARRA DE COTA VISUALMENTE AGORA
                            render_cota(enviados)
                        else:
                            erros += 1
                            log_erros.append(f"{cli_row['razao_social']} ({dest['email']}): {msg_log}")
                    
                    # --- ATUALIZAÇÃO AUTOMÁTICA DO STATUS ---
                    if email_enviado_para_cliente:
                        dados_update = {"status_prospect": "Contato Feito"}
                        
                        # Mantém a lógica da tentativa_1 se estiver vazia
                        if not cli_row['tentativa_1']:
                            dados_update["tentativa_1"] = datetime.now().strftime("%d/%m - Email em Massa")
                        
                        atualizar_cliente_directus(token, cli_row['id'], dados_update)
                    
                    bar.progress((i + 1) / total_empresas)
                
                status_box.update(label="✅ Finalizado!", state="complete", expanded=False)
                
                if enviados > 0:
                    st.success(f"Processo finalizado! {enviados} e-mails enviados.")
                    st.balloons()
                    time.sleep(3)
                    st.rerun() # Recarrega para atualizar a cota
                
                if erros > 0:
                    st.error(f"Ocorreram {erros} erros. Verifique o console.")

st.divider()

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("🚀 Modo de Ataque (Vendas)")
    if not df_filtrado.empty:
        opcoes = sorted(df_filtrado['label_select'].tolist())
        
        if "sb_principal" not in st.session_state:
            st.session_state["sb_principal"] = "Selecione..."
        if st.session_state["sb_principal"] not in (["Selecione..."] + opcoes):
             st.session_state["sb_principal"] = "Selecione..."

        selecionado = st.selectbox(
            "Busque Cliente (Filtrado):", 
            ["Selecione..."] + opcoes, 
            key="sb_principal" 
        )

        if selecionado and selecionado != "Selecione...":
            cli = df_filtrado[df_filtrado['label_select'] == selecionado].iloc[0]
            dias = cli['dias_sem_compra']
            area_cli = str(cli['area_atuacao'])
            tel_raw = str(cli['telefone_1'])
            email_cli = str(cli['email_1'])
            tel_clean = limpar_telefone(tel_raw)
            
            rep_nome = cli.get('representante_nome')
            rep_email = cli.get('representante_email')
            email2 = cli.get('email_2')
            
            # --- LÓGICA DE PRIORIDADE E FORMATAÇÃO PARA MODO ATAQUE ---
            nome_para_ia = ""
            email_para_ia = ""
            
            # 1. Escolhe o nome base (Rep ou Razao)
            if rep_nome and str(rep_nome).strip() != "" and str(rep_nome).lower() != "none":
                nome_base_atk = rep_nome
            else:
                nome_base_atk = cli['razao_social']
            
            # 2. Formata (Caio)
            nome_para_ia = str(nome_base_atk).split()[0].title()
            
            # 3. Escolhe o e-mail
            if rep_email and "@" in str(rep_email):
                email_para_ia = rep_email
            else:
                email_para_ia = email_cli

            with st.spinner("🦅 Consultando catálogo Elo Brindes..."):
                 sugestoes, motivo_sugestao = gerar_sugestoes_elo_brindes(area_cli)
                 
            html_sugestoes = "".join([f"<div class='sku-item'>{s}</div>" for s in sugestoes])
            script_msg = f"Olá! Sou da Elo Brindes. Vi que sua última compra foi há {dias} dias. Temos novidades personalizadas para {area_cli}."
            
            html_card = f"""
            <div class="foco-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2 style='margin:0; color: #FFF; font-size: 20px;'>🏢 {cli['razao_social'][:25]}...</h2>
                    <span style='background:#333; padding:2px 6px; border-radius:4px; font-size:11px; color:#aaa;'>ID: {cli['pj_id']}</span>
                </div>
                <div class="foco-grid">
                    <div class="foco-item"><b>📍 Área</b>{area_cli}</div>
                    <div class="foco-item"><b>📞 Tel</b>{tel_raw}</div>
                    <div class="foco-item"><b>📧 Email</b>{email_cli[:25]}...</div>
                    <div class="foco-item"><b>📧 Email 2</b>{email2 if email2 else '-'}</div>
                    <div class="foco-item"><b>👤 Rep.</b>{rep_nome if rep_nome else '-'}</div>
                    <div class="foco-item"><b>📧 Rep. Email</b>{rep_email if rep_email else '-'}</div>
                    <div class="foco-item"><b>📅 Compra</b>{cli['Ultima_Compra']}</div>
                    <div class="foco-item"><b>⚠️ Status</b>{cli['Categoria_Cliente']}</div>
                </div>
                <div class="sugestao-box">
                    <div class="sugestao-title">🎯 Sugestão Elo ({area_cli})</div>
                    <div style="margin-bottom:6px; font-size:12px; color:#ccc;"><i>💡 {motivo_sugestao}</i></div>
                    {html_sugestoes}
                </div>
                <div class="script-box">
                    <b style="color:#E31937; display:block; margin-bottom:5px; text-transform:uppercase; font-size:11px;">🗣️ Script WhatsApp:</b>
                    "{script_msg}"
                </div>
            </div>
            """
            st.markdown(html_card, unsafe_allow_html=True)
            
            b1, b2, b3 = st.columns(3)
            with b1:
                if tel_clean and len(tel_clean) >= 10:
                    link_wpp = f"https://wa.me/55{tel_clean}?text={urllib.parse.quote(script_msg)}"
                    st.link_button("💬 WhatsApp", link_wpp, type="primary", use_container_width=True)
            with b2:
                if email_para_ia and "@" in str(email_para_ia):
                    link_gmail = f"https://mail.google.com/mail/?view=cm&fs=1&to={email_para_ia}&su=Contato Elo&body={script_msg}"
                    st.link_button("📧 Gmail", link_gmail, use_container_width=True)
            with b3:
                if st.button("✨ IA Magica", use_container_width=True):
                    if not groq_client: 
                        st.error("Sem Chave IA")
                    else:
                        with st.spinner(f"🤖 Escrevendo e-mail para {nome_para_ia}..."):
                            # Passa o nome JÁ formatado (Ex: Caio)
                            subj, body = gerar_email_ia(nome_para_ia, area_cli, cli['Ultima_Compra'], campanha, nome_usuario, cargo_usuario)
                            st.session_state['ia_result'] = {'subj': subj, 'body': body, 'email': email_para_ia}
            
            # --- BOTÃO DE AÇÃO RÁPIDA (MODO ATAQUE) ---
            st.write("")
            if st.button("✅ Marcar 'Contato Feito'", key="btn_check_atk", use_container_width=True):
                update_payload = {"status_prospect": "Contato Feito"}
                if not cli['tentativa_1']:
                    update_payload["tentativa_1"] = datetime.now().strftime("%d/%m - Manual")
                
                if atualizar_cliente_directus(token, cli['id'], update_payload):
                    st.toast("✅ Status atualizado com sucesso!", icon="🎉")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Erro ao atualizar status.")

            if 'ia_result' in st.session_state:
                res = st.session_state['ia_result']
                
                # ASSINATURA AUTOMATICA - REMOVIDO CARGO
                assinatura_automatica = f"\n\nAtenciosamente,\n\n{nome_usuario}\nElo Brindes"
                corpo_final = res['body'] + assinatura_automatica
                
                st.info(f"Assunto: {res['subj']}")
                st.text_area(f"Prévia da Mensagem (Para: {res['email']}):", value=corpo_final, height=200, disabled=True)
                
                subject_enc = urllib.parse.quote(res['subj'])
                body_enc = urllib.parse.quote(corpo_final)
                
                link_gmail_final = f"https://mail.google.com/mail/?view=cm&fs=1&to={res['email']}&su={subject_enc}&body={body_enc}"
                
                st.link_button(f"📧 Abrir no Gmail (Enviar para {res['email']})", link_gmail_final, type="primary", use_container_width=True)

    else:
        st.info("Nenhum cliente encontrado com os filtros atuais.")

with col_right:
    st.subheader("📝 Modo Atualização")
    def checar_pendencia(row):
        t = limpar_telefone(row['telefone_1'])
        e = str(row['email_1'])
        if not t or len(t) < 8: return True
        if not e or '@' not in e or 'nan' in e: return True
        return False
    
    if not df_filtrado.empty:
        df_filtrado['pendente'] = df_filtrado.apply(checar_pendencia, axis=1)
        df_pend = df_filtrado[df_filtrado['pendente'] == True].copy()
        
        if df_pend.empty:
            st.success("✅ Nenhum cadastro pendente nos filtros selecionados!")
        else:
            df_pend['lbl'] = df_pend['razao_social'] + " (Pendente)"
            sel_up = st.selectbox("Atualizar:", ["Selecione..."] + sorted(df_pend['lbl'].tolist()))
            
            if sel_up and sel_up != "Selecione...":
                cli_up = df_pend[df_pend['lbl'] == sel_up].iloc[0]
                st.markdown(f"""
                <div class="foco-card" style="border-left: 6px solid #FFD700;">
                    <h3 style='color:#FFD700'>⚠️ Dados Faltantes</h3>
                    <h2 style='color:white'>{cli_up['razao_social']}</h2>
                    <div class="foco-grid">
                        <div class="foco-item"><b>CNPJ</b> {cli_up['cnpj']}</div>
                        <div class="foco-item" style="color:#FFD700"><b>Tel</b> {cli_up['telefone_1'] or 'VAZIO'}</div>
                        <div class="foco-item" style="color:#FFD700"><b>Email</b> {cli_up['email_1'] or 'VAZIO'}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # --- BOTÃO DE AÇÃO RÁPIDA (MODO ATUALIZAÇÃO) ---
                if st.button("✅ Marcar 'Contato Feito'", key="btn_check_upd", use_container_width=True):
                    update_payload = {"status_prospect": "Contato Feito"}
                    if not cli_up['tentativa_1']:
                        update_payload["tentativa_1"] = datetime.now().strftime("%d/%m - Manual")
                    
                    if atualizar_cliente_directus(token, cli_up['id'], update_payload):
                        st.toast("✅ Status atualizado com sucesso!", icon="🎉")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar status.")
    else:
        st.write("Sem dados.")

st.divider()
st.subheader("📋 Lista Geral (Editável - Auto Save)")

todas_colunas = list(df.columns)

CONFIG_FILE = "grid_config.json"
cols_default = [c for c in ['pj_id', 'razao_social', 'status_prospect', 'email_2', 'representante_nome', 'Categoria_Cliente', 'area_atuacao', 'Ultima_Compra', 'telefone_1'] if c in todas_colunas]

saved_cols = cols_default
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
            saved_cols = [c for c in loaded if c in todas_colunas]
            if not saved_cols: saved_cols = cols_default
    except:
        saved_cols = cols_default

colunas_selecionadas = st.multiselect(
    "Selecione as colunas para exibir/editar (Sua escolha fica salva):",
    options=todas_colunas,
    default=saved_cols
)

if colunas_selecionadas != saved_cols:
    with open(CONFIG_FILE, 'w') as f:
        json.dump(colunas_selecionadas, f)

if not df_filtrado.empty:
    config_cols = {
        "pj_id": st.column_config.TextColumn("ID Loja", disabled=True),
        "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
        "Categoria_Cliente": st.column_config.TextColumn("Status", disabled=True),
        "Ultima_Compra": st.column_config.TextColumn("Ult. Compra", disabled=True),
        "GAP (dias)": st.column_config.NumberColumn("GAP (dias)", disabled=True),
        "status_prospect": st.column_config.SelectboxColumn(
            "Status Prospecção",
            options=["Não atende", "Retornar", "Tel. Incorreto", "Contato Feito", "Enviado para o RD", "Status Final"],
            width="medium",
            required=False
        ),
        "id": None, 
        "Ação": st.column_config.CheckboxColumn("➡️ Abrir", help="Clique para abrir os dados deste cliente lá em cima", default=False)
    }

    df_filtrado.insert(0, "Ação", False)

    edicoes = st.data_editor(
        df_filtrado[["Ação"] + colunas_selecionadas + ['id']], 
        key="editor_dados",
        hide_index=True,
        column_config=config_cols,
        use_container_width=True,
        num_rows="fixed"
    )

    if "editor_dados" in st.session_state and st.session_state["editor_dados"]["edited_rows"]:
        alteracoes = st.session_state["editor_dados"]["edited_rows"]
        
        tem_edicao_real = False
        for idx, mudanca in alteracoes.items():
            if any(k != "Ação" for k in mudanca.keys()):
                tem_edicao_real = True
                break
        
        if tem_edicao_real:
            sucessos = 0
            erros = 0
            
            for i, mudancas in alteracoes.items():
                dados_limpos = {k: v for k, v in mudancas.items() if k not in ['GAP (dias)', 'Ultima_Compra', 'Categoria_Cliente', 'label_select', 'data_temp', 'dias_sem_compra', 'pendente', 'Ação']}
                
                if dados_limpos:
                    try:
                        id_cliente = df_filtrado.iloc[i]['id']
                        if atualizar_cliente_directus(token, id_cliente, dados_limpos):
                            sucessos += 1
                        else:
                            erros += 1
                    except Exception as e:
                        erros += 1
            
            if sucessos > 0:
                st.toast(f"✅ {sucessos} alterações salvas automaticamente!", icon="💾")
                time.sleep(1) 
                st.rerun()
