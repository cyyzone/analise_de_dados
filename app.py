import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

st.set_page_config(page_title="Análise Aircall e Intercom", layout="wide")

st.title("Análise de Tempo de Resposta e CSAT")
st.write("Mensuração do impacto da automação de status no atendimento.")

try:
    aircall_id = st.secrets["AIRCALL_ID"]
    aircall_token = st.secrets["AIRCALL_TOKEN"]
    api_intercom = st.secrets["INTERCOM_TOKEN"]
except KeyError:
    st.error("Erro: As credenciais não foram encontradas no arquivo .streamlit/secrets.toml")
    st.stop()

st.sidebar.header("Período de Análise")
data_inicio = st.sidebar.date_input("Data de Início", datetime(2026, 1, 1))
data_fim = st.sidebar.date_input("Data Final", datetime(2026, 1, 31))
data_corte = st.sidebar.date_input("Data da Automação", datetime(2026, 1, 15))

def extrair_dados_aircall(api_id, api_token, inicio, fim):
    ts_inicio = int(time.mktime(inicio.timetuple()))
    ts_fim = int(time.mktime(fim.timetuple())) + 86399
    
    auth = (api_id, api_token)
    url = "https://api.aircall.io/v1/calls"
    params = {"from": ts_inicio, "to": ts_fim, "per_page": 50, "order": "asc"}
    
    calls = []
    page = 1
    
    while True:
        params["page"] = page
        response = requests.get(url, params=params, auth=auth)
        if response.status_code != 200:
            st.error(f"Erro no Aircall: {response.status_code}")
            break
            
        data = response.json()
        calls.extend(data.get("calls", []))
        
        meta = data.get("meta", {})
        if not meta.get("next_page_link") or page >= meta.get("max_pages", 1):
            break
        page += 1
        
    lista_final = []
    for c in calls:
        if c.get("answered_at"):
            lista_final.append({
                "call_id": c.get("id"),
                "atendente": c.get("user", {}).get("email"),
                "inicio_chamada": datetime.fromtimestamp(c.get("answered_at")),
                "fim_chamada": datetime.fromtimestamp(c.get("ended_at")) if c.get("ended_at") else datetime.fromtimestamp(c.get("answered_at"))
            })
    return pd.DataFrame(lista_final)

def extrair_dados_intercom(token, inicio, fim):
    ts_inicio = int(time.mktime(inicio.timetuple()))
    ts_fim = int(time.mktime(fim.timetuple())) + 86399
    
    url = "https://api.intercom.io/conversations/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    query = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "created_at", "operator": ">", "value": ts_inicio},
                {"field": "created_at", "operator": "<", "value": ts_fim}
            ]
        }
    }
    
    response = requests.post(url, json=query, headers=headers)
    if response.status_code != 200:
        st.error(f"Erro no Intercom: {response.status_code}")
        return pd.DataFrame()
        
    data = response.json()
    conversations = data.get("conversations", [])
    
    lista_final = []
    for conv in conversations:
        stats = conv.get("statistics", {})
        first_reply_ts = stats.get("first_admin_reply_at")
        
        rating = conv.get("conversation_rating")
        if isinstance(rating, dict):
            csat_val = rating.get("value")
        else:
            csat_val = None
        
        lista_final.append({
            "chat_id": conv.get("id"),
            "criado_em": datetime.fromtimestamp(conv.get("created_at")),
            "primeira_resposta_em": datetime.fromtimestamp(first_reply_ts) if first_reply_ts else None,
            "csat": csat_val
        })
    return pd.DataFrame(lista_final)

if st.button("Processar Análise Real"):
    with st.spinner("Buscando dados das APIs..."):
        
        df_ligacoes = extrair_dados_aircall(aircall_id, aircall_token, data_inicio, data_fim)
        df_chats = extrair_dados_intercom(api_intercom, data_inicio, data_fim)
        
        if df_ligacoes.empty or df_chats.empty:
            st.warning("Não encontramos registros completos para o período selecionado.")
        else:
            df_ligacoes['inicio_chamada'] = pd.to_datetime(df_ligacoes['inicio_chamada'])
            df_ligacoes['fim_chamada'] = pd.to_datetime(df_ligacoes['fim_chamada'])
            df_chats['criado_em'] = pd.to_datetime(df_chats['criado_em'])
            df_chats['primeira_resposta_em'] = pd.to_datetime(df_chats['primeira_resposta_em'])
            
            df_chats['tpr_minutos'] = (df_chats['primeira_resposta_em'] - df_chats['criado_em']).dt.total_seconds() / 60
            
            chats_sobrepostos = []
            for _, ligacao in df_ligacoes.iterrows():
                mask = (df_chats['criado_em'] >= ligacao['inicio_chamada']) & (df_chats['criado_em'] <= ligacao['fim_chamada'])
                conversas_no_periodo = df_chats[mask].copy()
                if not conversas_no_periodo.empty:
                    # Guardando os dados da ligação junto com o chat
                    conversas_no_periodo['atendente_telefone'] = ligacao['atendente']
                    conversas_no_periodo['id_chamada'] = ligacao['call_id']
                    conversas_no_periodo['inicio_chamada'] = ligacao['inicio_chamada']
                    conversas_no_periodo['fim_chamada'] = ligacao['fim_chamada']
                    chats_sobrepostos.append(conversas_no_periodo)
            
            if not chats_sobrepostos:
                st.info("Nenhum chat entrou no exato momento em que os analistas estavam em ligações.")
            else:
                df_final = pd.concat(chats_sobrepostos).drop_duplicates(subset=['chat_id'])
                
                dt_corte_convertida = pd.to_datetime(data_corte)
                df_antes = df_final[df_final['criado_em'].dt.date < dt_corte_convertida.date()]
                df_depois = df_final[df_final['criado_em'].dt.date >= dt_corte_convertida.date()]
                
                tpr_antes = df_antes['tpr_minutos'].mean() if not df_antes.empty else 0
                tpr_depois = df_depois['tpr_minutos'].mean() if not df_depois.empty else 0
                csat_antes = df_antes['csat'].mean() if not df_antes.empty else 0
                csat_depois = df_depois['csat'].mean() if not df_depois.empty else 0
                
                st.subheader("Resultados do Cruzamento de Dados")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("### Antes da Automação")
                    st.metric(label="Tempo de Resposta Médio (TPR)", value=f"{tpr_antes:.1f} min")
                    st.metric(label="Satisfação Média (CSAT)", value=f"{csat_antes:.1f} *" if csat_antes > 0 else "Sem dados")
                    st.caption(f"Total de chats em ligação: {len(df_antes)}")
                    
                with col2:
                    st.markdown("### Depois da Automação")
                    delta_tpr = tpr_depois - tpr_antes
                    delta_csat = csat_depois - csat_antes if csat_antes > 0 and csat_depois > 0 else 0
                    
                    st.metric(label="Tempo de Resposta Médio (TPR)", value=f"{tpr_depois:.1f} min", 
                              delta=f"{delta_tpr:.1f} min", delta_color="inverse")
                    st.metric(label="Satisfação Média (CSAT)", value=f"{csat_depois:.1f} *" if csat_depois > 0 else "Sem dados",
                              delta=f"{delta_csat:.1f} *" if delta_csat != 0 else None)
                    st.caption(f"Total de chats em ligação: {len(df_depois)}")
                    
                st.markdown("---")
                st.subheader("Detalhamento para Validação")
                st.write("Abaixo estão todos os chats que entraram exatamente enquanto o analista estava ao telefone.")
                
                colunas_exibicao = [
                    'id_chamada', 'atendente_telefone', 'inicio_chamada', 'fim_chamada', 
                    'chat_id', 'criado_em', 'tpr_minutos', 'csat'
                ]
                
                st.dataframe(df_final[colunas_exibicao])
                
                csv = df_final[colunas_exibicao].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Baixar dados para validação (CSV)",
                    data=csv,
                    file_name='validacao_automacao_status.csv',
                    mime='text/csv',
                )
