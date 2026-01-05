import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import os
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Elo Flow", layout="wide", page_icon="🦅")

# --- CSS VISUAL ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    :root {
        --brand-dark: #050505; --brand-card: #121212; --brand-wine: #E31937;
        --text-main: #E5E7EB; --text-muted: #9CA3AF; --border-color: rgba(255, 255, 255, 0.1);
    }
    .stApp { background-color: var(--brand-dark); color: var(--text-main); font-family: 'Inter', sans-serif; }
    section[data-testid="stSidebar"] { background-color: var(--brand-card); border-right: 1px solid var(--border-color); }
    div[data-testid="stMetric"] { background-color: var(--brand-card); border: 1px solid var(--border-color); }
    div[data-testid="stMetricLabel"] { color: var(--text-muted); }
    div[data-testid="stMetricValue"] { color: var(--brand-wine); font-weight: 700; }
    div.stButton > button { background-color: var(--brand-wine); color: white; border: none; width: 100%; }
    div.stButton > button:hover { background-color: #C2132F; color: white; }
    h1, h2, h3 { color: var(--text-main) !important; }
    
    /* Destaque Data da Última Compra */
    div[data-testid="stDataEditor"] div[role="gridcell"][data-testid*="Ultima_Compra"] {
        color: #E31937; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

pio.templates.default = "plotly_dark"

# --- PERSISTÊNCIA ---
DB_FILE = "/app/data/db_elo_flow.csv"

def carregar_crm_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE, dtype={'pj_id': str})
    else:
        return pd.DataFrame(columns=['pj_id', 'status_venda', 'ja_ligou', 'obs', 'data_interacao'])

def salvar_alteracoes(df_editor, df_original_crm):
    novos_dados = df_editor[['pj_id', 'status_venda', 'ja_ligou', 'obs']].copy()
    novos_dados['data_interacao'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    crm_atualizado = df_original_crm[~df_original_crm['pj_id'].isin(novos_dados['pj_id'])]
    crm_final = pd.concat([crm_atualizado, novos_dados], ignore_index=True)
    crm_final.to_csv(DB_FILE, index=False)
    return crm_final

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='EloFlow_Dados')
    return output.getvalue()

# --- SIDEBAR ---
st.sidebar.markdown(f"<h2 style='color: #E31937; text-align: center;'>ELO FLOW</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader("📂 Importar Tabela (.xlsx)", type=["xlsx"])

# --- LEITURA INTELIGENTE DAS ABAS ---
@st.cache_data
def carregar_excel(file):
    try:
        xls = pd.ExcelFile(file)
        dfs = []
        for sheet_name in xls.sheet_names:
            name_upper = sheet_name.upper()
            
            # --- CORREÇÃO DA LÓGICA AQUI ---
            # Primeiro verificamos INATIVO, depois FRIO, depois ATIVO.
            # Se verificar ATIVO primeiro, ele pega o "ATIVO" de dentro da palavra "INATIVO".
            
            if "INATIVO" in name_upper: 
                categoria = "Inativos (2020-2024)"
            elif "FRIO" in name_upper: 
                categoria = "Frios (<2020)"
            elif "ATIVO" in name_upper: 
                categoria = "Ativos (2025)"
            else:
                categoria = "Outros" # Caso tenha alguma aba de config ou resumo
                continue # Pula abas que não sejam de dados de clientes
            
            # Lê a aba
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df['Categoria_Cliente'] = categoria
            
            # Tratamento da Data (DATA_EXIBICAO)
            if 'DATA_EXIBICAO' in df.columns:
                df['data_temp'] = pd.to_datetime(df['DATA_EXIBICAO'], errors='coerce', dayfirst=True)
                df['Ultima_Compra'] = df['data_temp'].dt.strftime('%d/%m/%Y').fillna("-")
            else:
                df['Ultima_Compra'] = "-"
                
            dfs.append(df)
            
        if not dfs:
            return None
            
        return pd.concat(dfs, ignore_index=True)
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        return None

if not uploaded_file:
    st.info("👆 Importe o arquivo XLSX para começar.")
    st.stop()

# --- PROCESSAMENTO ---
df_raw = carregar_excel(uploaded_file)

if df_raw is None or df_raw.empty:
    st.error("Nenhum dado encontrado nas abas ATIVOS, INATIVOS ou FRIOS.")
    st.stop()

if 'pj_id' in df_raw.columns:
    df_raw['pj_id'] = df_raw['pj_id'].astype(str)
else:
    st.error("Erro: Coluna 'pj_id' não encontrada.")
    st.stop()

df_crm = carregar_crm_db()
df_full = pd.merge(df_raw, df_crm, on='pj_id', how='left')
df_full['status_venda'] = df_full['status_venda'].fillna('Novo')
df_full['ja_ligou'] = df_full['ja_ligou'].fillna(False)
df_full['obs'] = df_full['obs'].fillna('')

# --- DASHBOARD ---
st.title("🦅 Visão Geral - 3 Categorias")

# Filtros
c1, c2 = st.columns(2)
cat = c1.multiselect("Categoria", df_full['Categoria_Cliente'].unique(), default=df_full['Categoria_Cliente'].unique())
sts = c2.multiselect("Status", df_full['status_venda'].unique(), default=df_full['status_venda'].unique())

df_view = df_full[(df_full['Categoria_Cliente'].isin(cat)) & (df_full['status_venda'].isin(sts))]

# Ordenação por data se existir (Recentes primeiro)
if 'data_temp' in df_view.columns:
    df_view = df_view.sort_values(by='data_temp', ascending=False)

# KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total na Lista", len(df_view))
k2.metric("Inativos/Frios", len(df_view[df_view['Categoria_Cliente'].str.contains('Inativo|Frio')]))
k3.metric("Falta Contatar", len(df_view[df_view['ja_ligou'] == False]))
k4.metric("Em Negociação", len(df_view[df_view['status_venda'] == 'Em Negociação']))

st.markdown("---")

# Gráficos
g1, g2 = st.columns(2)
with g1:
    fig = px.pie(df_view, names='Categoria_Cliente', title="Distribuição da Carteira", hole=0.5, color_discrete_sequence=['#E31937', '#999', '#333'])
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

with g2:
    if 'estado' in df_view.columns:
        fig2 = px.bar(df_view['estado'].value_counts().reset_index(), x='estado', y='count', title="Por Estado", color_discrete_sequence=['#E31937'])
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

# --- TABELA DE TRABALHO ---
st.subheader("🎯 Lista de Ataque (Ativos + Inativos + Frios)")

col_config = {
    "pj_id": st.column_config.TextColumn("ID", disabled=True),
    "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
    "Ultima_Compra": st.column_config.TextColumn("Última Compra", disabled=True),
    "status_venda": st.column_config.SelectboxColumn("Status", options=['Novo', 'Tentando Contato', 'Em Negociação', 'Fechado', 'Perdido'], required=True),
    "ja_ligou": st.column_config.CheckboxColumn("Ligou?"),
    "obs": st.column_config.TextColumn("Obs", width="large")
}

cols = ['pj_id', 'razao_social', 'Ultima_Compra', 'Categoria_Cliente', 'status_venda', 'ja_ligou', 'obs']
if 'telefone_1' in df_view.columns: cols.insert(3, 'telefone_1')

df_edit = st.data_editor(
    df_view[cols], 
    column_config=col_config, 
    hide_index=True, 
    use_container_width=True, 
    key="crm", 
    height=600
)

# Botões Finais
c_save, c_export = st.columns([1, 1])
with c_save:
    if st.button("💾 Salvar Alterações", type="primary"):
        salvar_alteracoes(df_edit, df_crm)
        st.toast("Salvo!", icon="✅")
        import time
        time.sleep(1)
        st.rerun()

with c_export:
    excel_data = converter_para_excel(df_edit)
    st.download_button("📥 Baixar Relatório (.xlsx)", data=excel_data, file_name="EloFlow.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
