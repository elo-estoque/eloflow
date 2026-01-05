import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import os
import io

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Elo Flow", layout="wide", page_icon="🦅")

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
</style>
""", unsafe_allow_html=True)

pio.templates.default = "plotly_dark"

# --- BANCO DE DADOS INTERNO ---
# Usamos CSV interno apenas para velocidade do sistema salvar rápido, 
# mas o usuário só vê e interage com EXCEL.
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

# --- SIDEBAR (UPLOAD XLSX) ---
st.sidebar.markdown(f"<h2 style='color: #E31937; text-align: center;'>ELO FLOW</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")
# AQUI: Aceita apenas XLSX
uploaded_file = st.sidebar.file_uploader("📂 Importar Tabela (.xlsx)", type=["xlsx"])

# --- LEITURA DO EXCEL (ABAS) ---
@st.cache_data
def carregar_excel(file):
    try:
        # Lê o arquivo Excel carregado na memória
        xls = pd.ExcelFile(file)
        dfs = []
        # Percorre todas as abas procurando as palavras chaves
        for sheet_name in xls.sheet_names:
            name_upper = sheet_name.upper()
            categoria = "Outros"
            
            if "ATIVO" in name_upper: categoria = "Ativos (2025)"
            elif "INATIVO" in name_upper: categoria = "Inativos (2020-2024)"
            elif "FRIO" in name_upper: categoria = "Frios (<2020)"
            
            # Lê a aba específica
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df['Categoria_Cliente'] = categoria
            dfs.append(df)
            
        return pd.concat(dfs, ignore_index=True)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo Excel: {e}")
        return None

if not uploaded_file:
    st.info("👆 Por favor, solte o arquivo EXCEL (.xlsx) na barra lateral.")
    st.stop()

# --- PROCESSAMENTO ---
df_raw = carregar_excel(uploaded_file)

if df_raw is not None:
    # Garante ID como texto
    if 'pj_id' in df_raw.columns:
        df_raw['pj_id'] = df_raw['pj_id'].astype(str)
    else:
        st.error("Erro: A coluna 'pj_id' não foi encontrada na sua planilha.")
        st.stop()

    df_crm = carregar_crm_db()
    
    # Cruzamento de dados
    df_full = pd.merge(df_raw, df_crm, on='pj_id', how='left')
    df_full['status_venda'] = df_full['status_venda'].fillna('Novo')
    df_full['ja_ligou'] = df_full['ja_ligou'].fillna(False)
    df_full['obs'] = df_full['obs'].fillna('')

    # --- DASHBOARD ---
    st.title("🦅 Visão Geral")
    
    # Filtros
    c1, c2 = st.columns(2)
    cat = c1.multiselect("Categoria", df_full['Categoria_Cliente'].unique(), default=df_full['Categoria_Cliente'].unique())
    sts = c2.multiselect("Status", df_full['status_venda'].unique(), default=df_full['status_venda'].unique())
    
    df_view = df_full[(df_full['Categoria_Cliente'].isin(cat)) & (df_full['status_venda'].isin(sts))]

    # Métricas
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total", len(df_view))
    k2.metric("Fechados", len(df_view[df_view['status_venda'] == 'Fechado']))
    k3.metric("Falta Contatar", len(df_view[df_view['ja_ligou'] == False]))
    k4.metric("Negociando", len(df_view[df_view['status_venda'] == 'Em Negociação']))

    st.markdown("---")

    # Gráficos
    g1, g2 = st.columns(2)
    with g1:
        if 'estado' in df_view.columns:
            fig = px.bar(df_view['estado'].value_counts().reset_index(), x='estado', y='count', title="Estados", color_discrete_sequence=['#E31937'])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig2 = px.pie(df_view, names='Categoria_Cliente', title="Distribuição", hole=0.5, color_discrete_sequence=['#E31937', '#666', '#333'])
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

    # --- CRM (TABELA) ---
    st.subheader("🎯 Lista de Trabalho")
    
    conf = {
        "pj_id": st.column_config.TextColumn("ID", disabled=True),
        "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
        "status_venda": st.column_config.SelectboxColumn("Status", options=['Novo', 'Tentando Contato', 'Em Negociação', 'Fechado', 'Perdido'], required=True),
        "ja_ligou": st.column_config.CheckboxColumn("Ligou?"),
        "obs": st.column_config.TextColumn("Obs", width="large")
    }
    
    cols = ['pj_id', 'razao_social', 'Categoria_Cliente', 'status_venda', 'ja_ligou', 'obs']
    # Adiciona telefone se existir na planilha
    if 'telefone_1' in df_view.columns: cols.insert(2, 'telefone_1')
    
    df_edit = st.data_editor(
        df_view[cols], 
        column_config=conf, 
        hide_index=True, 
        use_container_width=True, 
        key="crm", 
        height=500
    )

    c_save, c_export = st.columns([1, 1])
    
    with c_save:
        if st.button("💾 Salvar Alterações", type="primary"):
            salvar_alteracoes(df_edit, df_crm)
            st.toast("Dados salvos no sistema!", icon="✅")
            import time
            time.sleep(1)
            st.rerun()
            
    with c_export:
        # Botão para baixar tudo em EXCEL
        excel_data = converter_para_excel(df_edit)
        st.download_button(
            label="📥 Baixar Tabela Atualizada (.xlsx)",
            data=excel_data,
            file_name=f"EloFlow_Export_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
