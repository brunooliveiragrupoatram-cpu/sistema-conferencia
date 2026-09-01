import os
import sqlite3
import pandas as pd
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


def registrar_bip(cod_barras):
    conn = conectar_bd()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT cod_produto, volumes_totais, volumes_conferidos FROM conferencia WHERE cod_barras = ?",
        (cod_barras,),
    )
    produto = cursor.fetchone()

    if produto:
        cod_produto, vol_totais, vol_conferidos = produto

        if vol_conferidos < vol_totais:
            cursor.execute(
                """
                UPDATE conferencia 
                SET volumes_conferidos = volumes_conferidos + 1 
                WHERE cod_barras = ?
            """,
                (cod_barras,),
            )
            conn.commit()
            vol_conferidos += 1
            status = "sucesso"
        else:
            status = "concluido"

        conn.close()
        return status, cod_produto, vol_totais, vol_conferidos

    conn.close()
    return "nao_encontrado", None, 0, 0


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

# ==========================================
# LAYOUT EM COLUNAS
# ==========================================
st.title("📦 Sistema de Conferência de Volumes")

col_leitura, col_tabela = st.columns([1, 1], gap="large")

with col_leitura:
    st.subheader("🔍 Leitura de Código de Barras")

    codigo_lido = st.text_input(
        "Aguardando bip do leitor:",
        placeholder="Passe o leitor aqui...",
        key="codigo_input",
    )

    if codigo_lido:
        codigo_limpo = codigo_lido.strip()
        status, cod_produto, vol_totais, vol_conferidos = registrar_bip(
            codigo_limpo
        )

        if status == "sucesso":
            st.success(f"✅ Volume registrado para o produto **{cod_produto}**!")
            st.metric(
                label="Progresso do Produto",
                value=f"{vol_conferidos}/{vol_totais} volumes",
            )
            porcentagem = (
                (vol_conferidos / vol_totais) if vol_totais > 0 else 0.0
            )
            st.progress(porcentagem)

        elif status == "concluido":
            st.warning(
                f"⚠️ O produto **{cod_produto}** já teve todos os volumes conferidos ({vol_conferidos}/{vol_totais})!"
            )

        else:
            st.error("❌ Código de barras não encontrado no cadastro.")

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
# MENU LATERAL - OPÇÕES
# ==========================================
with st.sidebar:
    st.header("⚙️ Opções")
    if st.button("🔄 Reiniciar Toda a Conferência", use_container_width=True):
        resetar_conferencia()
        st.success("Conferência reiniciada!")
        st.rerun()