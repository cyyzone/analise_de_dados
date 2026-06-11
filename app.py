import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time
import pytz
import re

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

fuso_br = pytz.timezone('America/Sao_Paulo')

mapa_analistas = {
    "rhayslla.junca@produttivo.com.br": "5281911",
    "douglas.david@produttivo.com.br": "5586698",
    "aline.souza@produttivo.com.br": "5717251",
    "heloisa.atm.slv@produttivo.com.br": "7455039",
    "danielle.ghesini@produttivo.com.br": "7628368",
    "jenyffer.souza@produttivo.com.br": "8115775",
    "marcelo.misugi@produttivo.com.br": "8126602"
}

def extrair_dados_aircall(api_id, api_token, inicio, fim):
    auth = (api_id, api_token)
    url = "https://api.aircall.io/v1/calls"
    lista_final = []
    numeros_permitidos = ['554139060321', '554139060320']
    
    dias = pd.date_range(start=inicio, end=fim)
    
    for dia in dias:
        inicio_dt = fuso_br.localize(datetime.combine(dia.date(), datetime.min.time()))
        fim_dt = fuso_br.localize(datetime.combine(dia.date(), datetime.max.time()))
        ts_inicio = int(inicio_dt.timestamp())
        ts_fim = int(fim_dt.timestamp())
        
        params = {"from": ts_inicio, "to": ts_fim, "per_page": 50, "order": "asc"}
        page = 1
        
        while True:
            params["page"] = page
            response = requests.get(url, params=params, auth=auth)
            
            if response.status_code == 429:
                time.sleep(2)
                continue
                
            if response.status_code != 200:
                break
                
            data = response.json()
            calls = data.get("calls", [])
            
            for c in calls:
                if c.get("answered_at"):
                    numero_bruto = c.get("number", {}).get("digits", "")
                    if not numero_bruto:
                        numero_bruto = c.get("number", {}).get("name", "")
                        
                    numero_limpo = re.sub(r'\D', '', str(numero_bruto))
                    
                    if numero_limpo in numeros_permitidos:
                        inicio_chamada = pd.to_datetime(c.get("answered_at"), unit='s', utc=True).tz_convert(fuso_br).tz_localize(None)
                        fim_chamada = pd.to_datetime(c.get("ended_at") or c.get("answered_at"), unit='s', utc=True).tz_convert(fuso_br).tz_localize(None)
                        
                        lista_final.append({
                            "call_id": c.get("id"),
                            "atendente": c.get("user", {}).get("email"),
                            "inicio_chamada": inicio_chamada,
                            "fim_chamada": fim_chamada,
                            "numero_telefone": numero_bruto
                        })
            
            if len(calls) < 50:
                break
            
            page += 1
            time.sleep(0.2)
            
    return pd.DataFrame(lista_final)

def extrair_dados_intercom(token, inicio, fim):
    inicio_dt = fuso_br.localize(datetime.combine(inicio, datetime.min.time()))
    fim_dt = fuso_br.localize(datetime.combine(fim, datetime.max.time()))
    ts_inicio = int(inicio_dt.timestamp())
    ts_fim = int(fim_dt.timestamp())
    
    url = "https://api.intercom.io/conversations/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    body = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "created_at", "operator": ">", "value": ts_inicio},
                {"field": "created_at", "operator": "<", "value": ts_fim},
                {"field": "team_assignee_id", "operator": "=", "value": "8115775"}
            ]
        }
    }
    
    conversations = []
    
    while True:
        response = requests.post(url, json=body, headers=headers)
        if response.status_code != 200:
            st.error(f"Erro no Intercom: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        conversations.extend(data.get("conversations", []))
        
        pages = data.get("pages", {})
        next_page = pages.get("next", {})
        starting_after = next_page.get("starting_after")
        
        if not starting_after:
            break
            
        body["pagination"] = {"starting_after": starting_after}
        time.sleep(0.2)
        
    lista_final = []
    for conv in conversations:
        stats = conv.get("statistics", {})
        first_reply_ts = stats.get("first_admin_reply_at")
        
        rating = conv.get("conversation_rating")
        csat_val = rating.get("value") if isinstance(rating, dict) else None
        
        assignee_id = str(conv.get("assignee", {}).get("id", ""))
        
        criado_em = pd.to_datetime(conv.get("created_at"), unit='s', utc=True).tz_convert(fuso_br).tz_localize(None)
        primeira_resposta_em = pd.to_datetime(first_reply_ts, unit='s', utc=True).tz_convert(fuso_br).tz_localize(None) if first_reply_ts else pd.NaT
        
        lista_final.append({
            "chat_id": conv.get("id"),
            "assignee_id": assignee_id,
            "criado_em": criado_em,
            "primeira_resposta_em": primeira_resposta_em,
            "csat": csat_val
        })
        
    return pd.DataFrame(lista_final)

if st.button("Processar Análise Real"):
    with st.spinner("Buscando dados das APIs..."):
        
        df_ligacoes = extrair_dados_aircall(aircall_id, aircall_token, data_inicio, data_fim)
        df_chats = extrair_dados_intercom(api_intercom, data_inicio, data_fim)
        
        if df_ligacoes.empty and df_chats.empty:
            st.warning("Não encontramos registros no Aircall nem no Intercom para os filtros aplicados neste período.")
        elif df_ligacoes.empty:
            st.warning("O Intercom trouxe os chats, mas o Aircall não encontrou nenhuma ligação atendida nos números finais 0321 e 0320.")
        elif df_chats.empty:
            st.warning("O Aircall trouxe as ligações, mas o Intercom não retornou nenhum chat para a equipe 8115775 neste período.")
        else:
            st.subheader("Dados Brutos para Validação")
            col_raw1, col_raw2 = st.columns(2)
            with col_raw1:
                st.markdown(f"**Ligações Aircall Filtradas ({len(df_ligacoes)} encontradas)**")
                st.dataframe(df_ligacoes)
            with col_raw2:
                st.markdown(f"**Chats Intercom Filtrados ({len(df_chats)} encontrados)**")
                st.dataframe(df_chats)
                
            st.markdown("---")
            
            df_chats['tpr_minutos'] = (df_chats['primeira_resposta_em'] - df_chats['criado_em']).dt.total_seconds() / 60
            
            chats_sobrepostos = []
            for _, ligacao in df_ligacoes.iterrows():
                email_atendente = ligacao['atendente']
                id_intercom_esperado = mapa_analistas.get(email_atendente)
                
                mask_tempo = (df_chats['criado_em'] >= ligacao['inicio_chamada']) & (df_chats['criado_em'] <= ligacao['fim_chamada'])
                mask_analista = (df_chats['assignee_id'] == id_intercom_esperado)
                
                conversas_no_periodo = df_chats[mask_tempo & mask_analista].copy()
                
                if not conversas_no_periodo.empty:
                    conversas_no_periodo['atendente_telefone'] = email_atendente
                    conversas_no_periodo['id_chamada'] = ligacao['call_id']
                    conversas_no_periodo['inicio_chamada'] = ligacao['inicio_chamada']
                    conversas_no_periodo['fim_chamada'] = ligacao['fim_chamada']
                    chats_sobrepostos.append(conversas_no_periodo)
            
            if not chats_sobrepostos:
                st.info("Nenhum chat foi atribuído ao mesmo analista no exato momento em que ele estava na ligação.")
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
                    st.caption(f"Total de chats com o analista em ligação: {len(df_antes)}")
                    
                with col2:
                    st.markdown("### Depois da Automação")
                    delta_tpr = tpr_depois - tpr_antes
                    delta_csat = csat_depois - csat_antes if csat_antes > 0 and csat_depois > 0 else 0
                    
                    st.metric(label="Tempo de Resposta Médio (TPR)", value=f"{tpr_depois:.1f} min", 
                              delta=f"{delta_tpr:.1f} min", delta_color="inverse")
                    st.metric(label="Satisfação Média (CSAT)", value=f"{csat_depois:.1f} *" if csat_depois > 0 else "Sem dados",
                              delta=f"{delta_csat:.1f} *" if delta_csat != 0 else None)
                    st.caption(f"Total de chats com o analista em ligação: {len(df_depois)}")
                    
                st.markdown("---")
                st.subheader("Detalhamento para Validação")
                
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
