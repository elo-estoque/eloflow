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

# Ignorar avisos de SSL (necessário pois seu servidor não tem certificado válido)
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================================================
#  FUNÇÕES AUXILIARES E DE NEGÓCIO
# =========================================================

@st.cache_resource
def obter_modelo_compativel():
    if not GEMINI_API_KEY: return "gemini-pro"
    try:
        modelos = genai.list_models()
        modelos_validos = []
        for m in modelos:
            if 'generateContent' in m.supported_generation_methods:
                modelos_validos.append(m.name)
        
        for m in modelos_validos:
            if 'flash' in m: return m
        for m in modelos_validos:
            if 'pro' in m: return m
        
        if modelos_validos:
            return modelos_validos[0]
            
    except:
        pass
    return "gemini-1.5-flash"

def limpar_telefone(phone):
    if pd.isna(phone): return None
    return "".join(filter(str.isdigit, str(phone)))

def gerar_sugestoes_elo_brindes(area_atuacao):
    if not GEMINI_API_KEY:
        return ["🎁 Kit Boas Vindas Personalizado", "🎁 Caneta Metal Premium", "🎁 Caderno Moleskine com Logo"], "Sugestão Padrão (Sem IA)"
    
    try:
        nome_modelo = obter_modelo_compativel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = f"""
        Você é um consultor especialista da Elo Brindes (www.elobrindes.com.br).
        O cliente atua na área: '{area_atuacao}'.
        Sugira 3 brindes corporativos personalizados do catálogo da Elo Brindes que façam sentido para este ramo.
        Responda EXATAMENTE no formato: Produto A|Produto B|Produto C
        Não use introduções, apenas os nomes dos produtos.
        """
        response = model.generate_content(prompt)
        texto = response.text.strip()
        
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
    
    fields_full = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj,tentativa_1,tentativa_2,tentativa_3"
    fields_safe = "id,pj_id,razao_social,nome_fantasia,status_carteira,area_atuacao,data_ultima_compra,telefone_1,email_1,obs_gerais,cnpj"
    
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

def config_smtp_crud(token, payload=None):
    base_url = DIRECTUS_URL.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{base_url}/items/config_smtp"

    if payload:
        # Tenta verificar se já existe configuração
        try:
            check = requests.get(url, headers=headers, verify=False)
        except Exception as e:
            st.error(f"❌ Erro de conexão com Directus: {e}")
            return False

        if check.status_code != 200:
            st.error(f"❌ Erro ao acessar configurações no banco: {check.text}")
            return False

        data = check.json().get('data', [])
        
        if len(data) > 0:
            # ATUALIZA (PATCH)
            id_item = data[0]['id']
            r = requests.patch(f"{url}/{id_item}", json=payload, headers=headers, verify=False)
            if r.status_code == 200:
                return True
            else:
                st.error(f"❌ Erro ao salvar (PATCH). O Directus recusou: {r.text}")
                return False
        else:
            # CRIA (POST)
            r = requests.post(url, json=payload, headers=headers, verify=False)
            if r.status_code == 200:
                return True
            else:
                st.error(f"❌ Erro ao criar (POST). O Directus recusou: {r.text}")
                return False
    else:
        # APENAS LEITURA
        try:
            r = requests.get(url, headers=headers, verify=False)
            if r.status_code == 200 and r.json().get('data'): 
                return r.json()['data'][0]
        except: pass
        return None

def enviar_email_smtp(token, destinatario, assunto, mensagem_html, conf_smtp):
    if not conf_smtp: return False, "SMTP não configurado"
    try:
        msg = MIMEMultipart()
        msg['From'] = conf_smtp['smtp_user']
        msg['To'] = destinatario
        msg['Subject'] = assunto
        
        # --- LÓGICA INTELIGENTE DE HTML/TEXTO ---
        # Se detectar tags HTML comuns, assume que é código fonte e preserva
        if "<div" in mensagem_html or "<html" in mensagem_html or "<span" in mensagem_html or "<table" in mensagem_html or "<a href" in mensagem_html:
            corpo_completo = mensagem_html
        else:
            # Se for texto simples, converte quebras de linha em <br>
            corpo_completo = mensagem_html.replace("\n", "<br>")
            
        # Adiciona assinatura se não for um HTML completo (para não quebrar layout body/html fechados)
        if conf_smtp.get('assinatura_html') and "</body>" not in corpo_completo:
            corpo_completo += f"<br><br>{conf_smtp['assinatura_html']}"
            
        msg.attach(MIMEText(corpo_completo, 'html'))
        
        server = smtplib.SMTP(conf_smtp['smtp_host'], conf_smtp['smtp_port'])
        server.starttls()
        # Aqui é onde ocorre o login com a senha de app
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
        payload = {
            "cliente_pj_id": str(pj_id), "assunto_gerado": assunto, "corpo_email": corpo, 
            "status_envio": status, "data_envio": datetime.now().isoformat()
        }
        requests.post(f"{base_url}/items/historico_envios", json=payload, headers=headers, verify=False)
    except: pass

def gerar_email_ia(cliente, ramo, data_compra, campanha, usuario_nome, usuario_cargo):
    if not GEMINI_API_KEY: return "Erro IA", "Sem Chave API configurada"
    camp_nome = campanha.get('nome_campanha', 'Retomada') if campanha else 'Contato'
    
    prompt = f"""
    Você é {usuario_nome}, {usuario_cargo} da Elo Brindes.
    Escreva um email B2B curto e cordial para o cliente {cliente} (Ramo: {ramo}).
    Contexto: O cliente não compra desde {data_compra}.
    Motivo do contato: Campanha {camp_nome} e novidades no catálogo.
    Objetivo: Agendar uma breve conversa ou enviar catálogo atualizado.
    
    INSTRUÇÕES OBRIGATÓRIAS:
    1. Gere APENAS TEXTO SIMPLES (sem negrito, sem markdown, sem HTML).
    2. Separe o ASSUNTO do CORPO com '|||'.
    3. NÃO inclua 'Atenciosamente' ou assinatura no final, pois o sistema já coloca a sua.
    
    Saída esperada:
    Assunto aqui|||Olá Fulano, corpo do email aqui...
    """
    try:
        nome_modelo = obter_modelo_compativel()
        model = genai.GenerativeModel(nome_modelo)
        resp = model.generate_content(prompt)
        txt = resp.text.strip()
        
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

nome_usuario = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
primeiro_nome = user.get('first_name', '').strip().lower()
cargo_usuario = "Vendedora" if primeiro_nome.endswith("a") else "Vendedor"

# --- SIDEBAR (BARRA LATERAL) ---
with st.sidebar:
    st.markdown(f"<h2 style='color: #E31937; text-align: center;'>🦅 ELO FLOW</h2>", unsafe_allow_html=True)
    st.write(f"👤 **{nome_usuario}**")
    st.caption(f"💼 {cargo_usuario}")
    if st.button("Sair"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    
    with st.expander("⚙️ Configurar E-mail (SMTP)"):
        st.info("Necessário para o DISPARO EM MASSA.")
        conf = config_smtp_crud(token)
        
        # Carrega dados atuais do banco
        h = st.text_input("Host", value=conf['smtp_host'] if conf else "smtp.gmail.com")
        p = st.number_input("Porta", value=conf['smtp_port'] if conf else 587)
        u = st.text_input("Email", value=conf['smtp_user'] if conf else "")
        
        # Campo de senha com aviso importante
        pw_val = conf['smtp_pass_app'] if conf else ""
        pw = st.text_input("Senha App (Não use senha de login)", type="password", value=pw_val, help="Para Gmail, crie uma Senha de App em: Gerenciar Conta > Segurança > Verificação em 2 etapas > Senhas de App.")
        
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
                # Chama a função de salvar
                salvou = config_smtp_crud(token, payload)
                if salvou:
                    st.success("✅ Salvo com sucesso! Recarregando...")
                    time.sleep(1.5)
                    st.rerun() # <--- FORÇA O RECARREGAMENTO DA PÁGINA

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

if not df_filtrado.empty:
    df_filtrado['label_select'] = df_filtrado['razao_social'] + " (" + df_filtrado['Ultima_Compra'] + ")"

# --- LÓGICA DE GATILHO (Check prévio) ---
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

# --- BLOCO: DISPARO EM MASSA ---
with st.expander("📢 Disparo em Massa (Padrão para Vários Clientes)", expanded=False):
    st.markdown("⚠️ **Atenção:** Certifique-se de que configurou e salvou o SMTP na barra lateral antes de enviar.")
    
    col_m1, col_m2 = st.columns([1, 1])
    
    with col_m1:
        st.subheader("1. Selecione os Clientes")
        df_com_email = df_filtrado[df_filtrado['email_1'].str.contains('@', na=False)].copy()
        lista_emails_validos = df_com_email['label_select'].tolist()
        
        container_botoes = st.container()
        col_b1, col_b2 = container_botoes.columns(2)
        if col_b1.button("Selecionar Todos (Filtrados)"):
            st.session_state['selected_bulk'] = lista_emails_validos
        if col_b2.button("Limpar Seleção"):
            st.session_state['selected_bulk'] = []
            
        selecionados_bulk = st.multiselect(
            "Clientes Destinatários:", 
            options=lista_emails_validos,
            key='selected_bulk'
        )
        st.caption(f"Total Selecionado: {len(selecionados_bulk)} clientes")

    with col_m2:
        st.subheader("2. Defina a Mensagem")
        assunto_padrao = st.text_input("Assunto do E-mail", value=f"Novidades Elo Brindes - {campanha['nome_campanha'] if campanha else 'Especial'}")
        
        st.info("💡 Você pode colar código HTML (tabelas, imagens, cores) ou digitar texto normal aqui. O sistema detecta automaticamente.")
        corpo_padrao = st.text_area("Mensagem ou Código HTML", height=300, value=f"Olá,\n\nGostaria de apresentar as novidades da Elo Brindes para sua empresa.\n\nAguardo seu retorno.")
        
        if st.button("🚀 ENVIAR PARA TODOS SELECIONADOS", type="primary", use_container_width=True):
            # Recarrega a configuração na hora do clique para garantir que está atualizada
            conf_smtp = config_smtp_crud(token)
            
            if not conf_smtp or not conf_smtp.get('smtp_pass_app'):
                st.error("🚨 Configure o SMTP na barra lateral e clique em SALVAR primeiro!")
            elif len(selecionados_bulk) == 0:
                st.warning("Selecione pelo menos um cliente.")
            else:
                bar = st.progress(0)
                status_txt = st.empty()
                enviados = 0
                erros = 0
                log_erros = []
                
                for i, nome_cliente in enumerate(selecionados_bulk):
                    cli_row = df_com_email[df_com_email['label_select'] == nome_cliente].iloc[0]
                    email_dest = cli_row['email_1']
                    
                    status_txt.text(f"Enviando para {cli_row['razao_social']} ({email_dest})...")
                    
                    # Substituição simples de variável no texto
                    msg_final = corpo_padrao.replace("{cliente}", cli_row['razao_social'])
                    
                    sucesso, msg_log = enviar_email_smtp(token, email_dest, assunto_padrao, msg_final, conf_smtp)
                    
                    if sucesso:
                        enviados += 1
                        # Atualiza tentativa se estiver vazio
                        if not cli_row['tentativa_1']:
                            atualizar_cliente_directus(token, cli_row['id'], {"tentativa_1": datetime.now().strftime("%d/%m - Email em Massa")})
                    else:
                        erros += 1
                        log_erros.append(f"{cli_row['razao_social']}: {msg_log}")
                    
                    time.sleep(1.0) # Delay para evitar bloqueio SMTP
                    bar.progress((i + 1) / len(selecionados_bulk))
                
                status_txt.empty()
                bar.empty()
                
                if enviados > 0:
                    st.success(f"✅ Processo finalizado! {enviados} e-mails enviados com sucesso.")
                
                if erros > 0:
                    st.error(f"❌ Ocorreram {erros} erros de envio.")
                    with st.expander("Ver detalhes dos erros"):
                        for erro in log_erros:
                            st.write(erro)
                
                if erros == 0 and enviados > 0:
                    time.sleep(2)
                    st.rerun()

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
                if email_cli and "@" in email_cli:
                    link_gmail = f"https://mail.google.com/mail/?view=cm&fs=1&to={email_cli}&su=Contato Elo&body={script_msg}"
                    st.link_button("📧 Gmail", link_gmail, use_container_width=True)
            with b3:
                # --- BOTÃO MÁGICO ---
                if st.button("✨ IA Magica", use_container_width=True):
                    if not GEMINI_API_KEY: 
                        st.error("Sem Chave IA")
                    else:
                        with st.spinner("🤖 Escrevendo e-mail..."):
                            subj, body = gerar_email_ia(cli['razao_social'], area_cli, cli['Ultima_Compra'], campanha, nome_usuario, cargo_usuario)
                            st.session_state['ia_result'] = {'subj': subj, 'body': body, 'email': email_cli}
            
            # --- ÁREA DE RESULTADO DA IA ---
            if 'ia_result' in st.session_state:
                res = st.session_state['ia_result']
                
                assinatura_automatica = f"\n\nAtenciosamente,\n\n{nome_usuario}\n{cargo_usuario}\nElo Brindes"
                corpo_final = res['body'] + assinatura_automatica
                
                st.info(f"Assunto: {res['subj']}")
                st.text_area("Prévia da Mensagem:", value=corpo_final, height=200, disabled=True)
                
                subject_enc = urllib.parse.quote(res['subj'])
                body_enc = urllib.parse.quote(corpo_final)
                
                # --- LINK PARA GOOGLE WORKSPACE/GMAIL ---
                link_gmail_final = f"https://mail.google.com/mail/?view=cm&fs=1&to={res['email']}&su={subject_enc}&body={body_enc}"
                
                st.link_button("📧 Abrir no Gmail", link_gmail_final, type="primary", use_container_width=True)

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
    else:
        st.write("Sem dados.")

st.divider()
st.subheader("📋 Lista Geral (Editável - Auto Save)")

todas_colunas = list(df.columns)
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

    # --- LÓGICA DE AUTO-SAVE ---
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
