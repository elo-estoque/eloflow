import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import os
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Elo Flow - Prospecção", layout="wide", page_icon="🦅")

# --- CSS VISUAL (DARK MODE & ESTILOS) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    :root {
        --brand-dark: #050505; --brand-card: #121212; --brand-wine: #E31937;
        --text-main: #E5E7EB; --text-muted: #9CA3AF; --border-color: rgba(255, 255, 255, 0.1);
    }
    .stApp { background-color: var(--brand-dark); color: var(--text-main); font-family: 'Inter', sans-serif; }
    
    /* Sidebar e Cards */
    section[data-testid="stSidebar"] { background-color: var(--brand-card); border-right: 1px solid var(--border-color); }
    div[data-testid="stMetric"] { background-color: var(--brand-card); border: 1px solid var(--border-color); padding: 10px; border-radius: 8px; }
    div[data-testid="stMetricLabel"] { color: var(--text-muted); }
    div[data-testid="stMetricValue"] { color: var(--brand-wine); font-weight: 700; }
    
    /* Botões */
    div.stButton > button { background-color: var(--brand-wine); color: white; border: none; width: 100%; border-radius: 6px; }
    div.stButton > button:hover { background-color: #C2132F; color: white; border-color: #C2132F; }
    
    /* Destaque Data da Última Compra na Tabela */
    div[data-testid="stDataEditor"] div[role="gridcell"][data-testid*="Ultima_Compra"] {
        color: #E31937; font-weight: bold;
    }
    
    /* Estilo do Card de Modo Foco */
    .foco-card {
        background-color: #1A1A1A;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #E31937;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

pio.templates.default = "plotly_dark"

# --- PERSISTÊNCIA (BANCO DE DADOS LOCAL) ---
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
    
    # Remove duplicatas antigas para atualizar com novos dados
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
    """Remove caracteres não numéricos para link do WhatsApp"""
    if pd.isna(phone): return None
    return "".join(filter(str.isdigit, str(phone)))

# --- SIDEBAR ---
st.sidebar.markdown(f"<h2 style='color: #E31937; text-align: center;'>🦅 ELO FLOW</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader("📂 Importar Tabela (.xlsx)", type=["xlsx"])

# --- LEITURA E PROCESSAMENTO ---
@st.cache_data
def carregar_excel(file):
    try:
        xls = pd.ExcelFile(file)
        dfs = []
        for sheet_name in xls.sheet_names:
            name_upper = sheet_name.upper()
            
            # --- LÓGICA DE CATEGORIA ---
            if "INATIVO" in name_upper: categoria = "Inativos (Recuperação)"
            elif "FRIO" in name_upper: categoria = "Frios (Antigos)"
            elif "ATIVO" in name_upper: categoria = "Ativos (Carteira)"
            else: continue # Ignora abas que não sejam clientes
            
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df['Categoria_Cliente'] = categoria
            
            # Tratamento da Data
            if 'DATA_EXIBICAO' in df.columns:
                df['data_temp'] = pd.to_datetime(df['DATA_EXIBICAO'], errors='coerce', dayfirst=True)
                df['Ultima_Compra'] = df['data_temp'].dt.strftime('%d/%m/%Y').fillna("-")
                
                # Cálculo de Dias sem Compra (Recência)
                hoje = pd.Timestamp.now()
                df['dias_sem_compra'] = (hoje - df['data_temp']).dt.days.fillna(9999).astype(int)
            else:
                df['Ultima_Compra'] = "-"
                df['dias_sem_compra'] = 9999 # Valor alto para quem não tem data
            
            # Tratamento de Área e Telefone
            cols_check = {'area_atuacao_nome': 'Indefinido', 'telefone_1': '', 'email_1': ''}
            for col, val in cols_check.items():
                if col not in df.columns:
                    df[col] = val
                else:
                    df[col] = df[col].fillna(val)

            dfs.append(df)
            
        if not dfs: return None
        return pd.concat(dfs, ignore_index=True)
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        return None

if not uploaded_file:
    st.info("👆 Importe o arquivo XLSX na barra lateral para começar.")
    st.stop()

df_raw = carregar_excel(uploaded_file)

if df_raw is None or df_raw.empty:
    st.error("Nenhum dado encontrado.")
    st.stop()

# Garantir ID como string
if 'pj_id' in df_raw.columns:
    df_raw['pj_id'] = df_raw['pj_id'].astype(str)
else:
    st.error("Erro: Coluna 'pj_id' obrigatória.")
    st.stop()

# Tratamento CNPJ
if 'cnpj' in df_raw.columns:
    df_raw['cnpj'] = df_raw['cnpj'].astype(str).str.replace(r'\.0$', '', regex=True)
else:
    df_raw['cnpj'] = "-"

# Merge com CRM (Dados persistentes)
df_crm = carregar_crm_db()
df_full = pd.merge(df_raw, df_crm, on='pj_id', how='left')

# Preenche vazios do CRM
df_full['status_venda'] = df_full['status_venda'].fillna('Não contatado')
df_full['ja_ligou'] = df_full['ja_ligou'].fillna(False)
df_full['obs'] = df_full['obs'].fillna('')

# --- DASHBOARD DE GESTÃO ---
st.title("🦅 Visão Geral - Carteira")

# Filtros
c1, c2, c3 = st.columns(3)
cat = c1.multiselect("Categoria", df_full['Categoria_Cliente'].unique(), default=df_full['Categoria_Cliente'].unique())
sts = c2.multiselect("Status", df_full['status_venda'].unique(), default=df_full['status_venda'].unique())
area = c3.multiselect("Área", df_full['area_atuacao_nome'].unique(), default=df_full['area_atuacao_nome'].unique())

# Aplicar Filtros
df_view = df_full[
    (df_full['Categoria_Cliente'].isin(cat)) & 
    (df_full['status_venda'].isin(sts)) &
    (df_full['area_atuacao_nome'].isin(area))
].copy()

# Ordenar por Recência (Os que compraram mais recentemente primeiro, ou Inversamente)
if 'dias_sem_compra' in df_view.columns:
    df_view = df_view.sort_values(by='dias_sem_compra', ascending=True)

# KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Visível", len(df_view))
k2.metric("Oportunidades (Inativos)", len(df_view[df_view['Categoria_Cliente'].str.contains('Inativo')]))
k3.metric("Pendentes de Contato", len(df_view[df_view['status_venda'] == 'Não contatado']))
k4.metric("Em Negociação", len(df_view[df_view['status_venda'] == 'Em Negociação']))

st.divider()

# --- MODO DE ATAQUE (NOVA FUNCIONALIDADE) ---
st.markdown("### 🚀 Modo de Ataque (Foco)")

col_sel, col_detalhe = st.columns([1, 2])

with col_sel:
    st.markdown("**1. Selecione o Alvo:**")
    # Cria uma lista formatada para o selectbox
    df_view['label_select'] = df_view['razao_social'] + " (" + df_view['Ultima_Compra'] + ")"
    
    opcoes_ataque = df_view['label_select'].tolist()
    selecionado = st.selectbox("Busque por Razão Social:", ["Selecione..."] + opcoes_ataque)

if selecionado and selecionado != "Selecione...":
    # Recupera dados do cliente selecionado
    cliente = df_view[df_view['label_select'] == selecionado].iloc[0]
    
    # Preparação para Script
    dias = cliente['dias_sem_compra'] if cliente['dias_sem_compra'] < 9000 else "Muitos"
    area_cli = cliente['area_atuacao_nome']
    tel_raw = str(cliente['telefone_1'])
    tel_clean = limpar_telefone(tel_raw)
    
    # Lógica de Script Dinâmico
    if dias != "Muitos" and dias > 30:
        script_msg = f"Olá! Tudo bem? Sou da Elo. Vi que sua última compra foi há {dias} dias. Temos condições especiais para retomada."
    elif "Novo" in cliente['status_venda']:
        script_msg = f"Olá! Vi que vocês atuam com {area_cli} e gostaria de apresentar a Elo."
    else:
        script_msg = f"Olá! Gostaria de falar sobre oportunidades para a área de {area_cli}."

    with col_detalhe:
        st.markdown(f"""
        <div class="foco-card">
            <h3>🏢 {cliente['razao_social']}</h3>
            <p><b>CNPJ:</b> {cliente['cnpj']} | <b>Status Atual:</b> {cliente['status_venda']}</p>
            <p><b>📅 Última Compra:</b> {cliente['Ultima_Compra']} <span style="color:#E31937">({dias} dias atrás)</span></p>
            <hr style="border-color: #333;">
            <p>📝 <b>Script Sugerido:</b> <i>"{script_msg}"</i></p>
        </div>
        """, unsafe_allow_html=True)
        
        b1, b2 = st.columns(2)
        with b1:
            if tel_clean and len(tel_clean) >= 10:
                link_wpp = f"https://wa.me/55{tel_clean}?text={script_msg.replace(' ', '%20')}"
                st.link_button(f"💬 Abrir WhatsApp ({tel_raw})", link_wpp, type="primary", use_container_width=True)
            else:
                st.warning(f"Telefone inválido: {tel_raw}")
        with b2:
            st.link_button("📧 Enviar E-mail", f"mailto:{cliente['email_1']}?subject=Oportunidade Elo&body={script_msg}", use_container_width=True)

st.divider()

# --- TABELA DE TRABALHO ---
st.subheader("📋 Lista de Prospecção")

col_config = {
    "pj_id": st.column_config.TextColumn("ID", disabled=True),
    "razao_social": st.column_config.TextColumn("Razão Social", disabled=True),
    "cnpj": st.column_config.TextColumn("CNPJ", disabled=True),
    "Ultima_Compra": st.column_config.TextColumn("Última Compra", disabled=True),
    "dias_sem_compra": st.column_config.NumberColumn("Dias Inativo", format="%d dias"),
    "telefone_1": st.column_config.TextColumn("Telefone", disabled=True),
    "status_venda": st.column_config.SelectboxColumn(
        "Status", 
        options=['Não contatado', 'Tentando Contato', 'Em Negociação', 'Fechado', 'Perdido', 'Novo'], 
        required=True
    ),
    "ja_ligou": st.column_config.CheckboxColumn("Já Ligou?"),
    "obs": st.column_config.TextColumn("Observações", width="large")
}

cols_display = ['pj_id', 'razao_social', 'Ultima_Compra', 'dias_sem_compra', 'telefone_1', 'status_venda', 'ja_ligou', 'obs']

df_edit = st.data_editor(
    df_view[cols_display], 
    column_config=col_config, 
    hide_index=True, 
    use_container_width=True, 
    key="editor_crm", 
    height=500
)

# --- RODAPÉ: SALVAR E EXPORTAR ---
c_save, c_export, c_void = st.columns([1, 1, 2])

with c_save:
    if st.button("💾 Salvar Tudo", type="primary"):
        salvar_alteracoes(df_edit, df_crm)
        st.toast("Dados salvos com sucesso!", icon="✅")
        import time
        time.sleep(1)
        st.rerun()

with c_export:
    excel_data = converter_para_excel(df_edit)
    st.download_button(
        "📥 Baixar Planilha", 
        data=excel_data, 
        file_name="EloFlow_Prospeccao.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- GRÁFICOS INFERIORES ---
st.markdown("---")
g1, g2 = st.columns(2)
with g1:
    fig = px.pie(df_view, names='Categoria_Cliente', title="Distribuição da Carteira Filtrada", hole=0.6, color_discrete_sequence=['#E31937', '#666', '#333'])
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

with g2:
    if not df_view.empty:
        fig2 = px.histogram(df_view, x='status_venda', title="Funil de Vendas (Status)", color_discrete_sequence=['#E31937'])
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
