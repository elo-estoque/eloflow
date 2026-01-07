import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, date
import os
import io
import urllib.parse
import textwrap

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Elo Flow - Prospecção", layout="wide", page_icon="🦅")

# --- CSS VISUAL ---
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
    
    /* Estilo dos Cards */
    .foco-card {
        background-color: #151515 !important;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #333;
        border-left: 6px solid #E31937;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    /* Botões de Ação de Email */
    .email-btn {
        display: inline-block;
        text-decoration: none;
        color: white !important;
        padding: 8px 16px;
        border-radius: 6px;
        margin-right: 8px;
        margin-bottom: 8px;
        font-weight: 600;
        font-size: 0.85rem;
        text-align: center;
        transition: all 0.3s ease;
    }
    .btn-t1 { background-color: #2563EB; border: 1px solid #1D4ED8; } /* Azul */
    .btn-t2 { background-color: #D97706; border: 1px solid #B45309; } /* Laranja */
    .btn-t3 { background-color: #DC2626; border: 1px solid #B91C1C; } /* Vermelho */
    .btn-manutencao { background-color: #059669; border: 1px solid #047857; } /* Verde */
    .email-btn:hover { opacity: 0.9; transform: translateY(-1px); }

</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES DE SCRIPT DE VENDAS ---

def gerar_link_mailto(email_destinatario, assunto, corpo):
    """Gera um link mailto seguro e codificado."""
    if not email_destinatario or str(email_destinatario).lower() in ['nan', 'none', '']:
        return None
    
    params = {
        "subject": assunto,
        "body": corpo
    }
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{email_destinatario}?{query_string}"

def obter_scripts_por_perfil(row, status_grupo):
    """
    Retorna um dicionário com scripts baseados no perfil do cliente.
    Usa dados da linha (row) para personalizar (Nome, Empresa, etc).
    """
    # Tratamento de variáveis para não quebrar o texto
    nome_contato = str(row.get('representante_nome', 'Parceiro')).title()
    if nome_contato in ['Nan', 'None', '']: nome_contato = "Parceiro"
    
    nome_empresa = str(row.get('nome_fantasia', str(row.get('razao_social', 'Sua Empresa')))).title()
    
    area_atuacao = str(row.get('area_atuacao_nome', 'seu setor'))
    
    scripts = {}

    # --- PERFIL: INATIVOS E FRIOS (Recuperação) ---
    if status_grupo in ['INATIVOS', 'FRIOS (ANTES DE 2020)']:
        # T1: Novidade / Reaproximação
        scripts['T1'] = {
            'label': '📧 T1: Novidades (Reaproximação)',
            'assunto': f"{nome_contato}, novidades e tendências 2026",
            'corpo': f"""Olá, {nome_contato}. Tudo bem?

Estava revisando nossa carteira e vi que faz um tempo que não falamos sobre os projetos da {nome_empresa}.

Muita coisa mudou por aqui! Renovamos nosso portfólio com itens que estão em alta agora, como a Linha Térmica (Estilo Stanley) e opções Eco-Sustentáveis que muitas empresas do setor de {area_atuacao} estão pedindo.

Gostaria de te enviar nosso catálogo atualizado sem compromisso. Pode ser por aqui mesmo?

Abs,"""
        }
        
        # T2: Oportunidade / Sazonal
        scripts['T2'] = {
            'label': '📧 T2: Oportunidade (Sazonal)',
            'assunto': f"Oportunidade para {nome_empresa} - Kits e Sazonal",
            'corpo': f"""Oi, {nome_contato}.

Só para complementar meu contato anterior: estamos com uma condição especial para Guarda-chuvas personalizados e Kits de Onboarding para este trimestre.

Como a {nome_empresa} já tem cadastro conosco, consigo manter uma tabela diferenciada para reativação. 

Tem alguma demanda de brindes ou uniformes prevista para os próximos meses?

Abs,"""
        }
        
        # T3: Break-up
        scripts['T3'] = {
            'label': '📧 T3: Despedida (Break-up)',
            'assunto': f"Portfólio {nome_empresa} - Encerramento de contato",
            'corpo': f"""{nome_contato}, imagino que a correria esteja grande.

Vou pausar meu contato por hora para não lotar sua caixa de entrada. 

Deixo aqui o link do nosso portfólio caso precisem no futuro: [LINK DO SITE/CATALOGO]

Se precisar de cotação para Moleskines ou Eletrônicos, é só me chamar. Sucesso!"""
        }

    # --- PERFIL: ATIVOS (Manutenção/Cross-sell) ---
    elif status_grupo == 'ATIVOS':
        scripts['MANUTENCAO'] = {
            'label': '📧 Cross-Sell (Kit Boas-Vindas)',
            'assunto': f"Ideia para Kit Boas-vindas da {nome_empresa}",
            'corpo': f"""Oi {nome_contato}, tudo bom?

Vi que o último pedido da {nome_empresa} foi entregue certinho.

Queria te dar uma ideia rápida: muitas empresas que atendemos estão montando Kits de Boas-vindas completos (Mochila + Caderno + Garrafa). Isso aumenta muito o engajamento do colaborador novo.

Topa ver um modelo virtual com a logo da {nome_empresa} só para ver como ficaria? Sem compromisso.

Abs,"""
        }
        
        scripts['ANTECIPACAO'] = {
            'label': '📧 Antecipação (Datas)',
            'assunto': f"Planejamento de Brindes - {nome_empresa}",
            'corpo': f"""Olá {nome_contato},

Estou passando para lembrar que a produção de brindes para as próximas datas comemorativas já começou a ocupar a fábrica.

Para garantir o preço atual e a entrega no prazo para a {nome_empresa}, sugiro começarmos a desenhar os pedidos agora.

O que acha de reservarmos um estoque de Copos Térmicos ou Bolsas para vocês?

Abs,"""
        }

    # --- PERFIL: CRÍTICOS (Dados Faltantes) ---
    else: # Críticos ou Indefinido
        scripts['QUEM_E'] = {
            'label': '📧 Contato Geral (LinkedIn/Site)',
            'assunto': f"Parceria com a {nome_empresa} - Marketing/Compras",
            'corpo': f"""Olá,

Nós somos fornecedores especializados em brindes corporativos (atendemos grandes players do mercado). 

Eu precisava falar com o responsável pelo Marketing ou Compras da {nome_empresa} para atualizar um cadastro de fornecedor e apresentar nossa nova linha.

Você poderia me direcionar para a pessoa certa?

Obrigado,"""
        }

    return scripts

# --- CARREGAMENTO DE DADOS ---
@st.cache_data
def load_data():
    uploaded_files = [
        "JÉSSICA - CLIENTE - FINAL (1).xlsx - ATIVOS.csv",
        "JÉSSICA - CLIENTE - FINAL (1).xlsx - INATIVOS.csv",
        "JÉSSICA - CLIENTE - FINAL (1).xlsx - FRIOS (ANTES DE 2020).csv",
        "JÉSSICA - CLIENTE - FINAL (1).xlsx - CRITICOS.csv"
    ]
    
    dfs = []
    for file in uploaded_files:
        if os.path.exists(file):
            try:
                df_temp = pd.read_csv(file)
                # Identifica o grupo pelo nome do arquivo
                if "ATIVOS" in file:
                    df_temp['GRUPO_FINAL'] = 'ATIVOS'
                elif "INATIVOS" in file:
                    df_temp['GRUPO_FINAL'] = 'INATIVOS'
                elif "FRIOS" in file:
                    df_temp['GRUPO_FINAL'] = 'FRIOS (ANTES DE 2020)'
                elif "CRITICOS" in file:
                    df_temp['GRUPO_FINAL'] = 'CRITICOS'
                
                dfs.append(df_temp)
            except Exception as e:
                st.error(f"Erro ao ler {file}: {e}")
    
    if dfs:
        df_final = pd.concat(dfs, ignore_index=True)
        # Normalização básica
        cols_date = ['Ultima_Compra', 'DATA_EXIBICAO']
        for col in cols_date:
            if col in df_final.columns:
                df_final[col] = pd.to_datetime(df_final[col], errors='coerce', dayfirst=True)
        
        # Cria colunas de controle se não existirem
        cols_controle = ['status_venda', 'data_tentativa_1', 'gap_1_2', 'data_tentativa_2', 'gap_2_3', 'data_tentativa_3', 'obs']
        for col in cols_controle:
            if col not in df_final.columns:
                df_final[col] = None
                
        return df_final
    return pd.DataFrame()

# Inicializa Session State
if 'df_main' not in st.session_state:
    st.session_state.df_main = load_data()

df = st.session_state.df_main

# --- SIDEBAR E FILTROS ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/4149/4149665.png", width=50) # Icone ilustrativo
st.sidebar.title("Filtros")

if not df.empty:
    filtro_grupo = st.sidebar.multiselect("Carteira (Grupo)", df['GRUPO_FINAL'].unique(), default=df['GRUPO_FINAL'].unique())
    filtro_estado = st.sidebar.multiselect("Estado", df['estado'].dropna().unique())
    
    df_filtered = df[df['GRUPO_FINAL'].isin(filtro_grupo)]
    if filtro_estado:
        df_filtered = df_filtered[df_filtered['estado'].isin(filtro_estado)]
else:
    df_filtered = df

# --- INTERFACE PRINCIPAL ---

# TABS
tab1, tab2 = st.tabs(["🔥 Foco do Dia", "📋 Lista Geral / Editor"])

# --- FUNÇÃO DO DIALOG (CARD COMPLETO) ---
@st.dialog("Detalhes do Cliente")
def mostrar_detalhes(pj_id):
    # Busca o cliente atualizado no session state
    row = st.session_state.df_main[st.session_state.df_main['pj_id'] == pj_id].iloc[0]
    idx = row.name # Indice original para salvar depois
    
    st.subheader(f"{row.get('razao_social')} ({row.get('GRUPO_FINAL')})")
    
    # --- ÁREA DE SCRIPTS INTELIGENTES ---
    st.markdown("### 🚀 Ações Rápidas (Scripts)")
    email_cliente = row.get('email_1', '')
    
    if pd.isna(email_cliente) or str(email_cliente).strip() == '':
        st.warning("⚠️ Cliente sem e-mail cadastrado para disparo automático.")
    else:
        scripts_disponiveis = obter_scripts_por_perfil(row, row.get('GRUPO_FINAL'))
        
        cols_botoes = st.columns(len(scripts_disponiveis) if scripts_disponiveis else 1)
        
        for i, (key, script_data) in enumerate(scripts_disponiveis.items()):
            link = gerar_link_mailto(email_cliente, script_data['assunto'], script_data['corpo'])
            
            # Define classe CSS baseada no tipo
            css_class = "btn-t1"
            if "T2" in key: css_class = "btn-t2"
            if "T3" in key: css_class = "btn-t3"
            if "MANUTENCAO" in key: css_class = "btn-manutencao"
            
            if link:
                with cols_botoes[i]:
                    st.markdown(f"""
                        <a href="{link}" target="_blank" class="email-btn {css_class}">
                           {script_data['label']}
                        </a>
                    """, unsafe_allow_html=True)
    
    st.divider()

    # --- FORMULÁRIO DE EDIÇÃO ---
    with st.form("form_detalhes"):
        c1, c2 = st.columns(2)
        
        # Dados de Contato
        with c1:
            st.markdown("#### Contato")
            novo_rep = st.text_input("Representante", value=row.get('representante_nome', ''))
            novo_tel = st.text_input("Telefone", value=row.get('telefone_1', ''))
            novo_email = st.text_input("Email", value=row.get('email_1', ''))
        
        # Dados de Venda (Funil)
        with c2:
            st.markdown("#### Funil de Vendas")
            status_opts = ["Sem Contato", "Em Negociação", "Vendido", "Perdido", "Retomar Futuro"]
            
            # Tenta achar o index atual, se não default 0
            curr_status = row.get('status_venda')
            idx_status = status_opts.index(curr_status) if curr_status in status_opts else 0
            
            novo_status = st.selectbox("Status", status_opts, index=idx_status)
            nova_obs = st.text_area("Observações", value=row.get('obs', ''), height=100, placeholder="Ex: Cliente gostou do Copo Stanley...")

        st.markdown("#### Cadência")
        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
        
        # Lógica simples de datas
        def fmt_date(d): return pd.to_datetime(d).date() if pd.notnull(d) and d != '' else None
        
        d_t1 = cc1.date_input("Tentativa 1", value=fmt_date(row.get('data_tentativa_1')))
        gap_1 = cc2.text_input("Gap (dias)", value=row.get('gap_1_2', ''))
        d_t2 = cc3.date_input("Tentativa 2", value=fmt_date(row.get('data_tentativa_2')))
        gap_2 = cc4.text_input("Gap (dias)", value=row.get('gap_2_3', ''))
        d_t3 = cc5.date_input("Tentativa 3", value=fmt_date(row.get('data_tentativa_3')))

        if st.form_submit_button("💾 Salvar Alterações"):
            # Atualiza Session State
            st.session_state.df_main.at[idx, 'representante_nome'] = novo_rep
            st.session_state.df_main.at[idx, 'telefone_1'] = novo_tel
            st.session_state.df_main.at[idx, 'email_1'] = novo_email
            st.session_state.df_main.at[idx, 'status_venda'] = novo_status
            st.session_state.df_main.at[idx, 'obs'] = nova_obs
            
            st.session_state.df_main.at[idx, 'data_tentativa_1'] = d_t1
            st.session_state.df_main.at[idx, 'gap_1_2'] = gap_1
            st.session_state.df_main.at[idx, 'data_tentativa_2'] = d_t2
            st.session_state.df_main.at[idx, 'gap_2_3'] = gap_2
            st.session_state.df_main.at[idx, 'data_tentativa_3'] = d_t3
            
            st.success("Cliente atualizado!")
            st.rerun()

# --- ABA 1: FOCO DO DIA ---
with tab1:
    st.title("🔥 Foco do Dia")
    st.markdown("Clientes prioritários para atacar hoje.")
    
    # Exemplo simples de logica de foco (Pega os primeiros 5 de cada grupo filtrado)
    if not df_filtered.empty:
        # Mostra cards
        for index, row in df_filtered.head(10).iterrows():
            with st.container():
                st.markdown(f"""
                <div class="foco-card">
                    <h3>{row.get('razao_social')}</h3>
                    <p><b>Grupo:</b> {row.get('GRUPO_FINAL')} | <b>Setor:</b> {row.get('area_atuacao_nome')}</p>
                    <p><i>Última Interação: {row.get('Ultima_Compra', '-')}</i></p>
                </div>
                """, unsafe_allow_html=True)
                
                c_btn, c_info = st.columns([1, 4])
                if c_btn.button("Ver Detalhes / Script", key=f"btn_{row['pj_id']}"):
                    mostrar_detalhes(row['pj_id'])
    else:
        st.info("Nenhum cliente encontrado com os filtros atuais.")

# --- ABA 2: LISTA GERAL (EDITOR) ---
with tab2:
    st.title("📋 Visão Geral da Carteira")
    
    # Configuração das colunas para edição rápida
    col_config = {
        "pj_id": st.column_config.NumberColumn("ID", disabled=True),
        "razao_social": st.column_config.TextColumn("Empresa", disabled=True),
        "status_venda": st.column_config.SelectboxColumn(
            "Status Venda",
            options=["Sem Contato", "Em Negociação", "Vendido", "Perdido", "Retomar Futuro"],
            required=True
        ),
        "gap_1_2": st.column_config.TextColumn("Gap 1-2", help="Digite manualmente"),
        "gap_2_3": st.column_config.TextColumn("Gap 2-3", help="Digite manualmente")
    }

    cols_display = [
        'pj_id', 'razao_social', 'cnpj', 'status_venda', 
        'data_tentativa_1', 'gap_1_2', 
        'data_tentativa_2', 'gap_2_3', 
        'data_tentativa_3',
        'obs', 'telefone_1', 'Ultima_Compra', 'email_1', 'area_atuacao_nome'
    ]
    
    df_view = df_filtered.copy()

    # CORREÇÃO CRÍTICA: Força colunas de texto para serem string antes do editor
    cols_text_force = ['gap_1_2', 'gap_2_3', 'telefone_1', 'email_1']
    for col in cols_text_force:
        if col in df_view.columns:
            df_view[col] = df_view[col].astype(str).replace('nan', '')
            df_view[col] = df_view[col].replace('None', '')

    df_edit = st.data_editor(
        df_view[cols_display], 
        column_config=col_config, 
        hide_index=True, 
        use_container_width=True, 
        key="editor_crm", 
        height=500
    )

    # --- RODAPÉ DE AÇÃO ---
    c_save, c_down = st.columns(2)
    if c_save.button("Salvar Todas Alterações da Grade"):
        # Atualiza o dataframe principal com as edições da grade
        # (Lógica simplificada - num app real ideal merging por ID)
        st.session_state.df_main.update(df_edit)
        st.success("Base de dados atualizada na memória!")
    
    # Exportar CSV
    csv_buffer = df_edit.to_csv(index=False).encode('utf-8')
    c_down.download_button(
        label="📥 Baixar Planilha Atualizada",
        data=csv_buffer,
        file_name="crm_atualizado.csv",
        mime="text/csv"
    )
