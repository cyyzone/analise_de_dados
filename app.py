import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Configuração inicial da página
st.set_page_config(page_title="Análise Aircall e Intercom", layout="wide")

st.title("Análise de Tempo de Resposta e CSAT")
st.write("Mensuração do impacto da automação de status no atendimento.")

# Barra lateral para inputs
st.sidebar.header("Credenciais e Filtros")
api_aircall = st.sidebar.text_input("Token da API do Aircall", type="password")
api_intercom = st.sidebar.text_input("Token da API do Intercom", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("Período de Análise")
data_inicio = st.sidebar.date_input("Data de Início")
data_fim = st.sidebar.date_input("Data Final")
data_corte = st.sidebar.date_input("Data de criação da automação")

def extrair_dados_aircall(token, inicio, fim):
    # Aqui você vai inserir o requests.get para o endpoint do Aircall
    # O ideal é retornar uma lista de dicionários e converter para DataFrame
    # Exemplo do formato esperado:
    dados_mock = [
        {"id": 1, "atendente": "analista@empresa.com", "inicio_chamada": "2026-05-10 10:00:00", "fim_chamada": "2026-05-10 10:15:00"}
    ]
    return pd.DataFrame(dados_mock)

def extrair_dados_intercom(token, inicio, fim):
    # Aqui você vai inserir o requests.post ou get para o Intercom
    # Exemplo do formato esperado:
    dados_mock = [
        {"id": 101, "criado_em": "2026-05-10 10:05:00", "primeira_resposta_em": "2026-05-10 10:18:00", "csat": 4}
    ]
    return pd.DataFrame(dados_mock)

if st.sidebar.button("Processar Análise"):
    if not api_aircall or not api_intercom:
        st.warning("Por favor, insira os tokens das APIs para continuar.")
    else:
        with st.spinner("Extraindo e cruzando informações..."):
            
            # 1. Busca os dados
            df_ligacoes = extrair_dados_aircall(api_aircall, data_inicio, data_fim)
            df_chats = extrair_dados_intercom(api_intercom, data_inicio, data_fim)
            
            # 2. Converte as colunas de texto para formato de data/hora do Pandas
            df_ligacoes['inicio_chamada'] = pd.to_datetime(df_ligacoes['inicio_chamada'])
            df_ligacoes['fim_chamada'] = pd.to_datetime(df_ligacoes['fim_chamada'])
            df_chats['criado_em'] = pd.to_datetime(df_chats['criado_em'])
            df_chats['primeira_resposta_em'] = pd.to_datetime(df_chats['primeira_resposta_em'])
            
            # 3. Calcula o Tempo de Primeira Resposta (TPR) em minutos no Intercom
            df_chats['tpr_minutos'] = (df_chats['primeira_resposta_em'] - df_chats['criado_em']).dt.total_seconds() / 60
            
            # 4. Lógica de cruzamento: Quais chats entraram enquanto o analista estava na ligação?
            # Aqui você pode usar funções do Pandas para filtrar os chats onde a data 'criado_em' 
            # está entre 'inicio_chamada' e 'fim_chamada' daquele dia.
            
            st.success("Dados cruzados com sucesso!")
            
            # 5. Exibição dos resultados na interface
            st.subheader("Comparativo: Antes e Depois da Automação")
            
            col1, col2 = st.columns(2)
            
            # Estes valores são estáticos para visualização da interface
            # No script final, você substituirá pelas médias calculadas no Pandas
            with col1:
                st.markdown("**Antes da Automação**")
                st.metric(label="Tempo de Resposta Médio (TPR)", value="18 min")
                st.metric(label="CSAT Médio", value="4.1")
                
            with col2:
                st.markdown("**Depois da Automação**")
                st.metric(label="Tempo de Resposta Médio (TPR)", value="5 min", delta="-13 min", delta_color="inverse")
                st.metric(label="CSAT Médio", value="4.8", delta="0.7")
