import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, date
import os
import io
import urllib.parse
import textwrap  # <--- IMPORTAÇÃO ESSENCIAL PARA RESOLVER O BLOCO DE CÓDIGO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Elo Flow - Prospecção", layout="wide", page_icon="🦅")

# --- CSS VISUAL (ESTILOS CORRIGIDOS) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    /* Força o fundo geral e texto base */
    .stApp { 
        background-color: #050505; 
        color: #E5E7EB; 
        font-family: 'Inter', sans-serif; 
    }
    
    section[data-testid="stSidebar"] { background-color: #121212; border-right: 1px solid #333; }
    
    /* Estilo dos Cards (Fundo Escuro com Texto Branco Forçado) */
    .foco-card {
        background-color: #151515 !important;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #333;
        border-left: 6px solid #E31937;
        margin-bottom: 20px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
    }
    
    /* Grid de informações dentro do card */
    .foco-grid {
        display: grid;
        grid-template-columns: 1fr 1fr; /* Duas colunas */
        gap: 15px;
        margin-top: 20px;
        font-size: 15px;
    }
    
    /* Itens individuais (Caixinhas cinzas) */
    .foco-item {
        background-color: #252525 !important;
        color: #FFFFFF !important; /* Texto BRANCO forçado */
        padding: 12px 16px;
        border-radius: 8px;
        border: 1px solid #3a3a3a;
        line-height: 1.4;
    }

    /* Labels dentro dos itens (Negrito Vermelho) */
    .foco-item b {
        color: #E31937 !important; /* Vermelho da marca */
        font-weight: 700;
        display: block; /* Quebra linha para o título ficar em cima */
        font-size: 12px;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    
    /* Caixa de Sugestão (Amarela) - Destaque Sazonalidade */
    .sugestao-box {
        background-color: #2D2006 !important;
        border: 1px solid #B45309;
        border-radius: 8px;
        padding: 16px;
        margin-top: 20px;
    }
    .sugestao-title {
        color: #FBBF24 !important; /* Amarelo ouro */
        font-weight: 700;
        font-size: 16px;
        margin-bottom: 12px;
        display: flex; align-items: center; gap: 8px;
    }
    .sku-item {
        background-color: rgba(251, 191, 36, 0.15);
        color: #FCD34D !important; /* Texto amarelo claro */
        padding: 6px 10px;
        border-radius: 4px;
        margin-bottom: 6px;
        font-size: 14px;
        border: 1px solid rgba(251, 191, 36, 0.2);
    }

    /* Box de Observação e Script */
    .foco-obs, .script-box {
        background-color: #1E1E1E !important;
        padding: 15px;
        border-radius: 8px;
        margin-top: 20px;
        border: 1px solid #333;
        color: #E0E0E0 !important;
        font-size: 14px;
        font-style: italic;
    }
    .script-box {
        border-left: 4px solid #E31937;
        background-color: #2A1015 !important; /* Fundo avermelhado bem escuro */
    }
    
    /* Botões */
    div.stButton > button { background-color: #E31937; color: white; border: none; width: 100%; border-radius: 6px; }
    div.stButton > button:hover { background-color: #C2132F; color: white; border-color: #C2132F; }
</style>
""", unsafe_allow_html=True)

pio.templates.default = "plotly_dark"

# --- CONFIGURAÇÃO DE PASTAS ---
DATA_DIR = "/app/data" 
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_FILE = os.path.join(DATA_DIR, "db_elo_flow.csv")        
CACHE_FILE = os.path.join(DATA_DIR, "cache_dados.xlsx")
PRODUTOS_FILE = os.path.join(DATA_DIR, "mais_pedidos.csv") 

# --- FUNÇÕES AUXILIARES ---

def carregar_crm_db():
    cols_padrao = ['pj_id', 'status_venda', 'ja_ligou', 'obs', 'data_interacao', 
                   'data_tentativa_1', 'data_tentativa_2', 'data_tentativa_3',
                   'gap_1_2', 'gap_2_3']
    
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE, dtype={'pj_id': str})
        for col in cols_padrao:
            if col not in df.columns:
                df[col] = None
        return df
    else:
        return pd.DataFrame(columns=cols_padrao)

def salvar_alteracoes(df_editor, df_original_crm):
    cols_salvar = ['pj_id', 'status_venda', 'ja_ligou', 'obs', 
                   'data_tentativa_1', 'data_tentativa_2', 'data_tentativa_3',
                   'gap_1_2', 'gap_2_3']
    
    novos_dados = df_editor[cols_salvar].copy()
    novos_dados['data_interacao'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for col in ['data_tentativa_1', 'data_tentativa_2', 'data_tentativa_3']:
        novos_dados[col] = pd.to_datetime(novos_dados[col], errors='coerce').dt.strftime('%Y-%m-%d')

    novos_dados = novos_dados.drop_duplicates()
    
    crm_atualizado = df_original_crm[~df_original_crm['pj_id'].isin(novos_dados['pj_id'])]
    crm_final = pd.concat([crm_atualizado, novos_dados], ignore_index=True)
    
    crm_final.to_csv(DB_FILE, index=False)
    return crm_final

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='EloFlow_Dados')
    return output.getvalue()

def limpar_telefone(phone):
    if pd.isna(phone): return None
    return "".join(filter(str.isdigit, str(phone)))

# --- LEITURA DO EXCEL DE CLIENTES ---
@st.cache_data
def carregar_excel(path_or_file):
    try:
        xls = pd.ExcelFile(path_or_file)
        dfs = []
        for sheet_name in xls.sheet_names:
            name_upper = sheet_name.upper()
            
            if "INATIVO" in name_upper: categoria = "Inativos (Recuperação)"
            elif "FRIO" in name_upper: categoria = "Frios (Antigos)"
            elif "ATIVO" in name_upper: categoria = "Ativos (Carteira)"
            else: continue 
            
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df['Categoria_Cliente'] = categoria
            
            if 'DATA_EXIBICAO' in df.columns:
                df['data_temp'] = pd.to_datetime(df['DATA_EXIBICAO'], errors='coerce', dayfirst=True)
                df['Ultima_Compra'] = df['data_temp'].dt.strftime('%d/%m/%Y').fillna("-")
                hoje = pd.Timestamp.now()
                df['dias_sem_compra'] = (hoje - df['data_temp']).dt.days.fillna(9999).astype(int)
            else:
                df['Ultima_Compra'] = "-"
                df['dias_sem_compra'] = 9999
            
            # Normalização de colunas
            cols_check = {'area_atuacao_nome': 'Indefinido', 'telefone_1': '', 'email_1': '', 'pj_id': '', 'razao_social': ''}
            for col, val in cols_check.items():
                if col not in df.columns: df[col] = val
                else: df[col] = df[col].fillna(val)

            if 'pj_id' in df.columns:
                df['pj_id'] = df['pj_id'].astype(str).str.replace(r'\.0$', '', regex=True)

            dfs.append(df)
            
        if not dfs: return None
        
        df_final = pd.concat(dfs, ignore_index=True)
        df_final = df_final.drop_duplicates() 
        return df_final

    except Exception as e:
        return None

# --- LEITURA DO EXCEL DE PRODUTOS (MAIS PEDIDOS) ---
@st.cache_data
def carregar_produtos_sugestao(path_or_file):
    try:
        # Tenta ler csv ou excel
        if str(path_or_file).endswith('.csv'):
            df = pd.read_csv(path_or_file, sep=None, engine='python') 
        else:
            df = pd.read_excel(path_or_file)
            
        # Normalizar colunas para maiusculo para facilitar busca
        df.columns = [c.upper().strip() for c in df.columns]
        
        # Identificar colunas chaves (Adaptar conforme seu CSV)
        col_desc = next((c for c in df.columns if 'DESC' in c or 'NOME' in c or 'PRODUTO' in c), None)
        col_id = next((c for c in df.columns if 'COD' in c or 'SKU' in c), None)
        
        if col_desc:
            df = df.rename(columns={col_desc: 'PRODUTO_NOME'})
        if col_id:
            df = df.rename(columns={col_id: 'SKU'})
        
        # Garante que tem a coluna nome, se não tiver cria uma dummy
        if 'PRODUTO_NOME' not in df.columns:
             # Tenta pegar a primeira coluna de texto
             df['PRODUTO_NOME'] = df.iloc[:, 0].astype(str)

        return df
    except Exception as e:
        return None

# --- MOTOR DE SUGESTÃO (INTELIGÊNCIA DE VENDAS JANEIRO) ---
def gerar_sugestoes_janeiro(area_atuacao, df_produtos):
    """
    Cruza Área de Atuação com Palavras-Chave de Produtos para Janeiro.
    """
    if df_produtos is None or df_produtos.empty:
        return [], "Sem catálogo carregado."

    # Regras de Negócio: Área -> Palavras Chave
    regras_janeiro = {
        'EDUCACIONAL': ['PAPEL', 'CANETA', 'CADERNO', 'ESCOLA', 'LÁPIS', 'SULFITE', 'RESMA', 'TINTA', 'APAGADOR'],
        'ESCOLA': ['PAPEL', 'CANETA', 'CADERNO', 'ESCOLA', 'LÁPIS', 'SULFITE', 'RESMA'],
        'INDÚSTRIA': ['EPI', 'LUVA', 'OCULOS', 'CAPACETE', 'FERRAMENTA', 'FITA', 'ADHESIVO', 'MANUTENCAO', 'SOLDA', 'ABRASIVO'],
        'INDUSTRIA': ['EPI', 'LUVA', 'OCULOS', 'CAPACETE', 'FERRAMENTA', 'FITA', 'ADHESIVO', 'MANUTENCAO'],
        'SAÚDE': ['LUVA', 'MASCARA', 'HIGIENE', 'ALCOOL', 'DESCARTAVEL', 'SERINGA', 'GAZE', 'LENÇOL'],
        'FARMÁCIA': ['SOLAR', 'HIDRATANTE', 'VITAMINA', 'VERAO', 'REPELENTE'],
        'FARMACIA': ['SOLAR', 'HIDRATANTE', 'VITAMINA', 'VERAO', 'REPELENTE'],
        'TRANSPORTE': ['OLEO', 'PNEU', 'MANUTENCAO', 'LIMPEZA', 'AUTOMOTIVO', 'GRAXA', 'LUBRIFICANTE'],
        'LOGÍSTICA': ['FITA', 'ESTILETE', 'EMBALAGEM', 'PLASTICO', 'PALETE', 'STRETCH'],
        'COMÉRCIO': ['BOBINA', 'EMBALAGEM', 'SACOLA', 'ETIQUETA', 'PREÇO'],
        'SERVIÇOS': ['CAFE', 'COPO', 'LIMPEZA', 'PAPEL', 'ESCRITORIO', 'HIGIENE']
    }

    area_upper = str(area_atuacao).upper()
    keywords = []

    # Tenta dar match na área
    matched_key = "Geral"
    for key, words in regras_janeiro.items():
        if key in area_upper:
            keywords = words
            matched_key = key
            break
    
    # Se não achou regra específica, usa regra geral de Janeiro (Verão/Volta aulas)
    if not keywords:
        keywords = ['PAPEL', 'VERAO', 'VENTILADOR', 'AGUA', 'ORGANIZADOR', 'OFERTA']
        matched_key = "Geral (Janeiro)"

    # Filtra o DataFrame de Produtos
    mask = df_produtos['PRODUTO_NOME'].astype(str).str.upper().apply(lambda x: any(k in x for k in keywords))
    df_sugestao = df_produtos[mask].head(6) # Pega os top 6 dessa categoria
    
    lista_skus = []
    if not df_sugestao.empty:
        for _, row in df_sugestao.iterrows():
            nome = row['PRODUTO_NOME']
            sku = row.get('SKU', '-')
            # Tenta formatar bonito se tiver SKU
            if str(sku) != '-' and str(sku) != 'nan':
                 lista_skus.append(f"📦 <b>{sku}</b> - {nome}")
            else:
                 lista_skus.append(f"📦 {nome}")
    else:
        lista_skus.append("⚠️ Nenhum produto específico encontrado para esta área na lista de Mais Pedidos.")

    motivo = f"Foco em produtos de <b>{matched_key}</b> (Sazonalidade Janeiro)."
    return lista_skus, motivo

# --- SIDEBAR & UPLOAD ---
st.sidebar.markdown(f"<h2 style='color: #E31937; text-align: center;'>🦅 ELO FLOW</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

arquivo_carregado = None
produtos_carregado = None

# Upload Clientes
st.sidebar.subheader("1. Base de Clientes")
if os.path.exists(CACHE_FILE):
    st.sidebar.success("✅ Clientes carregados!")
    if st.sidebar.button("🗑️ Trocar Lista Clientes"):
        try:
            os.remove(CACHE_FILE)
            carregar_excel.clear() 
            st.rerun()
        except: pass
    arquivo_carregado = CACHE_FILE
else:
    uploaded_file = st.sidebar.file_uploader("📂 Importar Planilha Clientes (.xlsx)", type=["xlsx"], key="up_cli")
    if uploaded_file:
        with open(CACHE_FILE, "wb") as f:
            f.write(uploaded_file.getbuffer())
        carregar_excel.clear() 
        st.rerun()

# Upload Produtos (Mais Pedidos)
st.sidebar.markdown("---")
st.sidebar.subheader("2. Tabela Mais Pedidos")
if os.path.exists(PRODUTOS_FILE):
    st.sidebar.success("✅ Produtos carregados!")
    if st.sidebar.button("🗑️ Trocar Tabela Produtos"):
        try:
            os.remove(PRODUTOS_FILE)
            carregar_produtos_sugestao.clear()
            st.rerun()
        except: pass
    produtos_carregado = PRODUTOS_FILE
else:
    uploaded_prod = st.sidebar.file_uploader("📂 Importar Mais Pedidos (.csv/.xlsx)", type=["xlsx", "csv"], key="up_prod")
    if uploaded_prod:
        # Salva como CSV padronizado
        if uploaded_prod.name.endswith('.csv'):
            with open(PRODUTOS_FILE, "wb") as f:
                f.write(uploaded_prod.getbuffer())
        else:
            df_temp = pd.read_excel(uploaded_prod)
            df_temp.to_csv(PRODUTOS_FILE, index=False)
            
        carregar_produtos_sugestao.clear()
        st.rerun()

if not arquivo_carregado:
    st.info("👆 Por favor, comece importando a planilha de CLIENTES na barra lateral.")
    st.stop()

# --- CARGA DOS DADOS ---
df_raw = carregar_excel(arquivo_carregado)
df_produtos = carregar_produtos_sugestao(produtos_carregado) if produtos_carregado else None

if df_raw is None or df_raw.empty:
    st.error("Erro ao ler o arquivo de clientes.")
    st.stop()

if 'cnpj' in df_raw.columns:
    df_raw['cnpj'] = df_raw['cnpj'].astype(str).str.replace(r'\.0$', '', regex=True)
else:
    df_raw['cnpj'] = "-"

# Merge com CRM Local
df_crm = carregar_crm_db()
df_full = pd.merge(df_raw, df_crm, on='pj_id', how='left')

# Preenche vazios
df_full['status_venda'] = df_full['status_venda'].fillna('Não contatado')
df_full['ja_ligou'] = df_full['ja_ligou'].fillna(False)
df_full['obs'] = df_full['obs'].fillna('')
if 'gap_1_2' not in df_full.columns: df_full['gap_1_2'] = ""
if 'gap_2_3' not in df_full.columns: df_full['gap_2_3'] = ""

for col in ['data_tentativa_1', 'data_tentativa_2', 'data_tentativa_3']:
    if col in df_full.columns:
        df_full[col] = pd.to_datetime(df_full[col], errors='coerce')

# --- DASHBOARD ---
st.title("🦅 Visão Geral - Carteira")

c1, c2, c3 = st.columns(3)
cat = c1.multiselect("Categoria", df_full['Categoria_Cliente'].unique(), default=df_full['Categoria_Cliente'].unique())
sts = c2.multiselect("Status", df_full['status_venda'].unique(), default=df_full['status_venda'].unique())

with c3:
    todas_areas_opcoes = df_full['area_atuacao_nome'].unique()
    usar_todas = st.checkbox("Selecionar Todas as Áreas", value=True)
    if usar_todas:
        area = todas_areas_opcoes
        st.multiselect("Área", options=todas_areas_opcoes, default=todas_areas_opcoes, disabled=True)
    else:
        area = st.multiselect("Área", options=todas_areas_opcoes, default=todas_areas_opcoes)

df_view = df_full[
    (df_full['Categoria_Cliente'].isin(cat)) & 
    (df_full['status_venda'].isin(sts)) &
    (df_full['area_atuacao_nome'].isin(area))
].copy()

if 'dias_sem_compra' in df_view.columns:
    df_view = df_view.sort_values(by='dias_sem_compra', ascending=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Visível", len(df_view))
k2.metric("Oportunidades (Inativos)", len(df_view[df_view['Categoria_Cliente'].str.contains('Inativo', na=False)]))
k3.metric("Pendentes de Contato", len(df_view[df_view['status_venda'] == 'Não contatado']))
k4.metric("Em Negociação", len(df_view[df_view['status_venda'] == 'Em Negociação']))

st.divider()

# --- MODO DE ATAQUE (COM TEXTWRAP.DEDENT PARA RESOLVER O ERRO) ---
st.markdown("### 🚀 Modo de Ataque (Foco)")
col_sel, col_detalhe = st.columns([1, 2])

with col_sel:
    df_view['label_select'] = df_view['razao_social'] + " (" + df_view['Ultima_Compra'] + ")"
    opcoes_ataque = sorted(list(set(df_view['label_select'].tolist())))
    selecionado = st.selectbox("Busque por Razão Social:", ["Selecione..."] + opcoes_ataque)

if selecionado and selecionado != "Selecione...":
    cliente = df_view[df_view['label_select'] == selecionado].iloc[0]
    
    dias = cliente['dias_sem_compra'] if cliente['dias_sem_compra'] < 9000 else "Muitos"
    area_cli = str(cliente['area_atuacao_nome'])
    tel_raw = str(cliente['telefone_1'])
    email_cliente = str(cliente['email_1']).strip()
    obs_cliente = str(cliente['obs']).strip()
    status_cli = cliente['status_venda']
    tel_clean = limpar_telefone(tel_raw)
    
    # Lógica de Script Base
    if dias != "Muitos" and dias > 30:
        script_msg = f"Olá! Tudo bem? Sou da Elo. Vi que sua última compra foi há {dias} dias. Temos condições especiais para retomada agora em Janeiro."
    elif "Novo" in cliente['status_venda']:
        script_msg = f"Olá! Vi que vocês atuam com {area_cli} e gostaria de apresentar a Elo."
    else:
        script_msg = f"Olá! Gostaria de falar sobre oportunidades de Janeiro para a área de {area_cli}."

    # --- INTELIGÊNCIA DE PRODUTO ---
    sugestoes_skus, motivo_sugestao = gerar_sugestoes_janeiro(area_cli, df_produtos)
    html_sugestoes = "".join([f"<div class='sku-item'>{sku}</div>" for sku in sugestoes_skus])

    with col_detalhe:
        # AQUI ESTA O TRUQUE: textwrap.dedent remove a indentação inicial!
        # Isso garante que o Streamlit não confunda o HTML com bloco de código.
        html_card = textwrap.dedent(f"""
            <div class="foco-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2 style='margin:0; color: #FFF; font-size: 24px;'>🏢 {cliente['razao_social']}</h2>
                    <span style='background:#333; padding:4px 8px; border-radius:4px; font-size:12px; color:#aaa;'>ID: {cliente['pj_id']}</span>
                </div>
                
                <div class="foco-grid">
                    <div class="foco-item"><b>📍 Área / Segmento</b>{cliente['area_atuacao_nome']}</div>
                    <div class="foco-item"><b>📋 CNPJ</b>{cliente['cnpj']}</div>
                    <div class="foco-item"><b>📞 Telefone</b>{tel_raw}</div>
                    <div class="foco-item"><b>📧 E-mail</b>{email_cliente}</div>
                    <div class="foco-item"><b>📅 Última Compra</b>{cliente['Ultima_Compra']} <span style="color:#ff6b6b; font-size:12px;">({dias} dias)</span></div>
                    <div class="foco-item"><b>📊 Status Atual</b>{status_cli}</div>
                </div>

                <div class="sugestao-box">
                    <div class="sugestao-title">🎯 Oportunidade de Janeiro ({area_cli})</div>
                    <div style="margin-bottom:10px; font-size:14px; color:#ccc;"><i>💡 {motivo_sugestao}</i></div>
                    {html_sugestoes}
                </div>

                <div class="foco-obs">
                    <b style="color:#999; display:block; margin-bottom:5px; text-transform:uppercase; font-size:11px;">📝 Observação Salva:</b>
                    {obs_cliente if obs_cliente else "Nenhuma observação registrada."}
                </div>
                
                <div class="script-box">
                    <b style="color:#E31937; display:block; margin-bottom:5px; text-transform:uppercase; font-size:11px;">🗣️ Script Sugerido:</b>
                    "{script_msg}"
                </div>
            </div>
        """)
        st.markdown(html_card, unsafe_allow_html=True)
        
        b1, b2 = st.columns(2)
        with b1:
            if tel_clean and len(tel_clean) >= 10:
                link_wpp = f"https://wa.me/55{tel_clean}?text={script_msg.replace(' ', '%20')}"
                st.link_button(f"💬 Abrir WhatsApp ({tel_raw})", link_wpp, type="primary", use_container_width=True)
            else:
                st.warning(f"Telefone inválido: {tel_raw}")
        
        with b2:
            if email_cliente and email_cliente.lower() != "nan" and "@" in email_cliente:
                params = {"view": "cm", "fs": "1", "to": email_cliente, "su": f"Oportunidade Janeiro - {cliente['razao_social']}", "body": script_msg}
                link_gmail = f"https://mail.google.com/mail/?{urllib.parse.urlencode(params)}"
                st.link_button(f"📧 Abrir Gmail ({email_cliente})", link_gmail, use_container_width=True)
            else:
                st.warning("E-mail não cadastrado")

st.divider()

# --- TABELA DE TRABALHO ---
st.subheader("📋 Lista de Prospecção & Cadência")

col_config = {
    "pj_id": st.column_config.TextColumn("ID", disabled=True),
    "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
    "cnpj": st.column_config.TextColumn("CNPJ", disabled=True),
    "area_atuacao_nome": st.column_config.TextColumn("Área", disabled=True),
    "email_1": st.column_config.TextColumn("E-mail", disabled=True),
    "Ultima_Compra": st.column_config.TextColumn("Última Compra", disabled=True),
    "dias_sem_compra": st.column_config.NumberColumn("Dias Inativo", format="%d dias"),
    "telefone_1": st.column_config.TextColumn("Telefone", disabled=True),
    "status_venda": st.column_config.SelectboxColumn(
        "Status", 
        options=['Não contatado', 'Tentando Contato', 'Em Negociação', 'Fechado', 'Perdido', 'Novo'], 
        required=True
    ),
    "ja_ligou": st.column_config.CheckboxColumn("Ligou?"),
    "obs": st.column_config.TextColumn("Obs", width="large"),
    
    # DATAS E GAPS
    "data_tentativa_1": st.column_config.DateColumn("Tentativa 1", format="DD/MM/YYYY"),
    "data_tentativa_2": st.column_config.DateColumn("Tentativa 2", format="DD/MM/YYYY"),
    "data_tentativa_3": st.column_config.DateColumn("Tentativa 3", format="DD/MM/YYYY"),
    "gap_1_2": st.column_config.TextColumn("Intervalo 1-2 (Dias)", help="Digite manualmente"),
    "gap_2_3": st.column_config.TextColumn("Intervalo 2-3 (Dias)", help="Digite manualmente")
}

cols_display = [
    'pj_id', 'razao_social', 'cnpj', 'status_venda', 
    'data_tentativa_1', 'gap_1_2', 
    'data_tentativa_2', 'gap_2_3', 
    'data_tentativa_3',
    'obs', 'telefone_1', 'Ultima_Compra', 'email_1', 'area_atuacao_nome'
]

df_edit = st.data_editor(
    df_view[cols_display], 
    column_config=col_config, 
    hide_index=True, 
    use_container_width=True, 
    key="editor_crm", 
    height=600
)

# --- RODAPÉ ---
c_save, c_export = st.columns([1, 1])

with c_save:
    if st.button("💾 Salvar Alterações", type="primary"):
        salvar_alteracoes(df_edit, df_crm)
        st.toast("Dados Salvos!", icon="✅")
        import time
        time.sleep(1)
        st.rerun()

with c_export:
    excel_data = converter_para_excel(df_edit)
    st.download_button("📥 Baixar Planilha", data=excel_data, file_name="EloFlow_Full.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
