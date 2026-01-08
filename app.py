import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
import time
import os
import random
import urllib.parse
import warnings
import urllib3 

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="NeuroSales CRM", layout="wide", page_icon="🦅")

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
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. VARIÁVEIS DE AMBIENTE ---
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://elo-flow-eloflowdirectus-a9lluh-7f4d22-152-53-165-62.traefik.me")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================================================
#  FUNÇÕES AUXILIARES E DE NEGÓCIO
# =========================================================

def limpar_telefone(phone):
    if pd.isna(phone): return None
    return "".join(filter(str.isdigit, str(phone)))

def gerar_sugestoes_fixas(area_atuacao):
    area_upper = str(area_atuacao).upper()
    sugestoes = []
    motivo = "Mix Geral"
    
    if any(x in area_upper for x in ['ESCOLA', 'EDUCACIONAL', 'CURSO']):
        sugestoes = ["📦 Papel Sulfite A4", "📦 Canetas Esferográficas", "📦 Marcadores de Quadro Branco"]
        motivo = "Volta às Aulas / Material de Secretaria"
    elif any(x in area_upper for x in ['SAUDE', 'HOSPITAL', 'CLINICA', 'FARMACIA']):
        sugestoes = ["📦 Luvas Descartáveis", "📦 Papel Toalha Interfolha", "📦 Copos Descartáveis"]
        motivo = "Higiene e Descartáveis"
    elif any(x in area_upper for x in ['INDUSTRIA', 'FABRICA', 'LOGISTICA', 'TRANSPORTE']):
        sugestoes = ["📦 Fita Adesiva", "📦 Filme Stretch", "📦 EPIs Básicos"]
        motivo = "Expedição e Segurança"
    else:
        sugestoes = ["📦 Kit Café (Copos + Açúcar)", "📦 Material de Escritório Básico", "📦 Produtos de Limpeza"]
        motivo = "Uso Geral Corporativo"
        
    return sugestoes, motivo

# =========================================================
#  FUNÇÕES DE BACKEND (COM CORREÇÃO DE ERRO DE COLUNA)
# =========================================================

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

def carregar_clientes(token):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Tenta carregar TUDO (incluindo campos novos)
    fields_full = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj,tentativa_1,tentativa_2,tentativa_3"
    
    # 2. Se der erro (porque campos não existem), carrega só o BÁSICO (Segurança)
    fields_safe = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj"
    
    df = pd.DataFrame()
    colunas_faltantes = False

    try:
        # TENTATIVA 1: Completa
        url = f"{base_url}/items/clientes?limit=-1&fields={fields_full}"
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        
        if r.status_code == 200:
            df = pd.DataFrame(r.json()['data'])
        else:
            # TENTATIVA 2: Fallback de Segurança
            colunas_faltantes = True
            url_safe = f"{base_url}/items/clientes?limit=-1&fields={fields_safe}"
            r_safe = requests.get(url_safe, headers=headers, timeout=10, verify=False)
            if r_safe.status_code == 200:
                df = pd.DataFrame(r_safe.json()['data'])
                # Cria colunas vazias na memória para o app não quebrar
                df['tentativa_1'] = None
                df['tentativa_2'] = None
                df['tentativa_3'] = None

        if not df.empty:
            # Processamento
            df['data_temp'] = pd.to_datetime(df['data_ultima_compra'], errors='coerce')
            df['Ultima_Compra'] = df['data_temp'].dt.strftime('%d/%m/%Y').fillna("-")
            hoje = pd.Timestamp.now()
            df['dias_sem_compra'] = (hoje - df['data_temp']).dt.days.fillna(9999).astype(int)
            
            def definir_cat(row):
                if 'status_carteira' in row and row['status_carteira']: return row['status_carteira']
                dias = row['dias_sem_compra']
                if dias > 365: return "Crítico"
                if dias > 180: return "Inativo"
                return "Ativo"
            
            df['Categoria_Cliente'] = df.apply(definir_cat, axis=1)
            df['GAP (dias)'] = df['dias_sem_compra']
            
            # Limpeza de Nones para edição
            for col in ['tentativa_1', 'tentativa_2', 'tentativa_3']:
                df[col] = df[col].fillna("")

            if colunas_faltantes:
                st.toast("⚠️ Aviso: As colunas de 'Tentativa' ainda não existem no Directus. As edições não serão salvas até você criá-las lá.", icon="⚠️")
                
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

def config_smtp_crud(token, payload=None):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{base_url}/items/config_smtp"
    if payload:
        check = requests.get(url, headers=headers, verify=False)
        if check.status_code == 200 and len(check.json()['data']) > 0:
            requests.patch(f"{url}/{check.json()['data'][0]['id']}", json=payload, headers=headers, verify=False)
        else:
            requests.post(url, json=payload, headers=headers, verify=False)
        return True
    else:
        r = requests.get(url, headers=headers, verify=False)
        if r.status_code == 200 and r.json()['data']: return r.json()['data'][0]
        return None

def registrar_log(token, pj_id, assunto, corpo, status):
    try:
        base_url = DIRECTUS_URL.rstrip('/')
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "cliente_pj_id": str(pj_id), "assunto_gerado": assunto, "corpo_email": corpo, 
            "status_envio": status, "data_envio": datetime.now().isoformat()
        }
        requests.post(f"{base_url}/items/historico_envios", json=payload, headers=headers, verify=False)
    except: pass

def gerar_email_ia(cliente, ramo, data_compra, campanha):
    if not GEMINI_API_KEY: return "Erro IA", "Sem Chave API configurada"
    camp_nome = campanha.get('nome_campanha', 'Retomada') if campanha else 'Contato'
    prompt = f"""
    Escreva um email B2B curto para {cliente} ({ramo}). 
    Ultima compra: {data_compra}. Campanha: {camp_nome}.
    Saída: ASSUNTO|CORPO_HTML
    """
    try:
        model = genai.GenerativeModel('gemini-pro')
        resp = model.generate_content(prompt)
        txt = resp.text.strip()
        if "|" in txt: return txt.split("|", 1)
        return "Contato Elo", txt
    except Exception as e: return "Erro", str(e)

def enviar_email(conf, para, assunto, corpo):
    try:
        msg = MIMEMultipart()
        msg['From'] = conf['smtp_user']
        msg['To'] = para
        msg['Subject'] = assunto
        msg.attach(MIMEText(f"{corpo}<br><br>{conf.get('assinatura_html','')}", 'html'))
        s = smtplib.SMTP(conf['smtp_host'], conf['smtp_port'])
        s.starttls()
        s.login(conf['smtp_user'], conf['smtp_pass_app'])
        s.sendmail(conf['smtp_user'], para, msg.as_string())
        s.quit()
        return True, "Enviado"
    except Exception as e: return False, str(e)

# =========================================================
#  INTERFACE (STREAMLIT)
# =========================================================

if 'token' not in st.session_state:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br><h1 style='text-align:center; color:#E31937'>🦅 NeuroSales CRM</h1>", unsafe_allow_html=True)
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        if st.button("ENTRAR", use_container_width=True):
            token, user = login_directus_debug(email, senha)
            if token:
                st.session_state['token'] = token
                st.session_state['user'] = user
                st.rerun()
    st.stop()

token = st.session_state['token']
user = st.session_state['user']

with st.sidebar:
    st.markdown(f"<h2 style='color: #E31937; text-align: center;'>🦅 ELO FLOW</h2>", unsafe_allow_html=True)
    st.write(f"👤 **{user.get('first_name', 'Vendedor')}**")
    if st.button("Sair"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    with st.expander("⚙️ Configurar E-mail (SMTP)"):
        conf = config_smtp_crud(token)
        h = st.text_input("Host", value=conf['smtp_host'] if conf else "smtp.gmail.com")
        p = st.number_input("Porta", value=conf['smtp_port'] if conf else 587)
        u = st.text_input("Email", value=conf['smtp_user'] if conf else "")
        pw = st.text_input("Senha App", type="password", value=conf['smtp_pass_app'] if conf else "")
        ass = st.text_area("Assinatura HTML", value=conf['assinatura_html'] if conf else "")
        if st.button("Salvar Config"):
            payload = {"smtp_host": h, "smtp_port": int(p), "smtp_user": u, "smtp_pass_app": pw, "assinatura_html": ass}
            config_smtp_crud(token, payload)
            st.success("Salvo!")

df = carregar_clientes(token)
campanha = carregar_campanha_ativa(token)

if df.empty:
    st.warning("⚠️ Sua carteira está vazia ou falha ao carregar (Verifique conexão ou colunas no Directus).")
    st.stop()

st.title(f"Visão Geral - {user.get('first_name','')}")
k1, k2, k3 = st.columns(3)
k1.markdown(f"<div class='metric-card'><h3>Total Clientes</h3><h1>{len(df)}</h1></div>", unsafe_allow_html=True)
inativos = len(df[df['Categoria_Cliente'].astype(str).str.contains('Inativo|Frio|Crítico', case=False)])
k2.markdown(f"<div class='metric-card'><h3>Oportunidades (Inativos/Crít.)</h3><h1 style='color:#E31937'>{inativos}</h1></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='metric-card'><h3>Campanha</h3><h4>{campanha['nome_campanha'] if campanha else 'Nenhuma'}</h4></div>", unsafe_allow_html=True)

st.markdown("### 🔍 Filtros Globais")
c_f1, c_f2 = st.columns(2)
with c_f1:
    opcoes_status = sorted(list(df['Categoria_Cliente'].unique()))
    filtro_status = st.multiselect("Filtrar por Status (Carteira):", options=opcoes_status, default=opcoes_status)
with c_f2:
    opcoes_area = sorted([str(x) for x in df['area_atuacao'].unique() if x is not None])
    filtro_area = st.multiselect("Filtrar por Área de Atuação:", options=opcoes_area, default=opcoes_area)

df_filtrado = df.copy()
if filtro_status:
    df_filtrado = df_filtrado[df_filtrado['Categoria_Cliente'].isin(filtro_status)]
if filtro_area:
    df_filtrado = df_filtrado[df_filtrado['area_atuacao'].astype(str).isin(filtro_area)]

st.divider()

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("🚀 Modo de Ataque (Vendas)")
    if not df_filtrado.empty:
        df_filtrado['label_select'] = df_filtrado['razao_social'] + " (" + df_filtrado['Ultima_Compra'] + ")"
        opcoes = sorted(df_filtrado['label_select'].tolist())
        
        # --- CORREÇÃO DO SELECTBOX: AGORA ELE OBEDECE AO SESSION STATE ---
        if "sb_principal" not in st.session_state:
            st.session_state["sb_principal"] = "Selecione..."
        
        # Garante que o valor no session state é válido para a lista atual
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
            sugestoes, motivo_sugestao = gerar_sugestoes_fixas(area_cli)
            html_sugestoes = "".join([f"<div class='sku-item'>{s}</div>" for s in sugestoes])
            script_msg = f"Olá! Sou da Elo Brindes. Vi que sua última compra foi há {dias} dias. Temos novidades para {area_cli}."
            
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
                    <div class="foco-item"><b>📅 Compra</b>{cli['Ultima_Compra']}</div>
                    <div class="foco-item"><b>⚠️ Status</b>{cli['Categoria_Cliente']}</div>
                </div>
                <div class="sugestao-box">
                    <div class="sugestao-title">🎯 Sugestão ({area_cli})</div>
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
                if email_cli and "@" in email_cli:
                    link_gmail = f"https://mail.google.com/mail/?view=cm&fs=1&to={email_cli}&su=Contato Elo&body={script_msg}"
                    st.link_button("📧 Gmail", link_gmail, use_container_width=True)
            with b3:
                if st.button("✨ IA Magica", use_container_width=True):
                    if not GEMINI_API_KEY: st.error("Sem Chave IA")
                    else:
                        subj, body = gerar_email_ia(cli['razao_social'], area_cli, cli['Ultima_Compra'], campanha)
                        st.session_state['ia_result'] = {'subj': subj, 'body': body, 'email': email_cli}
            
            if 'ia_result' in st.session_state:
                res = st.session_state['ia_result']
                st.info(f"Assunto: {res['subj']}")
                st.markdown(res['body'], unsafe_allow_html=True)
                if st.button("🚀 Enviar Email IA Agora"):
                    conf = config_smtp_crud(token)
                    if conf:
                        ok, msg = enviar_email(conf, res['email'], res['subj'], res['body'])
                        if ok: st.success("Enviado!"); registrar_log(token, cli['pj_id'], res['subj'], res['body'], "Sucesso")
                        else: st.error(f"Erro: {msg}")
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
            # Tenta sincronizar atualização também se possível, mas mantendo simples
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
    else:
        st.write("Sem dados.")

st.divider()
c_list1, c_list2 = st.columns([4, 1])
with c_list1:
    st.subheader("📋 Lista Geral (Editável)")

todas_colunas = list(df.columns)
# Remove ID da lista padrão de exibição
colunas_padrao = [c for c in ['pj_id', 'razao_social', 'Categoria_Cliente', 'area_atuacao', 'Ultima_Compra', 'GAP (dias)', 'tentativa_1', 'tentativa_2', 'tentativa_3', 'telefone_1'] if c in todas_colunas]

colunas_selecionadas = st.multiselect(
    "Selecione as colunas para exibir/editar:",
    options=todas_colunas,
    default=colunas_padrao
)

if not df_filtrado.empty:
    config_cols = {
        "pj_id": st.column_config.TextColumn("ID Loja", disabled=True),
        "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
        "Categoria_Cliente": st.column_config.TextColumn("Status", disabled=True),
        "Ultima_Compra": st.column_config.TextColumn("Ult. Compra", disabled=True),
        "GAP (dias)": st.column_config.NumberColumn("GAP (dias)", disabled=True),
        "id": None, # <--- Oculta o ID totalmente da visão
        "Ação": st.column_config.CheckboxColumn("➡️ Abrir", help="Clique para abrir os dados deste cliente lá em cima", default=False)
    }

    # Adiciona a coluna de botão/ação no inicio
    df_filtrado.insert(0, "Ação", False)

    # Exibe editor
    edicoes = st.data_editor(
        df_filtrado[["Ação"] + colunas_selecionadas + ['id']], 
        key="editor_dados",
        hide_index=True,
        column_config=config_cols,
        use_container_width=True,
        num_rows="fixed"
    )

    # --- LÓGICA DO CLIQUE NA AÇÃO (BOTÃO) ---
    if "editor_dados" in st.session_state:
        mudancas = st.session_state["editor_dados"]["edited_rows"]
        for idx, val in mudancas.items():
            if "Ação" in val and val["Ação"] == True:
                # O usuário clicou no checkbox "Ação"
                try:
                    cliente_alvo = df_filtrado.iloc[idx]['label_select']
                    # AQUI ESTÁ O PULO DO GATO: Atualiza diretamente a chave do Selectbox
                    st.session_state["sb_principal"] = cliente_alvo
                    st.rerun() 
                except: pass

    with c_list2:
        st.write("") 
        st.write("") 
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            if "editor_dados" in st.session_state and st.session_state["editor_dados"]["edited_rows"]:
                alteracoes = st.session_state["editor_dados"]["edited_rows"]
                sucessos = 0
                erros = 0
                
                progresso = st.progress(0)
                total = len(alteracoes)
                idx = 0

                for i, mudancas in alteracoes.items():
                    # Pula se for só o clique do botão Ação
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
                    
                    idx += 1
                    progresso.progress(idx / total)
                
                time.sleep(0.5)
                progresso.empty()
                
                if erros == 0:
                    if sucessos > 0:
                        st.success(f"✅ {sucessos} registros atualizados com sucesso!")
                        time.sleep(1)
                        st.rerun() 
                else:
                    st.warning(f"⚠️ {sucessos} salvos, mas {erros} falharam.")
            else:
                st.info("Nenhuma alteração detectada para salvar.")
else:
    st.write("Nenhum dado para exibir com os filtros atuais.")
