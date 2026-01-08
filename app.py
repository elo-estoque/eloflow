import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time
import os
import random
import warnings

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="NeuroSales CRM", layout="wide", page_icon="🦅")

# Remove avisos chatos do console
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "false"

# --- 2. CSS VISUAL (DARK MODE) ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #E5E7EB; }
    div.stButton > button { background-color: #E31937; color: white; border: none; font-weight: bold; }
    div.stButton > button:hover { background-color: #C2132F; }
    .metric-card {
        background-color: #151515; border: 1px solid #333; padding: 15px; 
        border-radius: 8px; border-left: 4px solid #E31937; margin-bottom: 10px;
    }
    .metric-card h3 { color: #888; font-size: 14px; margin: 0; }
    .metric-card h1 { color: #FFF; margin: 5px 0 0 0; }
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. VARIÁVEIS DE AMBIENTE ---
# URL Padrão (Tenta pegar do .env, se não usa a fixa)
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://elo-operaes-elo-operaes-directus-sotkfd-93c3dc-152-53-165-62.traefik.me")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================================================
#  FUNÇÕES DE BACKEND (COM DEBUG DE LOGIN)
# =========================================================

def login_directus_debug(email, password):
    """
    Tenta logar e retorna EXATAMENTE o motivo se falhar.
    """
    login_url = f"{DIRECTUS_URL}/auth/login"
    
    # 1. TENTATIVA DE CONEXÃO E AUTENTICAÇÃO
    try:
        response = requests.post(login_url, json={"email": email, "password": password}, timeout=15)
    except Exception as e:
        st.error(f"❌ ERRO DE CONEXÃO: O Python não conseguiu chegar no endereço {DIRECTUS_URL}")
        st.caption(f"Detalhe técnico: {e}")
        return None, None

    # 2. ANÁLISE DA RESPOSTA DO LOGIN
    if response.status_code == 401:
        st.error("🔒 E-mail ou Senha incorretos.")
        return None, None
    
    if response.status_code != 200:
        st.error(f"❌ Erro no Login. Código: {response.status_code}")
        st.text(response.text)
        return None, None

    # Se chegou aqui, a senha está certa. Pegamos o token.
    token = response.json()['data']['access_token']

    # 3. TENTATIVA DE LER O PERFIL (Onde costuma dar erro de permissão)
    try:
        user_url = f"{DIRECTUS_URL}/users/me"
        user_resp = requests.get(user_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        
        if user_resp.status_code == 200:
            return token, user_resp.json()['data']
        
        elif user_resp.status_code == 403:
            st.error("⛔ LOGIN OK, MAS PERFIL BLOQUEADO!")
            st.warning("O usuário e senha estão certos, mas o Directus bloqueou a leitura do perfil.")
            st.info("🔧 SOLUÇÃO: Vá no Painel Admin > Settings > Roles & Permissions > Vendedor > System Collections > Users (directus_users) e dê permissão de Leitura (Olho).")
            return None, None
        
        else:
            st.error(f"⚠️ Erro ao carregar perfil: {user_resp.status_code}")
            return None, None

    except Exception as e:
        st.error(f"Erro ao buscar dados do usuário: {e}")
        return None, None

def carregar_clientes(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        # Pede campos específicos para ser mais leve
        fields = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,email_1"
        url = f"{DIRECTUS_URL}/items/clientes?limit=-1&fields={fields}"
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()['data']
            return pd.DataFrame(data) if data else pd.DataFrame()
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def carregar_campanha_ativa(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{DIRECTUS_URL}/items/campanhas_vendas?filter[ativa][_eq]=true&limit=1"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200 and r.json()['data']:
            return r.json()['data'][0]
    except:
        pass
    return None

def config_smtp_crud(token, payload=None):
    """Lê ou Grava configuração SMTP"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{DIRECTUS_URL}/items/config_smtp"
    
    # Se tem payload, é para SALVAR
    if payload:
        # Verifica se já existe config
        check = requests.get(url, headers=headers)
        if check.status_code == 200 and len(check.json()['data']) > 0:
            item_id = check.json()['data'][0]['id']
            requests.patch(f"{url}/{item_id}", json=payload, headers=headers)
        else:
            requests.post(url, json=payload, headers=headers)
        return True
    
    # Se não tem payload, é para LER
    else:
        r = requests.get(url, headers=headers)
        if r.status_code == 200 and r.json()['data']:
            return r.json()['data'][0]
        return None

def registrar_log(token, pj_id, assunto, corpo, status):
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "cliente_pj_id": str(pj_id),
            "assunto_gerado": assunto,
            "corpo_email": corpo,
            "status_envio": status,
            "data_envio": datetime.now().isoformat()
        }
        requests.post(f"{DIRECTUS_URL}/items/historico_envios", json=payload, headers=headers)
    except:
        pass

# =========================================================
#  IA & SMTP
# =========================================================

def gerar_email_ia(cliente, ramo, data_compra, campanha):
    if not GEMINI_API_KEY:
        return "Erro: Falta Chave Gemini", "Configure a API Key."
    
    camp_nome = campanha.get('nome_campanha', 'Retomada') if campanha else 'Contato'
    camp_inst = campanha.get('prompt_instrucao', 'Ofereça produtos.') if campanha else 'Geral'
    
    prompt = f"""
    Aja como um vendedor da Elo Brindes. Email curto (max 100 palavras).
    Cliente: {cliente} ({ramo}). Última Compra: {data_compra}.
    Campanha: {camp_nome}. Instrução: {camp_inst}.
    Retorne APENAS: ASSUNTO|CORPO_HTML
    """
    try:
        model = genai.GenerativeModel('gemini-pro')
        resp = model.generate_content(prompt)
        txt = resp.text.strip()
        if "|" in txt:
            return txt.split("|", 1)
        return "Assunto Elo", txt
    except Exception as e:
        return "Erro IA", str(e)

def enviar_email(conf, para, assunto, corpo):
    try:
        msg = MIMEMultipart()
        msg['From'] = conf['smtp_user']
        msg['To'] = para
        msg['Subject'] = assunto
        final = f"{corpo}<br><br>{conf.get('assinatura_html', '')}"
        msg.attach(MIMEText(final, 'html'))
        
        s = smtplib.SMTP(conf['smtp_host'], conf['smtp_port'])
        s.starttls()
        s.login(conf['smtp_user'], conf['smtp_pass_app'])
        s.sendmail(conf['smtp_user'], para, msg.as_string())
        s.quit()
        return True, "Enviado"
    except Exception as e:
        return False, str(e)

# =========================================================
#  INTERFACE (STREAMLIT)
# =========================================================

# --- TELA DE LOGIN ---
if 'token' not in st.session_state:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br><h1 style='text-align:center; color:#E31937'>🦅 NeuroSales CRM</h1>", unsafe_allow_html=True)
        st.info(f"Conectando em: {DIRECTUS_URL}")
        
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        
        if st.button("ENTRAR", use_container_width=True):
            token, user = login_directus_debug(email, senha)
            if token:
                st.session_state['token'] = token
                st.session_state['user'] = user
                st.rerun()
    st.stop()

# --- ÁREA LOGADA ---
token = st.session_state['token']
user = st.session_state['user']

# Sidebar
with st.sidebar:
    st.write(f"👤 **{user.get('first_name', 'Vendedor')}**")
    if st.button("Sair"):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    with st.expander("⚙️ Configurar E-mail"):
        conf = config_smtp_crud(token)
        h = st.text_input("Host", value=conf['smtp_host'] if conf else "smtp.gmail.com")
        p = st.number_input("Porta", value=conf['smtp_port'] if conf else 587)
        u = st.text_input("Email", value=conf['smtp_user'] if conf else "")
        pw = st.text_input("Senha App", type="password", value=conf['smtp_pass_app'] if conf else "")
        ass = st.text_area("Assinatura HTML", value=conf['assinatura_html'] if conf else "")
        
        if st.button("Salvar"):
            payload = {"smtp_host": h, "smtp_port": int(p), "smtp_user": u, "smtp_pass_app": pw, "assinatura_html": ass}
            config_smtp_crud(token, payload)
            st.success("Salvo!")

# Main
df = carregar_clientes(token)
campanha = carregar_campanha_ativa(token)

st.title(f"Painel - {user.get('first_name', '')}")

if df.empty:
    st.warning("⚠️ Sua carteira está vazia ou não carregou.")
    st.stop()

# Métricas
k1, k2, k3 = st.columns(3)
k1.markdown(f"<div class='metric-card'><h3>Clientes</h3><h1>{len(df)}</h1></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='metric-card'><h3>Campanha</h3><h4>{campanha['nome_campanha'] if campanha else 'Nenhuma'}</h4></div>", unsafe_allow_html=True)

# Abas
tab1, tab2 = st.tabs(["🚀 Disparo IA", "📋 Lista"])

with tab1:
    st.subheader("Gerar Emails")
    filtro = st.multiselect("Status", df['status_carteira'].unique())
    df_view = df[df['status_carteira'].isin(filtro)] if filtro else df
    
    st.dataframe(df_view[['razao_social', 'status_carteira', 'email_1']], use_container_width=True, hide_index=True)
    
    opcoes = df_view.set_index('id')['razao_social'].to_dict()
    sel = st.multiselect("Selecionar Clientes:", options=opcoes.keys(), format_func=lambda x: opcoes[x])
    
    if sel and st.button("✨ Gerar IA"):
        res = []
        bar = st.progress(0)
        for i, cid in enumerate(sel):
            row = df[df['id']==cid].iloc[0]
            subj, body = gerar_email_ia(row['razao_social'], row['area_atuacao'], row['data_ultima_compra'], campanha)
            res.append({"id": cid, "pj_id": row['pj_id'], "email": row['email_1'], "subj": subj, "body": body, "name": row['razao_social']})
            bar.progress((i+1)/len(sel))
        st.session_state['rascunhos'] = res
        
    if 'rascunhos' in st.session_state:
        st.divider()
        for mail in st.session_state['rascunhos']:
            with st.expander(f"✉️ {mail['name']}"):
                st.write(f"**{mail['subj']}**")
                st.markdown(mail['body'], unsafe_allow_html=True)
        
        if st.button("🚀 Enviar Todos"):
            conf = config_smtp_crud(token)
            if not conf or not conf.get('smtp_pass_app'):
                st.error("Configure o SMTP na barra lateral!")
            else:
                bar = st.progress(0)
                for i, mail in enumerate(st.session_state['rascunhos']):
                    ok, msg = enviar_email(conf, mail['email'], mail['subj'], mail['body'])
                    status = "Sucesso" if ok else f"Erro: {msg}"
                    registrar_log(token, mail['pj_id'], mail['subj'], mail['body'], status)
                    time.sleep(random.uniform(2, 5))
                    bar.progress((i+1)/len(st.session_state['rascunhos']))
                st.success("Concluído!")
                del st.session_state['rascunhos']

with tab2:
    st.dataframe(df, use_container_width=True)
