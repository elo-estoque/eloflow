import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Elo Flow", 
    layout="wide", 
    page_icon="🦅",
    initial_sidebar_state="expanded"
)

# --- 2. CSS PERSONALIZADO (IDENTIDADE VISUAL ELO) ---
st.markdown("""
<style>
    /* Fonte Inter */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    /* Variáveis Globais (Dark Mode + Vermelho Elo) */
    :root {
        --brand-dark: #050505;
        --brand-card: #121212;
        --brand-wine: #E31937;
        --text-main: #E5E7EB;
        --text-muted: #9CA3AF;
        --border-color: rgba(255, 255, 255, 0.1);
    }

    /* Fundo Geral */
    .stApp {
        background-color: var(--brand-dark);
        color: var(--text-main);
        font-family: 'Inter', sans-serif;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: var(--brand-card);
        border-right: 1px solid var(--border-color);
    }

    /* Métricas (Cards) */
    div[data-testid="stMetric"] {
        background-color: var(--brand-card);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid var(--border-color);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetricLabel"] { color: var(--text-muted); font-size: 0.9rem; }
    div[data-testid="stMetricValue"] { color: var(--brand-wine); font-weight: 700; }

    /* Botões Primários */
    div.stButton > button {
        background-color: var(--brand-wine);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
        width: 100%;
    }
    div.stButton > button:hover {
        background-color: #C2132F;
        box-shadow: 0 0 10px rgba(227, 25, 55, 0.5);
        color: white;
    }

    /* Tabela Editável */
    div[data-testid="stDataEditor"] {
        border: 1px solid var(--border-color);
        border-radius: 8px;
        background-color: var(--brand-card);
    }

    /* Títulos e Textos */
    h1, h2, h3 { color: var(--text-main) !important; }
    
    /* Remove padding excessivo do topo */
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# Define tema escuro para os gráficos
pio.templates.default = "plotly_dark"

# --- 3. FUNÇÕES DE BANCO DE DADOS (PERSISTÊNCIA) ---
DB_FILE = "db_elo_flow.csv"

def carregar_crm_db():
    """Carrega o histórico de interações ou cria novo se não existir."""
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE, dtype={'pj_id': str})
    else:
        return pd.DataFrame(columns=['pj_id', 'status_venda', 'ja_ligou', 'obs', 'data_interacao'])

def salvar_alteracoes(df_editor, df_original_crm):
    """Salva as edições do vendedor no CSV local."""
    # Prepara os dados novos
    novos_dados = df_editor[['pj_id', 'status_venda', 'ja_ligou', 'obs']].copy()
    novos_dados['data_interacao'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Remove registros antigos desses IDs para atualizar
    crm_atualizado = df_original_crm[~df_original_crm['pj_id'].isin(novos_dados['pj_id'])]
    
    # Concatena e salva
    crm_final = pd.concat([crm_atualizado, novos_dados], ignore_index=True)
    crm_final.to_csv(DB_FILE, index=False)
    return crm_final

# --- 4. BARRA LATERAL (MENU E UPLOAD) ---
st.sidebar.markdown(f"<h2 style='color: #E31937; text-align: center; margin-bottom: 0;'>ELO FLOW</h2>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: #666; font-size: 0.8rem;'>Intelligence System</p>", unsafe_allow_html=True)
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader("📂 Importar Planilha (Excel)", type=["xlsx"])

# --- 5. LÓGICA DE CARREGAMENTO ---
@st.cache_data
def carregar_excel(file):
    try:
        xls = pd.ExcelFile(file)
        dfs = []
        for sheet_name in xls.sheet_names:
            name_upper = sheet_name.upper()
            categoria = "Outros"
            # Detecção inteligente das abas
            if "ATIVO" in name_upper: categoria = "Ativos (2025)"
            elif "INATIVO" in name_upper: categoria = "Inativos (2020-2024)"
            elif "FRIO" in name_upper: categoria = "Frios (<2020)"
            
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df['Categoria_Cliente'] = categoria
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True)
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None

# Se não tiver arquivo, mostra tela inicial
if not uploaded_file:
    st.info("👆 Por favor, faça o upload da planilha 'ADRIELLY - CLIENTE' na barra lateral.")
    
    # Exibe um resumo vazio só para dar visual
    st.markdown("### 📊 Aguardando dados...")
    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes Ativos", "--")
    c2.metric("Clientes Inativos", "--")
    c3.metric("Oportunidades", "--")
    st.stop()

# --- 6. PROCESSAMENTO DOS DADOS ---
df_raw = carregar_excel(uploaded_file)

if df_raw is not None:
    # Garante que ID é texto para cruzar corretamente
    if 'pj_id' in df_raw.columns:
        df_raw['pj_id'] = df_raw['pj_id'].astype(str)
    else:
        st.error("Erro Crítico: A coluna 'pj_id' não foi encontrada na planilha.")
        st.stop()

    # Carrega banco de dados do sistema (CRM)
    df_crm = carregar_crm_db()
    
    # Detecta novos clientes
    ids_no_excel = set(df_raw['pj_id'])
    ids_no_crm = set(df_crm['pj_id'])
    novos_clientes = len(ids_no_excel - ids_no_crm)

    # Junta Planilha + CRM
    df_full = pd.merge(df_raw, df_crm, on='pj_id', how='left')
    
    # Preenche valores nulos para quem nunca foi trabalhado
    df_full['status_venda'] = df_full['status_venda'].fillna('Novo')
    df_full['ja_ligou'] = df_full['ja_ligou'].fillna(False)
    df_full['obs'] = df_full['obs'].fillna('')

    # --- 7. DASHBOARD SUPERIOR ---
    st.title("🦅 Visão Geral da Carteira")
    
    if novos_clientes > 0:
        st.markdown(f"""
        <div style="background-color: rgba(227, 25, 55, 0.15); border: 1px solid #E31937; color: #E5E7EB; padding: 10px; border-radius: 5px; margin-bottom: 20px;">
            🔔 <b>Radar Elo Flow:</b> Identificamos <b>{novos_clientes}</b> novos clientes desde sua última atualização!
        </div>
        """, unsafe_allow_html=True)

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtro_cat = st.multiselect("Filtrar por Categoria", df_full['Categoria_Cliente'].unique(), default=df_full['Categoria_Cliente'].unique())
    with col_f2:
        filtro_status = st.multiselect("Filtrar por Status", df_full['status_venda'].unique(), default=df_full['status_venda'].unique())
    
    # Aplica Filtros
    df_view = df_full[
        (df_full['Categoria_Cliente'].isin(filtro_cat)) & 
        (df_full['status_venda'].isin(filtro_status))
    ]

    # Cards de KPIs
    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total na Visão", len(df_view))
    k2.metric("Vendas Fechadas", len(df_view[df_view['status_venda'] == 'Fechado']))
    k3.metric("Falta Contatar", len(df_view[df_view['ja_ligou'] == False]), delta_color="inverse")
    k4.metric("Em Negociação", len(df_view[df_view['status_venda'] == 'Em Negociação']))

    st.markdown("---")

    # Gráficos (Plotly)
    g1, g2 = st.columns(2)
    
    with g1:
        if 'estado' in df_view.columns:
            estado_counts = df_view['estado'].value_counts().reset_index()
            estado_counts.columns = ['Estado', 'Clientes']
            fig_map = px.bar(
                estado_counts.head(10), 
                x='Estado', y='Clientes', 
                title="Top 10 Estados",
                color_discrete_sequence=['#E31937']
            )
            fig_map.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_map, use_container_width=True)

    with g2:
        fig_pie = px.pie(
            df_view, 
            names='Categoria_Cliente', 
            title="Distribuição da Carteira", 
            hole=0.5,
            color_discrete_sequence=['#E31937', '#808080', '#404040']
        )
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True)

    # --- 8. LISTA DE TRABALHO (CRM) ---
    st.subheader("🎯 Lista de Ataque")
    
    # Configuração da Tabela
    col_config = {
        "pj_id": st.column_config.TextColumn("ID", disabled=True, width="small"),
        "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
        "telefone_1": st.column_config.TextColumn("Telefone", disabled=True),
        "status_venda": st.column_config.SelectboxColumn(
            "Status Flow", 
            options=['Novo', 'Tentando Contato', 'Em Negociação', 'Fechado', 'Perdido', 'Email Enviado'],
            required=True,
            width="medium"
        ),
        "ja_ligou": st.column_config.CheckboxColumn("Ligou?", width="small"),
        "obs": st.column_config.TextColumn("Diário de Bordo", width="large")
    }

    # Define colunas visíveis
    cols_visiveis = ['pj_id', 'razao_social', 'Categoria_Cliente', 'status_venda', 'ja_ligou', 'obs']
    if 'telefone_1' in df_view.columns: cols_visiveis.insert(2, 'telefone_1')
    if 'representante_nome' in df_view.columns: cols_visiveis.insert(3, 'representante_nome')

    # Componente de Edição
    df_editado = st.data_editor(
        df_view[cols_visiveis], 
        column_config=col_config, 
        hide_index=True, 
        use_container_width=True,
        key="editor_crm",
        height=600,
        num_rows="fixed"
    )

    # Botão de Salvar
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Salvar Alterações e Atualizar Base", type="primary"):
        salvar_alteracoes(df_editado, df_crm)
        st.toast("Base atualizada com sucesso! O Elo Flow registrou suas ações.", icon="✅")
        
        # Delay para reload
        import time
        time.sleep(1.5)
        st.rerun()
