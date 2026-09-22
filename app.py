import io
import os
import sqlite3
import pandas as pd
import qrcode
import streamlit as st
import streamlit.components.v1 as components

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Conferência de volumes Gaja", page_icon="📦", layout="wide"
)

ARQUIVO_EXCEL = "Programa conferencia.xlsx"
BANCO_DADOS = "conferencia.db"

# Estado da navegação
if "aba_atual" not in st.session_state:
    st.session_state["aba_atual"] = "Leitura"

# ==========================================
# ESTILOS COMPACTOS
# ==========================================
st.markdown(
    """
    <style>
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    .titulo-rodape {
        font-size: 13px !important;
        font-weight: bold;
        color: #1b5e20 !important;
        margin-top: 10px !important;
        margin-bottom: 10px !important;
        text-align: center;
        border-top: 1px solid #e0e0e0;
        padding-top: 6px;
    }
    
    div[data-baseweb="input"] {
        border: 2px solid #0066cc !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] input {
        font-size: 18px !important;
        font-weight: bold !important;
        padding: 8px 10px !important;
    }
    label[data-testid="stWidgetLabel"] {
        font-size: 15px !important;
        font-weight: bold !important;
        margin-bottom: 2px !important;
    }
    
    .txt-produto-encontrado {
        font-size: 13px !important;
        color: #2e7d32;
        font-weight: bold;
        margin-top: 2px !important;
    }
    .txt-codigo-produto {
        font-size: 14px !important;
        font-weight: bold;
        color: #0066cc;
        margin-top: 4px !important;
        margin-bottom: 4px !important;
    }
    
    div[data-testid="stMetric"] { padding: 0px !important; }
    div[data-testid="stMetricValue"] {
        font-size: 24px !important;
        color: #1b5e20 !important;
        font-weight: bold !important;
    }
    div[data-testid="stMetricLabel"] { font-size: 13px !important; }
    .stButton button {
        padding: 8px 12px !important;
        font-size: 15px !important;
        font-weight: bold !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# FUNÇÕES AUXILIARES E BASE DE DADOS
# ==========================================
def gerar_qrcode(url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def conectar_bd():
    return sqlite3.connect(BANCO_DADOS)


def inicializar_banco():
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conferencia (
            cod_barras TEXT PRIMARY KEY,
            cod_produto TEXT,
            volumes_totais INTEGER,
            volumes_conferidos INTEGER
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM conferencia")
    if cursor.fetchone()[0] == 0:
        if not os.path.exists(ARQUIVO_EXCEL):
            st.error(f"Arquivo '{ARQUIVO_EXCEL}' não encontrado!")
            st.stop()

        df = pd.read_excel(ARQUIVO_EXCEL)
        df.columns = df.columns.str.strip()
        df["Cod de barras XML"] = (
            df["Cod de barras XML"]
            .astype(str)
            .str.replace(".0", "", regex=False)
            .str.strip()
        )
        df["Volumes"] = (
            pd.to_numeric(df["Volumes"], errors="coerce").fillna(0).astype(int)
        )

        for _, row in df.iterrows():
            cursor.execute(
                """
                INSERT OR REPLACE INTO conferencia 
                (cod_barras, cod_produto, volumes_totais, volumes_conferidos)
                VALUES (?, ?, ?, 0)
            """,
                (
                    row["Cod de barras XML"],
                    str(row["Código do Produto"]),
                    row["Volumes"],
                ),
            )
        conn.commit()
    conn.close()


def buscar_produto(cod_barras):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cod_produto, volumes_totais, volumes_conferidos FROM conferencia WHERE cod_barras = ?",
        (cod_barras,),
    )
    resultado = cursor.fetchone()
    conn.close()
    return resultado


def registrar_novo_produto_avulso(cod_barras):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO conferencia (cod_barras, cod_produto, volumes_totais, volumes_conferidos)
        VALUES (?, ?, 1, 1)
    """,
        (cod_barras, f"AVULSO-{cod_barras}"),
    )
    conn.commit()
    conn.close()


def baixar_volume(cod_barras):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conferencia 
        SET volumes_conferidos = volumes_conferidos + 1 
        WHERE cod_barras = ? AND volumes_conferidos < volumes_totais
    """,
        (cod_barras,),
    )
    conn.commit()
    conn.close()


def obter_todos_produtos():
    conn = conectar_bd()
    df = pd.read_sql_query(
        """
        SELECT 
            cod_barras AS [Código de Barras],
            cod_produto AS [Código do Produto],
            volumes_conferidos || '/' || volumes_totais AS [Progresso (Conferido/Total)],
            CASE 
                WHEN volumes_conferidos = 0 THEN '🔴 Não iniciado'
                WHEN volumes_conferidos < volumes_totais THEN '🟡 Em andamento'
                ELSE '🟢 Concluído'
            END AS [Status],
            volumes_conferidos,
            volumes_totais
        FROM conferencia
    """,
        conn,
    )
    conn.close()
    return df


def resetar_conferencia():
    if os.path.exists(BANCO_DADOS):
        os.remove(BANCO_DADOS)


def limpar_dados():
    st.session_state["codigo_input"] = ""
    st.session_state["ultimo_codigo_processado"] = ""
    st.session_state["focar_no_input"] = True


# ==========================================
# INICIALIZAÇÃO
# ==========================================
try:
    inicializar_banco()
except Exception as e:
    st.error(f"Erro ao inicializar o banco de dados: {e}")
    st.stop()

# ==========================================
# CONTEÚDO PRINCIPAL
# ==========================================
if st.session_state["aba_atual"] == "Leitura":
    codigo_lido = st.text_input(
        "🔍 Leitura de Código de Barras:",
        placeholder="PASSE O LEITOR AQUI...",
        key="codigo_input",
    )

    st.button(
        "❌ Limpar",
        use_container_width=True,
        on_click=limpar_dados,
    )

    # Injeção JavaScript para focar no campo após limpar ou ao carregar
    components.html(
        """
        <script>
            function forcarFocoGarantido() {
                var inputs = window.parent.document.querySelectorAll('input[data-testid="stTextInput"]');
                if (inputs.length > 0) {
                    var inputLeitura = inputs[0];
                    inputLeitura.focus();
                    inputLeitura.select();
                }
            }
            setTimeout(forcarFocoGarantido, 100);
            setTimeout(forcarFocoGarantido, 300);
        </script>
    """,
        height=0,
    )

    if codigo_lido:
        codigo_limpo = codigo_lido.strip()

        if st.session_state.get("ultimo_codigo_processado") != codigo_limpo:
            produto = buscar_produto(codigo_limpo)
            if produto:
                baixar_volume(codigo_limpo)
            elif codigo_limpo.isdigit() and (5 <= len(codigo_limpo) <= 14):
                registrar_novo_produto_avulso(codigo_limpo)
            st.session_state["ultimo_codigo_processado"] = codigo_limpo

        produto = buscar_produto(codigo_limpo)

        if produto:
            cod_produto, vol_totais, vol_conferidos = produto

            st.metric(
                label="Quantidade de Volumes",
                value=f"{vol_conferidos} de {vol_totais} Volumes",
            )
            porcentagem = (
                (vol_conferidos / vol_totais) if vol_totais > 0 else 0.0
            )
            st.progress(porcentagem)

            st.markdown(
                f'<div class="txt-codigo-produto">Código do Produto: {cod_produto}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="txt-produto-encontrado">✅ Produto Encontrado</div>',
                unsafe_allow_html=True,
            )
        else:
            if codigo_limpo.isdigit() and (5 <= len(codigo_limpo) <= 14):
                st.metric(label="Quantidade de Volumes", value="1 Volume")
                st.progress(1.0)
                st.markdown(
                    f'<div class="txt-codigo-produto">Código do Produto: AVULSO-{codigo_limpo}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.error("❌ Código digitado/lido está incorreto ou é inválido!")

elif st.session_state["aba_atual"] == "Status":
    st.subheader("📋 Status dos Produtos Cadastrados")

    df_produtos = obter_todos_produtos()
    col_filtros, col_busca = st.columns([1, 1])

    with col_filtros:
        filtro_status = st.radio(
            "Filtrar por status:",
            options=["Todos", "Pendentes 🟡🔴", "Concluídos 🟢"],
            horizontal=True,
        )

    with col_busca:
        busca_filtro = st.text_input(
            "🔎 Pesquisar por código ou EAN:",
            placeholder="Digite para filtrar...",
            key="busca_filtro_key",
        )

    if filtro_status == "Pendentes 🟡🔴":
        df_produtos = df_produtos[
            df_produtos["volumes_conferidos"] < df_produtos["volumes_totais"]
        ]
    elif filtro_status == "Concluídos 🟢":
        df_produtos = df_produtos[
            df_produtos["volumes_conferidos"] == df_produtos["volumes_totais"]
        ]

    if busca_filtro:
        df_produtos = df_produtos[
            df_produtos["Código do Produto"]
            .astype(str)
            .str.contains(busca_filtro, case=False)
            | df_produtos["Código de Barras"]
            .astype(str)
            .str.contains(busca_filtro, case=False)
        ]

    df_exibicao = df_produtos.drop(
        columns=["volumes_conferidos", "volumes_totais"]
    )
    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

elif st.session_state["aba_atual"] == "Opcoes":
    st.subheader("⚙️ Configurações e Ações")

    if st.button("🔄 Reiniciar Toda a Conferência", use_container_width=True):
        resetar_conferencia()
        st.session_state["ultimo_codigo_processado"] = ""
        st.success("Conferência reiniciada com sucesso!")
        st.rerun()

    st.markdown("---")
    st.markdown("### 📲 Conectar outro Coletor")
    url_app = st.text_input(
        "Link do sistema:",
        placeholder="https://seu-sistema.streamlit.app",
        key="url_app_key",
    )

    if url_app:
        qr_img = gerar_qrcode(url_app)
        st.image(
            qr_img,
            caption="Escanear com a câmera do coletor",
            use_container_width=True,
        )

# ==========================================
# RODAPÉ FIXO DE NAVEGAÇÃO
# ==========================================
st.markdown(
    '<div class="titulo-rodape">📦 Conferência de volumes Gaja</div>',
    unsafe_allow_html=True,
)

col_nav1, col_nav2, col_nav3 = st.columns(3)

with col_nav1:
    btn_tipo1 = (
        "primary" if st.session_state["aba_atual"] == "Leitura" else "secondary"
    )
    if st.button("🔍 Leitura", use_container_width=True, type=btn_tipo1):
        st.session_state["aba_atual"] = "Leitura"
        st.rerun()

with col_nav2:
    btn_tipo2 = (
        "primary" if st.session_state["aba_atual"] == "Status" else "secondary"
    )
    if st.button("📋 Status", use_container_width=True, type=btn_tipo2):
        st.session_state["aba_atual"] = "Status"
        st.rerun()

with col_nav3:
    btn_tipo3 = (
        "primary" if st.session_state["aba_atual"] == "Opcoes" else "secondary"
    )
    if st.button("⚙️ Opções", use_container_width=True, type=btn_tipo3):
        st.session_state["aba_atual"] = "Opcoes"
        st.rerun()