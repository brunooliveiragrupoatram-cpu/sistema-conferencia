import io
import os
import sqlite3
import pandas as pd
import qrcode
import streamlit as st

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Sistema de Conferência", page_icon="📦", layout="wide"
)

ARQUIVO_EXCEL = "Programa conferencia.xlsx"
BANCO_DADOS = "conferencia.db"

# ==========================================
# ESTILOS PERSONALIZADOS (CSS)
# ==========================================
st.markdown(
    """
    <style>
    .titulo-reduzido {
        font-size: 18px !important;
        font-weight: bold;
        margin-bottom: 10px;
    }
    
    div[data-baseweb="input"] {
        border: 2px solid #0066cc !important;
        border-radius: 8px !important;
    }
    
    div[data-baseweb="input"] input {
        font-size: 20px !important;
        font-weight: bold !important;
        padding: 8px !important;
    }

    label[data-testid="stWidgetLabel"] {
        font-size: 16px !important;
        font-weight: bold !important;
    }

    .txt-produto-encontrado {
        font-size: 13px !important;
        color: #2e7d32;
        font-weight: bold;
        margin-top: 5px;
    }
    
    .txt-codigo-produto {
        font-size: 15px !important;
        font-weight: bold;
        color: #0066cc;
        margin-bottom: 10px;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# FUNÇÃO PARA GERAR QR CODE
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


# ==========================================
# FUNÇÕES DE BANCO DE DADOS
# ==========================================
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
    """Insere um código não encontrado com 1 volume total e 1 conferido."""
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


# ==========================================
# INICIALIZAÇÃO
# ==========================================
try:
    inicializar_banco()
except Exception as e:
    st.error(f"Erro ao inicializar o banco de dados: {e}")
    st.stop()

# TÍTULO REDUZIDO
st.markdown('<div class="titulo-reduzido">📦 Sistema de Conferência de Volumes</div>', unsafe_allow_html=True)

# ==========================================
# LAYOUT EM COLUNAS
# ==========================================
col_leitura, col_tabela = st.columns([1.2, 1], gap="large")

with col_leitura:
    # 1. LEITOR DE CÓDIGO DE BARRAS
    codigo_lido = st.text_input(
        "🔍 Leitura de Código de Barras:",
        placeholder="PASSE O LEITOR AQUI...",
        key="codigo_input",
    )

    if codigo_lido:
        codigo_limpo = codigo_lido.strip()
        produto = buscar_produto(codigo_limpo)

        if produto:
            cod_produto, vol_totais, vol_conferidos = produto

            # 2. PROGRESSO DA CONFERÊNCIA
            st.metric(
                label="Progresso da Conferência",
                value=f"{vol_conferidos}/{vol_totais} volumes",
            )
            porcentagem = (
                (vol_conferidos / vol_totais) if vol_totais > 0 else 0.0
            )
            st.progress(porcentagem)

            # 3. CONFIRMAR BAIXA
            if vol_conferidos < vol_totais:
                if st.button(
                    "✅ CONFIRMAR BAIXA (+1 VOLUME)",
                    use_container_width=True,
                    type="primary",
                ):
                    baixar_volume(codigo_limpo)
                    st.toast("Volume registrado com sucesso!", icon="🎉")
                    st.session_state["codigo_input"] = ""
                    st.rerun()
            else:
                st.warning(
                    f"⚠️ Todos os {vol_totais} volumes já foram conferidos!"
                )

            st.markdown("---")

            # 4. CÓDIGO DO PRODUTO
            st.markdown(
                f'<div class="txt-codigo-produto">Código do Produto: {cod_produto}</div>',
                unsafe_allow_html=True,
            )

            # 5. PRODUTO ENCONTRADO
            st.markdown(
                '<div class="txt-produto-encontrado">✅ Produto Encontrado</div>',
                unsafe_allow_html=True,
            )

        else:
            # CASO O CÓDIGO NÃO EXISTA NA PLANILHA
            st.error("⚠️ Código não cadastrado na planilha!")
            
            st.metric(
                label="Progresso da Conferência (Item Avulso)",
                value="0/1 volume",
            )
            st.progress(0.0)

            if st.button(
                "✅ CONFIRMAR BAIXA (1 VOLUME)",
                use_container_width=True,
                type="primary",
            ):
                registrar_novo_produto_avulso(codigo_limpo)
                st.toast("Item avulso registrado (1 volume)!", icon="🎉")
                st.session_state["codigo_input"] = ""
                st.rerun()

            st.markdown("---")
            st.markdown(
                f'<div class="txt-codigo-produto">Código do Produto: AVULSO-{codigo_limpo}</div>',
                unsafe_allow_html=True,
            )

with col_tabela:
    st.subheader("📋 Status dos Produtos Cadastrados")

    df_produtos = obter_todos_produtos()

    filtro_status = st.radio(
        "Filtrar por status:",
        options=["Todos", "Pendentes 🟡🔴", "Concluídos 🟢"],
        horizontal=True,
    )

    if filtro_status == "Pendentes 🟡🔴":
        df_produtos = df_produtos[
            df_produtos["volumes_conferidos"] < df_produtos["volumes_totais"]
        ]
    elif filtro_status == "Concluídos 🟢":
        df_produtos = df_produtos[
            df_produtos["volumes_conferidos"] == df_produtos["volumes_totais"]
        ]

    busca_filtro = st.text_input(
        "🔎 Pesquisar por código ou EAN:",
        placeholder="Digite para filtrar...",
    )

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

    st.dataframe(
        df_exibicao,
        use_container_width=True,
        hide_index=True,
    )

# ==========================================
# MENU LATERAL - OPÇÕES E QR CODE
# ==========================================
with st.sidebar:
    st.header("📲 Conectar Coletor")

    url_app = st.text_input(
        "Link do sistema (Streamlit Cloud):",
        placeholder="https://seu-sistema.streamlit.app",
    )

    if url_app:
        qr_img = gerar_qrcode(url_app)
        st.image(
            qr_img,
            caption="Escanear com a câmera ou leitor do coletor",
            use_container_width=True,
        )

    st.markdown("---")
    st.header("⚙️ Opções")
    if st.button("🔄 Reiniciar Toda a Conferência", use_container_width=True):
        resetar_conferencia()
        st.success("Conferência reiniciada!")
        st.rerun()