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

# --- 1. CONFIGURAÇÕES INICIAIS E SILENCIAMENTO DE AVISOS ---
st.set_page_config(page_title="NeuroSales CRM", layout="wide", page_icon="🦅")

# Ignora avisos chatos do Pandas e Streamlit
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "false"

# --- 2. CSS PERSONALIZADO (DARK MODE & ELO BRAND) ---
st.markdown("""
<style>
    /* Fundo e Texto Geral */
    .stApp { background-color: #050505; color: #E5E7EB; }
    
    /* Botões */
    div.stButton > button { 
        background-color: #E31937; 
        color: white; 
        border: none; 
        border-radius: 6px; 
        font-weight: bold;
    }
    div.stButton > button:hover { 
        background-color: #C2132F; 
        border-color: #C2132F;
    }
    
    /* Cards de Métricas */
    .metric-card {
        background-color: #151515; 
        border: 1px solid #333; 
        padding: 15px; 
        border-radius: 8px; 
        border-left: 4px solid #E31937;
        margin-bottom: 10px;
    }
    .metric-card h3 { font-size: 14px; color: #888; margin: 0; }
    .metric-card h1 { font-size: 28px; color: #FFF; margin: 5px 0 0 0; }
    .metric-card h4 { font-size: 18px; color: #EEE; margin: 5px 0 0 0; }
    
    /* Inputs e Tabelas */
    .stTextInput > div > div > input { background-color: #1A1A1A; color: white; border-color: #333; }
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. VARIÁVEIS DE AMBIENTE ---
# Se não estiverem no .env, use os valores padrão (ajuste se necessário)
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "http://152.53.165.62:8055") 
# Coloque sua chave do Google AI Studio aqui se não usar variável de ambiente
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================================================
#  FUNÇÕES DE BACKEND (API DIRECTUS)
# =========================================================

def login_directus(email, password):
    """Autentica o vendedor e retorna o Token JWT + Dados do Usuário"""
    try:
        url = f"{DIRECTUS_URL}/auth/login"
        payload = {"email": email, "password": password}
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()['data']
            # Pega dados do usuário logado
            user_resp = requests.get(f"{DIRECTUS_URL}/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}, timeout=10)
            if user_resp.status_code == 200:
                user_data = user_resp.json()['data']
                return data['access_token'], user_data
        return None, None
    except Exception as e:
        st.error(f"Erro de conexão com servidor: {e}")
        return None, None

def carregar_clientes(token):
    """Busca clientes do Directus."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        # Busca campos essenciais
        fields = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais"
        url = f"{DIRECTUS_URL}/items/clientes?limit=-1&fields={fields}"
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()['data']
            if not data: return pd.DataFrame()
            return pd.DataFrame(data)
        else:
            st.warning("Não foi possível carregar a lista de clientes.")
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def carregar_campanha_ativa(token):
    """Busca a campanha de vendas ativa"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{DIRECTUS_URL}/items/campanhas_vendas?filter[ativa][_eq]=true&limit=1"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and response.json()['data']:
            return response.json()['data'][0]
    except:
        pass
    return None

def salvar_config_smtp(token, host, port, user, password, assinatura):
    """Salva as credenciais SMTP"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Verifica se já existe
    check = requests.get(f"{DIRECTUS_URL}/items/config_smtp", headers=headers, timeout=10)
    
    payload = {
        "smtp_host": host,
        "smtp_port": int(port),
        "smtp_user": user,
        "smtp_pass_app": password,
        "assinatura_html": assinatura
    }
    
    if check.status_code == 200 and len(check.json()['data']) > 0:
        item_id = check.json()['data'][0]['id']
        requests.patch(f"{DIRECTUS_URL}/items/config_smtp/{item_id}", json=payload, headers=headers)
    else:
        requests.post(f"{DIRECTUS_URL}/items/config_smtp", json=payload, headers=headers)

def pegar_config_smtp(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{DIRECTUS_URL}/items/config_smtp", headers=headers, timeout=10)
        if resp.status_code == 200 and resp.json()['data']:
            return resp.json()['data'][0]
    except:
        return None
    return None

def registrar_log_envio(token, cliente_pj_id, assunto, corpo, status):
    """Registra no Directus o envio"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "cliente_pj_id": str(cliente_pj_id),
        "assunto_gerado": assunto,
        "corpo_email": corpo,
        "status_envio": status,
        "data_envio": datetime.now().isoformat()
    }
    requests.post(f"{DIRECTUS_URL}/items/historico_envios", json=payload, headers=headers)

# =========================================================
#  IA GENERATIVA (GEMINI)
# =========================================================
def gerar_email_ia(cliente_nome, ramo, data_compra, campanha_obj):
    if not GEMINI_API_KEY:
        return "Erro: Configure a Chave da IA", "A chave GEMINI_API_KEY não foi encontrada."
    
    campanha_nome = campanha_obj.get('nome_campanha', 'Retomada de Contato') if campanha_obj else "Contato Geral"
    campanha_instrucao = campanha_obj.get('prompt_instrucao', 'Ofereça o portfólio completo.') if campanha_obj else "Ofereça produtos gerais."
    
    prompt = f"""
    Aja como um vendedor B2B da Elo Brindes. Escreva um e-mail curto (máx 120 palavras).
    
    Cliente: {cliente_nome} ({ramo})
    Última Compra: {data_compra if data_compra else 'Não informado'}
    Campanha Atual: {campanha_nome}
    Instrução de Venda: {campanha_instrucao}
    
    Regras:
    1. Assunto: Curto e intrigante (sem "Venda" ou "Promoção").
    2. Corpo: HTML simples (<p>, <b>, <br>). Sem saudação genérica.
    3. Foco: Retomar relacionamento ou oferecer novidade.
    4. SAÍDA OBRIGATÓRIA: ASSUNTO|CORPO_HTML
    """
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        texto = response.text.strip()
        
        if "|" in texto:
            parts = texto.split("|", 1)
            return parts[0].strip(), parts[1].strip()
        else:
            return "Oportunidade Elo Brindes", texto
            
    except Exception as e:
        return "Erro IA", f"Falha na geração: {str(e)}"

# =========================================================
#  MOTOR DE ENVIO (SMTP)
# =========================================================
def enviar_email_smtp(smtp_config, destinatario, assunto, corpo_html):
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_config['smtp_user']
        msg['To'] = destinatario
        msg['Subject'] = assunto
        
        assinatura = smtp_config.get('assinatura_html', '')
        corpo_final = f"{corpo_html}<br><br>{assinatura}"
        
        msg.attach(MIMEText(corpo_final, 'html'))
        
        server = smtplib.SMTP(smtp_config['smtp_host'], smtp_config['smtp_port'])
        server.starttls()
        server.login(smtp_config['smtp_user'], smtp_config['smtp_pass_app'])
        server.sendmail(smtp_config['smtp_user'], destinatario, msg.as_string())
        server.quit()
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
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #E31937;'>🦅 NeuroSales CRM</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #888;'>Acesse sua carteira exclusiva</p>", unsafe_allow_html=True)
        
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        
        if st.button("ENTRAR", use_container_width=True):
            if not email or not senha:
                st.warning("Preencha todos os campos.")
            else:
                token, user_data = login_directus(email, senha)
                if token:
                    st.session_state['token'] = token
                    st.session_state['user'] = user_data
                    st.rerun()
                else:
                    st.error("Login falhou. Verifique suas credenciais.")
    st.stop()

# --- DASHBOARD LOGADO ---
user = st.session_state['user']
token = st.session_state['token']

# Sidebar (Perfil e Config)
with st.sidebar:
    st.write(f"👤 **{user.get('first_name', 'Vendedor')} {user.get('last_name', '')}**")
    
    if st.button("🚪 Sair"):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.markdown("### ⚙️ Configuração SMTP")
    with st.expander("Configurar meu E-mail"):
        conf = pegar_config_smtp(token)
        
        # Valores padrão ou carregados do banco
        val_host = conf['smtp_host'] if conf else "smtp.gmail.com"
        val_port = conf['smtp_port'] if conf else 587
        val_user = conf['smtp_user'] if conf else ""
        val_pass = conf['smtp_pass_app'] if conf else ""
        val_ass = conf['assinatura_html'] if conf else "<p>Att,<br><b>Equipe Elo</b></p>"
        
        smtp_host = st.text_input("Host SMTP", value=val_host)
        smtp_port = st.number_input("Porta", value=val_port)
        smtp_user = st.text_input("Seu E-mail", value=val_user)
        smtp_pass = st.text_input("Senha de App", type="password", value=val_pass)
        assinatura = st.text_area("Assinatura HTML", value=val_ass)
        
        if st.button("Salvar Configuração"):
            salvar_config_smtp(token, smtp_host, smtp_port, smtp_user, smtp_pass, assinatura)
            st.success("Configuração salva!")

# Carregar Dados Iniciais
df_clientes = carregar_clientes(token)
campanha = carregar_campanha_ativa(token)

st.title(f"Painel de Vendas - {user.get('first_name', '')}")

if df_clientes.empty:
    st.info("👋 Olá! Nenhum cliente encontrado na sua carteira. Fale com o administrador para importar os dados.")
    st.stop()

# Métricas Topo
k1, k2, k3 = st.columns(3)
total_cli = len(df_clientes)
inativos_count = len(df_clientes[df_clientes['status_carteira'].astype(str).str.contains('Inativo|Frio', case=False, na=False)])
campanha_nome = campanha['nome_campanha'] if campanha else "Nenhuma Campanha Ativa"

k1.markdown(f"<div class='metric-card'><h3>Total Clientes</h3><h1>{total_cli}</h1></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='metric-card'><h3>Inativos/Frios</h3><h1 style='color:#E31937'>{inativos_count}</h1></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='metric-card'><h3>Campanha Atual</h3><h4>{campanha_nome}</h4></div>", unsafe_allow_html=True)

st.divider()

# Abas Principais
tab1, tab2 = st.tabs(["🚀 Modo Ataque (IA + Email)", "📋 Carteira Completa"])

# --- TAB 1: MODO ATAQUE ---
with tab1:
    st.subheader("Gerador de Oportunidades")
    
    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        opcoes_status = df_clientes['status_carteira'].dropna().unique().tolist()
        filtro_status = st.multiselect("Filtrar Status:", options=opcoes_status)
    with col_f2:
        opcoes_ramo = df_clientes['area_atuacao'].dropna().unique().tolist()
        filtro_ramo = st.multiselect("Filtrar Ramo:", options=opcoes_ramo)
    
    df_filtrado = df_clientes.copy()
    if filtro_status:
        df_filtrado = df_filtrado[df_filtrado['status_carteira'].isin(filtro_status)]
    if filtro_ramo:
        df_filtrado = df_filtrado[df_filtrado['area_atuacao'].isin(filtro_ramo)]
        
    st.dataframe(
        df_filtrado[['razao_social', 'email_1', 'status_carteira', 'data_ultima_compra']], 
        use_container_width=True, 
        hide_index=True
    )
    
    st.markdown("### 📧 Preparar Disparo")
    
    # Selectbox dos clientes filtrados
    if not df_filtrado.empty:
        clientes_dict = df_filtrado.set_index('id')['razao_social'].to_dict()
        selecionados_ids = st.multiselect(
            "Selecione os clientes para atacar:", 
            options=clientes_dict.keys(), 
            format_func=lambda x: clientes_dict[x]
        )
        
        if selecionados_ids:
            st.info(f"{len(selecionados_ids)} clientes selecionados.")
            
            # Botão 1: Gerar IA
            if st.button("✨ 1. Gerar Rascunhos com IA", type="primary"):
                if not GEMINI_API_KEY:
                    st.error("Erro: Configure a API KEY do Gemini.")
                else:
                    rascunhos = []
                    progresso = st.progress(0)
                    texto_progresso = st.empty()
                    
                    for i, c_id in enumerate(selecionados_ids):
                        cli_row = df_clientes[df_clientes['id'] == c_id].iloc[0]
                        texto_progresso.text(f"Gerando para: {cli_row['razao_social']}...")
                        
                        assunto, corpo = gerar_email_ia(
                            cli_row['razao_social'], 
                            cli_row['area_atuacao'], 
                            cli_row['data_ultima_compra'], 
                            campanha
                        )
                        rascunhos.append({
                            "id": c_id,
                            "pj_id": cli_row.get('pj_id', '-'),
                            "razao_social": cli_row['razao_social'],
                            "email": cli_row['email_1'],
                            "assunto": assunto,
                            "corpo": corpo
                        })
                        progresso.progress((i + 1) / len(selecionados_ids))
                    
                    st.session_state['rascunhos_gerados'] = rascunhos
                    st.success("Rascunhos gerados! Revise abaixo.")

    # Área de Revisão e Envio
    if 'rascunhos_gerados' in st.session_state and st.session_state['rascunhos_gerados']:
        st.divider()
        st.subheader("📝 Revisão e Disparo")
        
        # Mostra preview do primeiro como exemplo
        st.markdown("**Preview dos E-mails Gerados:**")
        for item in st.session_state['rascunhos_gerados']:
            with st.expander(f"✉️ {item['razao_social']} - {item['assunto']}"):
                st.markdown(item['corpo'], unsafe_allow_html=True)
                st.caption(f"Envia para: {item['email']}")
        
        if st.button("🚀 2. Disparar Todos Agora"):
            conf_smtp = pegar_config_smtp(token)
            if not conf_smtp or not conf_smtp.get('smtp_pass_app'):
                st.error("⚠️ ERRO: Você não configurou seu E-mail SMTP na barra lateral!")
            else:
                bar_envio = st.progress(0)
                log_status = []
                
                for i, item in enumerate(st.session_state['rascunhos_gerados']):
                    if not item['email'] or "@" not in str(item['email']):
                        log_status.append(f"❌ {item['razao_social']}: E-mail inválido")
                        continue
                        
                    sucesso, msg = enviar_email_smtp(conf_smtp, item['email'], item['assunto'], item['corpo'])
                    
                    if sucesso:
                        registrar_log_envio(token, item['pj_id'], item['assunto'], item['corpo'], "Sucesso")
                        log_status.append(f"✅ {item['razao_social']}: Enviado")
                    else:
                        registrar_log_envio(token, item['pj_id'], item['assunto'], item['corpo'], f"Erro: {msg}")
                        log_status.append(f"❌ {item['razao_social']}: Falha ({msg})")
                    
                    # Delay Humanizado (5 a 10s)
                    time.sleep(random.uniform(5, 10))
                    bar_envio.progress((i + 1) / len(st.session_state['rascunhos_gerados']))
                
                st.success("Disparos finalizados!")
                st.write(log_status)
                # Limpa a sessão
                del st.session_state['rascunhos_gerados']

# --- TAB 2: LISTA COMPLETA ---
with tab2:
    st.subheader("Base Geral")
    st.dataframe(df_clientes, use_container_width=True)
