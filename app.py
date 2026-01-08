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

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="NeuroSales CRM", layout="wide", page_icon="🦅")

# --- CSS PERSONALIZADO (DARK MODE & ELO BRAND) ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #E5E7EB; }
    div.stButton > button { background-color: #E31937; color: white; border: none; border-radius: 6px; }
    div.stButton > button:hover { background-color: #C2132F; }
    
    /* Cards */
    .metric-card {
        background-color: #151515; border: 1px solid #333; 
        padding: 15px; border-radius: 8px; border-left: 4px solid #E31937;
    }
    
    /* Status Badges */
    .badge-frio { background-color: #3b82f6; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    .badge-inativo { background-color: #E31937; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    
    /* Inputs */
    .stTextInput > div > div > input { background-color: #1A1A1A; color: white; border-color: #333; }
</style>
""", unsafe_allow_html=True)

# --- VARIÁVEIS DE AMBIENTE (Configure no seu servidor ou .env) ---
# URL do seu Directus (conforme configurado no .env anterior)
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://elo-operaes-elo-operaes-directus-sotkfd-93c3dc-152-53-165-62.traefik.me") 
# Chave da IA (Coloque sua chave do Google AI Studio aqui ou nas variáveis de ambiente)
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
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()['data']
            # Pega dados do usuário logado
            user_resp = requests.get(f"{DIRECTUS_URL}/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
            if user_resp.status_code == 200:
                user_data = user_resp.json()['data']
                return data['access_token'], user_data
        return None, None
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None, None

def carregar_clientes(token):
    """Busca clientes do Directus. As permissões da Role 'Vendedor' garantem que ele só veja os dele."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        # Busca campos essenciais
        fields = "pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,id"
        url = f"{DIRECTUS_URL}/items/clientes?limit=-1&fields={fields}"
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()['data']
            if not data: return pd.DataFrame()
            return pd.DataFrame(data)
        else:
            st.error("Falha ao carregar clientes.")
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def carregar_campanha_ativa(token):
    """Busca a campanha de vendas ativa para orientar a IA"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{DIRECTUS_URL}/items/campanhas_vendas?filter[ativa][_eq]=true&limit=1"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json()['data']:
            return response.json()['data'][0]
    except:
        pass
    return None

def salvar_config_smtp(token, host, port, user, password, assinatura):
    """Salva/Atualiza as credenciais SMTP do vendedor no Directus"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 1. Verifica se já existe config para este usuário
    # Assumindo que o usuário logado só vê a sua config via permissão do Directus
    check = requests.get(f"{DIRECTUS_URL}/items/config_smtp", headers=headers)
    
    payload = {
        "smtp_host": host,
        "smtp_port": int(port),
        "smtp_user": user,
        "smtp_pass_app": password, # Idealmente criptografar, mas estamos enviando via HTTPS
        "assinatura_html": assinatura
    }
    
    if check.status_code == 200 and len(check.json()['data']) > 0:
        # Atualiza (PATCH)
        item_id = check.json()['data'][0]['id']
        requests.patch(f"{DIRECTUS_URL}/items/config_smtp/{item_id}", json=payload, headers=headers)
    else:
        # Cria (POST)
        requests.post(f"{DIRECTUS_URL}/items/config_smtp", json=payload, headers=headers)

def pegar_config_smtp(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{DIRECTUS_URL}/items/config_smtp", headers=headers)
        if resp.status_code == 200 and resp.json()['data']:
            return resp.json()['data'][0]
    except:
        return None
    return None

def registrar_log_envio(token, cliente_id, assunto, corpo, status):
    """Registra no Directus que um e-mail foi enviado"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "cliente_pj_id": str(cliente_id), # Usando pj_id como referência visual
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
        return "Erro: Chave API Gemini não configurada.", "Erro"
    
    campanha_nome = campanha_obj.get('nome_campanha', 'Retomada de Contato') if campanha_obj else "Contato Geral"
    campanha_instrucao = campanha_obj.get('prompt_instrucao', 'Ofereça nossos produtos gerais.') if campanha_obj else "Ofereça o portfólio completo."
    
    prompt = f"""
    Aja como um vendedor consultivo B2B da Elo Brindes.
    Escreva um e-mail curto (máximo 100 palavras) para o cliente '{cliente_nome}' do ramo '{ramo}'.
    
    Contexto:
    - Última compra deles foi em: {data_compra if data_compra else 'Sem data registrada'}
    - Campanha atual: {campanha_nome}
    - Instrução da Campanha: {campanha_instrucao}
    
    Regras:
    1. O assunto deve ser intrigante e curto.
    2. O corpo deve ser HTML simples (use <p>, <br>, <b>).
    3. NÃO coloque saudação genérica como "Prezado". Comece com "Olá {cliente_nome.split()[0].title()}" ou similar.
    4. Termine convidando para uma resposta rápida.
    5. Retorne a resposta no formato exato: ASSUNTO|CORPO_HTML
    """
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        texto = response.text.strip()
        
        if "|" in texto:
            assunto, corpo = texto.split("|", 1)
            return assunto.strip(), corpo.strip()
        else:
            return "Oportunidade na Elo Brindes", texto
            
    except Exception as e:
        return "Erro na IA", f"Não foi possível gerar. Erro: {str(e)}"

# =========================================================
#  MOTOR DE ENVIO (SMTP)
# =========================================================
def enviar_email_smtp(smtp_config, destinatario, assunto, corpo_html):
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_config['smtp_user']
        msg['To'] = destinatario
        msg['Subject'] = assunto
        
        # Anexa assinatura se tiver
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
        st.markdown("<h1 style='text-align: center; color: #E31937;'>🦅 NeuroSales CRM</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Acesse sua carteira exclusiva</p>", unsafe_allow_html=True)
        
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        
        if st.button("ENTRAR", use_container_width=True):
            token, user_data = login_directus(email, senha)
            if token:
                st.session_state['token'] = token
                st.session_state['user'] = user_data
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

# --- DASHBOARD LOGADO ---
user = st.session_state['user']
token = st.session_state['token']

# Sidebar
with st.sidebar:
    st.write(f"👤 **{user['first_name']} {user['last_name']}**")
    st.caption(f"ID: {user['id']}")
    
    if st.button("🚪 Sair"):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.markdown("### ⚙️ Configuração SMTP")
    with st.expander("Configurar E-mail"):
        conf = pegar_config_smtp(token)
        smtp_host = st.text_input("Host SMTP", value=conf['smtp_host'] if conf else "smtp.gmail.com")
        smtp_port = st.number_input("Porta", value=conf['smtp_port'] if conf else 587)
        smtp_user = st.text_input("Seu E-mail", value=conf['smtp_user'] if conf else "")
        smtp_pass = st.text_input("Senha de App", type="password", value=conf['smtp_pass_app'] if conf else "")
        assinatura = st.text_area("Assinatura HTML", value=conf['assinatura_html'] if conf else "<p>Att, Vendedor</p>")
        
        if st.button("Salvar Configuração"):
            salvar_config_smtp(token, smtp_host, smtp_port, smtp_user, smtp_pass, assinatura)
            st.success("Salvo!")

# Carregar Dados
df_clientes = carregar_clientes(token)
campanha = carregar_campanha_ativa(token)

st.title(f"Painel de Vendas - {user['first_name']}")

if df_clientes.empty:
    st.info("👋 Olá! Sua carteira ainda está vazia ou não carregou. Fale com o administrador.")
    st.stop()

# Métricas Topo
k1, k2, k3 = st.columns(3)
k1.markdown(f"<div class='metric-card'><h3>Total Carteira</h3><h1>{len(df_clientes)}</h1></div>", unsafe_allow_html=True)
inativos_count = len(df_clientes[df_clientes['status_carteira'].astype(str).str.contains('Inativo|Frio', case=False, na=False)])
k2.markdown(f"<div class='metric-card'><h3>Inativos/Frios</h3><h1 style='color:#E31937'>{inativos_count}</h1></div>", unsafe_allow_html=True)
campanha_nome = campanha['nome_campanha'] if campanha else "Sem Campanha Ativa"
k3.markdown(f"<div class='metric-card'><h3>Campanha Atual</h3><h4>{campanha_nome}</h4></div>", unsafe_allow_html=True)

st.divider()

# Abas Principais
tab1, tab2 = st.tabs(["🚀 Modo Ataque (Disparo IA)", "📋 Lista Completa"])

# --- TAB 1: MODO ATAQUE ---
with tab1:
    st.subheader("Gerador de Oportunidades")
    
    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtro_status = st.multiselect("Filtrar Status:", df_clientes['status_carteira'].unique())
    with col_f2:
        filtro_ramo = st.multiselect("Filtrar Ramo:", df_clientes['area_atuacao'].unique())
    
    df_filtrado = df_clientes.copy()
    if filtro_status:
        df_filtrado = df_filtrado[df_filtrado['status_carteira'].isin(filtro_status)]
    if filtro_ramo:
        df_filtrado = df_filtrado[df_filtrado['area_atuacao'].isin(filtro_ramo)]
        
    st.dataframe(df_filtrado[['razao_social', 'email_1', 'status_carteira', 'data_ultima_compra']], use_container_width=True, hide_index=True)
    
    # Seleção para Disparo
    st.markdown("### 📧 Preparar Disparo")
    
    # Selectbox dos clientes filtrados
    clientes_opcoes = df_filtrado.set_index('id')['razao_social'].to_dict()
    selecionados_ids = st.multiselect("Selecione os clientes para atacar agora:", options=clientes_opcoes.keys(), format_func=lambda x: clientes_opcoes[x])
    
    if selecionados_ids:
        st.info(f"{len(selecionados_ids)} clientes selecionados.")
        
        # Botão Gerar IA
        if st.button("✨ 1. Gerar Rascunhos com IA", type="primary"):
            if not GEMINI_API_KEY:
                st.error("Configure a API KEY do Gemini no código ou variáveis de ambiente.")
            else:
                rascunhos = []
                progresso = st.progress(0)
                
                for i, c_id in enumerate(selecionados_ids):
                    cli_data = df_clientes[df_clientes['id'] == c_id].iloc[0]
                    assunto, corpo = gerar_email_ia(
                        cli_data['razao_social'], 
                        cli_data['area_atuacao'], 
                        cli_data['data_ultima_compra'], 
                        campanha
                    )
                    rascunhos.append({
                        "id": c_id,
                        "razao_social": cli_data['razao_social'],
                        "email": cli_data['email_1'],
                        "assunto": assunto,
                        "corpo": corpo
                    })
                    progresso.progress((i + 1) / len(selecionados_ids))
                
                st.session_state['rascunhos_gerados'] = rascunhos
                st.success("Rascunhos gerados! Revise abaixo.")

    # Área de Revisão e Envio
    if 'rascunhos_gerados' in st.session_state and st.session_state['rascunhos_gerados']:
        st.divider()
        st.subheader("📝 Revisão e Envio")
        
        # Mostra um preview editável do primeiro da lista (MVP simplificado)
        # Numa versão completa, usaria um st.data_editor complexo
        st.write("Exemplo do que será enviado:")
        
        for email_obj in st.session_state['rascunhos_gerados']:
            with st.expander(f"✉️ {email_obj['razao_social']} ({email_obj['email']})"):
                st.markdown(f"**Assunto:** {email_obj['assunto']}")
                st.markdown(email_obj['corpo'], unsafe_allow_html=True)
        
        st.warning("⚠️ Certifique-se de ter configurado seu SMTP na barra lateral antes de enviar.")
        
        if st.button("🚀 2. Disparar Todos Agora"):
            conf_smtp = pegar_config_smtp(token)
            if not conf_smtp or not conf_smtp.get('smtp_pass_app'):
                st.error("Configure seu E-mail SMTP na barra lateral primeiro!")
            else:
                bar_envio = st.progress(0)
                log_status = []
                
                for i, item in enumerate(st.session_state['rascunhos_gerados']):
                    if not item['email'] or "@" not in str(item['email']):
                        log_status.append(f"❌ {item['razao_social']}: E-mail inválido")
                        continue
                        
                    sucesso, msg = enviar_email_smtp(conf_smtp, item['email'], item['assunto'], item['corpo'])
                    
                    if sucesso:
                        registrar_log_envio(token, df_clientes[df_clientes['id']==item['id']].iloc[0]['pj_id'], item['assunto'], item['corpo'], "Sucesso")
                        log_status.append(f"✅ {item['razao_social']}: Enviado")
                    else:
                        registrar_log_envio(token, df_clientes[df_clientes['id']==item['id']].iloc[0]['pj_id'], item['assunto'], item['corpo'], f"Erro: {msg}")
                        log_status.append(f"❌ {item['razao_social']}: Falha ({msg})")
                    
                    # Delay Humanizado Anti-Bloqueio
                    time.sleep(random.uniform(5, 15))
                    bar_envio.progress((i + 1) / len(st.session_state['rascunhos_gerados']))
                
                st.success("Processo finalizado!")
                st.write(log_status)
                del st.session_state['rascunhos_gerados']

# --- TAB 2: LISTA COMPLETA ---
with tab2:
    st.dataframe(df_clientes)
