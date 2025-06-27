import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import json

# --- Configurações da Página Streamlit (DEVE SER O PRIMEIRO COMANDO STREAMLIT) ---
st.set_page_config(
    page_title="Finanças da Família 💰",
    page_icon="💸",
    layout="wide"
)

# --- Configurações Iniciais ---
DB_NAME = 'financas_familia.db' # Nome do arquivo do banco de dados

# --- Funções de Ajuda para Segurança (Hashing) ---
def make_hashes(password):
    """Cria um hash SHA256 da senha para armazenamento seguro."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Verifica se a senha fornecida corresponde ao hash armazenado."""
    return make_hashes(password) == hashed_text

# --- Funções do Banco de Dados para Usuários ---
def init_user_db():
    """Inicializa o banco de dados de usuários e cria a tabela 'users'."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        ''')
        conn.commit()

def add_user(username, password):
    """Adiciona um novo usuário ao banco de dados."""
    hashed_password = make_hashes(password)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            return True
        except sqlite3.IntegrityError: # Usuário já existe
            return False

def verify_user(username, password):
    """Verifica as credenciais do usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result:
            hashed_password_db = result[0]
            return check_hashes(password, hashed_password_db)
        return False

# --- Funções do Banco de Dados para Transações Financeiras ---
def init_transactions_db():
    """Inicializa o banco de dados de transações e cria a tabela 'transacoes'."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                tipo TEXT NOT NULL, -- 'receita' ou 'despesa'
                categoria TEXT,    -- para despesa ou tipo de receita
                username TEXT NOT NULL, -- Para vincular a transação ao usuário logado
                
                -- Campos específicos para Receita
                responsavel TEXT, 
                banco TEXT,       
                forma_recebimento TEXT, 
                datas_parcelas_receita TEXT,    -- JSON string de datas
                
                -- Novos campos específicos para Despesa
                recorrente TEXT,    -- 'Sim' ou 'Não'
                vezes_recorrencia INTEGER, -- Quantas vezes a despesa se repete
                status TEXT,        -- 'A Pagar' ou 'Pago'
                
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        conn.commit()

# --- Funções do Banco de Dados para Metas ---
def init_goals_db():
    """Inicializa o banco de dados de metas e cria a tabela 'goals'."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor_meta REAL NOT NULL,
                categoria TEXT NOT NULL,
                data_limite TEXT NOT NULL,
                valor_atual REAL DEFAULT 0.0, -- Quanto já foi contribuído para a meta
                status TEXT DEFAULT 'Em Progresso', -- 'Em Progresso', 'Concluída', 'Cancelada'
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        conn.commit()

def add_goal(username, descricao, valor_meta, categoria, data_limite):
    """Adiciona uma nova meta ao banco de dados."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO goals (username, descricao, valor_meta, categoria, data_limite, status)
            VALUES (?, ?, ?, ?, ?, 'Em Progresso')
        ''', (username, descricao, valor_meta, categoria, data_limite))
        conn.commit()

def get_goals(username):
    """Recupera todas as metas de um usuário específico."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, descricao, valor_meta, categoria, data_limite, valor_atual, status FROM goals WHERE username = ?", (username,))
        return cursor.fetchall()

def update_goal_progress(goal_id, username, amount):
    """Atualiza o progresso (valor_atual) de uma meta."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE goals SET valor_atual = valor_atual + ? WHERE id = ? AND username = ?", (amount, goal_id, username))
        conn.commit()

def mark_goal_as_completed(goal_id, username):
    """Marca uma meta como concluída e define valor_atual como valor_meta."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Primeiro, obtenha o valor_meta da meta
        cursor.execute("SELECT valor_meta FROM goals WHERE id = ? AND username = ?", (goal_id, username))
        result = cursor.fetchone()
        if result:
            valor_meta = result[0]
            cursor.execute("UPDATE goals SET status = 'Concluída', valor_atual = ? WHERE id = ? AND username = ?", (valor_meta, goal_id, username))
            conn.commit()
            return True
        return False

def delete_goal(goal_id, username):
    """Exclui uma meta específica de um usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM goals WHERE id = ? AND username = ?", (goal_id, username))
        conn.commit()
        return cursor.rowcount > 0


# Funções para gerenciar Nomes e Bancos
def get_unique_responsibles(username):
    """Obtém todos os responsáveis únicos para um usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT responsavel FROM transacoes WHERE username = ? AND responsavel IS NOT NULL", (username,))
        return [row[0] for row in cursor.fetchall()]

def get_unique_banks(username):
    """Obtém todos os bancos únicos para um usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT banco FROM transacoes WHERE username = ? AND banco IS NOT NULL", (username,))
        return [row[0] for row in cursor.fetchall()]


def add_transaction(username, data, descricao, valor, tipo, categoria=None,
                    responsavel=None, banco=None, forma_recebimento=None, datas_parcelas_receita=None,
                    recorrente=None, vezes_recorrencia=None, status=None):
    """Adiciona uma nova transação ao banco de dados, vinculada ao usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transacoes (username, data, descricao, valor, tipo, categoria,
                                    responsavel, banco, forma_recebimento, datas_parcelas_receita,
                                    recorrente, vezes_recorrencia, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (username, data, descricao, valor, tipo, categoria,
              responsavel, banco, forma_recebimento, datas_parcelas_receita,
              recorrente, vezes_recorrencia, status))
        conn.commit()

def get_transactions(username):
    """Recupera todas as transações de um usuário específico."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, data, descricao, valor, tipo, categoria, responsavel, banco,
                   forma_recebimento, datas_parcelas_receita, recorrente,
                   vezes_recorrencia, status
            FROM transacoes WHERE username = ? ORDER BY data DESC
        ''', (username,))
        return cursor.fetchall()

def delete_transaction(transaction_id, username):
    """Exclui uma transação específica de um usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transacoes WHERE id = ? AND username = ?", (transaction_id, username))
        conn.commit()
        return cursor.rowcount > 0 # Retorna True se alguma linha foi deletada

def update_transaction(transaction_id, username, **kwargs):
    """Atualiza uma transação específica de um usuário."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.extend([transaction_id, username]) # Adiciona ID e username no final para a cláusula WHERE

        try:
            cursor.execute(f"UPDATE transacoes SET {set_clause} WHERE id = ? AND username = ?", tuple(values))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao atualizar transação: {e}")
            return False

def get_summary_current_month(username):
    """Calcula o resumo de receitas e despesas para o mês atual para um usuário específico."""
    current_year_month = datetime.now().strftime("%Y-%m")
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Receitas do mês atual
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE username = ? AND tipo = 'receita' AND strftime('%Y-%m', data) = ?", (username, current_year_month))
        total_receitas = cursor.fetchone()[0] or 0.0

        # Despesas pagas do mês atual
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE username = ? AND tipo = 'despesa' AND status = 'Pago' AND strftime('%Y-%m', data) = ?", (username, current_year_month))
        total_despesas_pagas = cursor.fetchone()[0] or 0.0

        # Despesas a pagar do mês atual
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE username = ? AND tipo = 'despesa' AND status = 'A Pagar' AND strftime('%Y-%m', data) = ?", (username, current_year_month))
        total_despesas_apagar = cursor.fetchone()[0] or 0.0

        return total_receitas, total_despesas_pagas, total_despesas_apagar

# --- Funções de Renderização de Formulários ---
def render_unified_transaction_form(current_username):
    """Função para renderizar o formulário de Entrada/Despesa unificado."""
    st.header("➕ Adicionar Novo Lançamento")

    # Escolha do tipo de lançamento
    transaction_type = st.radio("Tipo de Lançamento", ["Receita", "Despesa"], horizontal=True)

    with st.form("unified_transaction_form", clear_on_submit=True):
        # Campos comuns a ambos os tipos
        col_date, col_value = st.columns(2)
        with col_date:
            data_transacao = st.date_input("Data da Transação", datetime.now())
        with col_value:
            valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        
        descricao = st.text_input("Descrição", placeholder="Ex: Salário, Aluguel, Compra de Supermercado")

        # Inicializa todos os campos extras como None
        responsavel = None
        banco = None
        forma_recebimento = None
        datas_parcelas_receita_json = None
        categoria_selecionada = None
        recorrente = None
        vezes_recorrencia = None
        status = None

        if transaction_type == "Receita":
            st.markdown("---")
            st.subheader("Detalhes da Receita")
            
            # Responsável pela Entrada
            existing_responsibles = get_unique_responsibles(current_username)
            # Garante que o usuário logado esteja sempre no topo e sem duplicatas
            all_responsibles_options = [current_username] + sorted([r for r in existing_responsibles if r != current_username and r is not None])
            all_responsibles_options.append("Adicionar Outro...") # Adiciona a opção de adicionar novo
            
            selected_responsavel = st.selectbox("Responsável pela Entrada", all_responsibles_options)
            
            if selected_responsavel == "Adicionar Outro...":
                novo_responsavel = st.text_input("Nome do Novo Responsável pela Entrada", key="new_responsavel_input")
                if novo_responsavel:
                    responsavel = novo_responsavel
                else:
                    st.warning("Por favor, insira o nome do novo responsável.")
            else:
                responsavel = selected_responsavel

            # Banco
            existing_banks = get_unique_banks(current_username)
            all_banks_options = sorted([b for b in existing_banks if b is not None]) 
            all_banks_options.append("Cadastrar Novo Banco...") # Adiciona a opção de cadastrar novo

            selected_bank = st.selectbox("Banco", all_banks_options)

            if selected_bank == "Cadastrar Novo Banco...":
                novo_banco = st.text_input("Nome do Novo Banco", key="new_bank_input")
                if novo_banco:
                    banco = novo_banco
                else:
                    st.warning("Por favor, insira o nome do novo banco.")
            else:
                banco = selected_bank
            
            col_type, col_form = st.columns(2)
            with col_type:
                # Usamos categoria para tipo de entrada na DB
                categoria_selecionada = st.selectbox("Tipo de Entrada (Categoria)", ["Venda de Produto", "Prestação de Serviço", "Salário", "Investimento", "Outros"]) 
            with col_form:
                forma_recebimento = st.selectbox("Forma de Recebimento", ["Parcela Única", "2x", "3x", "4x", "5x", "6x", "Mais de 6x"])

            if forma_recebimento not in ["Parcela Única", "Mais de 6x"]:
                st.markdown("##### Datas de Recebimento das Parcelas")
                datas_parcelas = []
                try:
                    num_parcelas = int(forma_recebimento.replace('x', ''))
                    for i in range(1, num_parcelas + 1):
                        parcel_date = st.date_input(f"Data da {i}ª Parcela", datetime.now().date() + pd.DateOffset(months=i-1), key=f"receita_parcel_date_{i}")
                        datas_parcelas.append(parcel_date.strftime("%Y-%m-%d"))
                    datas_parcelas_receita_json = json.dumps(datas_parcelas)
                except ValueError: # Caso seja "Mais de 6x" ou outra opção que não converta para int
                    st.warning("Para 'Mais de 6x', por favor, registre as parcelas individualmente.")

            # Limpar campos de despesa
            recorrente, vezes_recorrencia, status = None, None, None

        elif transaction_type == "Despesa":
            st.markdown("---")
            st.subheader("Detalhes da Despesa")
            categorias_despesa = [
                "Alimentação", "Transporte", "Moradia", "Lazer", "Educação",
                "Saúde", "Contas Fixas", "Compras", "Outros", "Investimentos"
            ]
            categoria_selecionada = st.selectbox("Categoria", categorias_despesa)

            col_rec, col_status = st.columns(2)
            with col_rec:
                recorrente = st.radio("Despesa Recorrente?", ["Não", "Sim"])
                vezes_recorrencia = None
                if recorrente == "Sim":
                    vezes_recorrencia = st.number_input("Quantas vezes a despesa se repete (incluindo a atual)?", min_value=1, value=1, step=1)
                    st.info("Para despesas recorrentes, apenas o primeiro lançamento é adicionado. As futuras parcelas precisam ser registradas individualmente ou por automação.")
            with col_status:
                status = st.radio("Status da Despesa", ["A Pagar", "Pago"])
            
            # Limpar campos de receita
            responsavel, banco, forma_recebimento, datas_parcelas_receita_json = None, None, None, None

        submitted = st.form_submit_button("Adicionar Lançamento", use_container_width=True)

        if submitted:
            if not descricao or not valor:
                st.error("Por favor, preencha a descrição e o valor.")
            else:
                try:
                    data_str = data_transacao.strftime("%Y-%m-%d")
                    add_transaction( # Chamada para a função global
                        username=current_username,
                        data=data_str,
                        descricao=descricao,
                        valor=float(valor),
                        tipo=transaction_type.lower(),
                        categoria=categoria_selecionada, 
                        responsavel=responsavel,
                        banco=banco,
                        forma_recebimento=forma_recebimento,
                        datas_parcelas_receita=datas_parcelas_receita_json,
                        recorrente=recorrente,          
                        vezes_recorrencia=vezes_recorrencia, 
                        status=status                   
                    )
                    st.success(f"{transaction_type.capitalize()} adicionada com sucesso! 🎉")
                    st.balloons()
                    st.rerun() # Recarrega a página para refletir a nova transação
                except Exception as e:
                    st.error(f"Erro ao adicionar {transaction_type}: {e}")
                    st.exception(e) # Mostra o erro completo para debug

# --- Funções de Renderização dos Elementos do Dashboard e Análises ---
def render_overview_dashboard(current_username, df_all_transactions):
    """Renderiza o dashboard de visão geral compacta."""
    st.header("📊 Visão Geral Financeira")

    # Resumo do mês corrente
    total_receitas_mes, total_despesas_pagas_mes, total_despesas_apagar_mes = get_summary_current_month(current_username)
    saldo_real_mes = total_receitas_mes - total_despesas_pagas_mes
    saldo_projetado_mes = total_receitas_mes - (total_despesas_pagas_mes + total_despesas_apagar_mes)

    st.markdown(f"### Saldo Real (Mês Atual): <span style='color:{'green' if saldo_real_mes >= 0 else 'red'};'>R$ {saldo_real_mes:,.2f}</span>", unsafe_allow_html=True)
    st.markdown(f"### Saldo Projetado (Mês Atual, Considerandando a Pagar): <span style='color:{'green' if saldo_projetado_mes >= 0 else 'red'};'>R$ {saldo_projetado_mes:,.2f}</span>", unsafe_allow_html=True)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Receitas (Mês)", f"R$ {total_receitas_mes:,.2f}", delta_color="normal")
    with col2:
        st.metric("Despesas Pagas (Mês)", f"R$ {total_despesas_pagas_mes:,.2f}", delta_color="inverse")
    with col3:
        st.metric("Despesas a Pagar (Mês)", f"R$ {total_despesas_apagar_mes:,.2f}", delta_color="inverse")
    
    st.markdown("---")
    st.subheader("Tendência Mensal (Últimos 12 Meses)")
    if not df_all_transactions.empty:
        # Filtrar transações dos últimos 12 meses
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(months=12)
        
        df_filtered = df_all_transactions[
            (df_all_transactions['Data'] >= start_date) & 
            (df_all_transactions['Data'] <= end_date)
        ].copy() 

        if not df_filtered.empty:
            df_filtered['AnoMes'] = df_filtered['Data'].dt.to_period('M').astype(str)
            
            # Use pivot_table para garantir que todos os tipos de transação ('receita', 'despesa') estejam presentes como colunas
            # e preencha os valores ausentes com 0
            monthly_summary = pd.pivot_table(df_filtered, values='Valor', index='AnoMes', columns='Tipo', aggfunc='sum', fill_value=0)
            
            # Renomeia as colunas para o que px.line espera
            monthly_summary = monthly_summary.rename(columns={'despesa': 'Despesa', 'receita': 'Receita'})
            
            # Garante que as colunas 'Receita' e 'Despesa' existam, mesmo que não haja dados
            for col in ['Receita', 'Despesa']:
                if col not in monthly_summary.columns:
                    monthly_summary[col] = 0.0

            # Calcula o Saldo
            monthly_summary['Saldo'] = monthly_summary['Receita'] - monthly_summary['Despesa']
            
            # Reindexar para garantir que todos os meses no período estejam presentes
            all_months = pd.period_range(start_date, end_date, freq='M').astype(str)
            monthly_summary = monthly_summary.reindex(all_months, fill_value=0)
            
            # Reiniciar o índice para que 'AnoMes' se torne uma coluna normal novamente
            # Ao invés de `reset_index()`, que pode renomear para 'index',
            # vamos criar uma nova coluna 'AnoMes' a partir do índice e depois resetar/dropar o índice antigo se necessário.
            # No entanto, com pivot_table e reindex, 'AnoMes' já deveria ser o índice.
            # Vamos garantir que a coluna 'AnoMes' seja explicitamente criada a partir do índice ANTES de resetar.
            monthly_summary['AnoMes'] = monthly_summary.index # Cria a coluna 'AnoMes' a partir do índice
            monthly_summary = monthly_summary.reset_index(drop=True) # Reseta o índice sem criar uma coluna 'index' extra

            fig = px.line(monthly_summary, x='AnoMes', y=['Receita', 'Despesa', 'Saldo'], # Agora 'AnoMes' é uma coluna
                          title='Receitas, Despesas e Saldo Mensal',
                          labels={'value': 'Valor (R$)', 'AnoMes': 'Mês'}, # Corrigido para 'AnoMes'
                          color_discrete_map={'Receita': 'green', 'Despesa': 'red', 'Saldo': 'blue'})
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma transação nos últimos 12 meses para análise de tendência.")
    else:
        st.info("Nenhuma transação para análise de tendência ainda.")

    st.markdown("---")
    st.subheader("Progresso das Metas")
    goals = get_goals(current_username)
    if goals:
        goals_df = pd.DataFrame(goals, columns=['ID', 'Descrição', 'Valor Meta', 'Categoria', 'Data Limite', 'Valor Atual', 'Status'])
        goals_df['Progresso (%)'] = (goals_df['Valor Atual'] / goals_df['Valor Meta'] * 100).round(2)
        goals_df['Progresso (%)'] = goals_df['Progresso (%)'].clip(upper=100) # Limita a 100%

        # Exibir metas em progresso e concluídas separadamente ou com ícones
        st.dataframe(goals_df[['Descrição', 'Valor Meta', 'Valor Atual', 'Progresso (%)', 'Data Limite', 'Status']].style.format({
            'Valor Meta': "R$ {:,.2f}",
            'Valor Atual': "R$ {:,.2f}",
            'Progresso (%)': "{:.2f}%"
        }), use_container_width=True, hide_index=True)

        for index, row in goals_df.iterrows():
            if row['Status'] == 'Em Progresso':
                st.write(f"**{row['Descrição']}** ({row['Categoria']}) - R$ {row['Valor Atual']:,.2f} / R$ {row['Valor Meta']:,.2f}")
                st.progress(float(row['Progresso (%)']) / 100)
            elif row['Status'] == 'Concluída':
                st.write(f"**{row['Descrição']}** ({row['Categoria']}) - **Concluída!** 🎉")
                st.progress(1.0) # 100%

        # Gráfico de progresso das metas
        # Filtrar metas não concluídas para o gráfico principal se houver muitas metas concluídas
        goals_for_chart = goals_df[goals_df['Status'] == 'Em Progresso'].copy()
        if not goals_for_chart.empty:
            fig_goals = px.bar(goals_for_chart, x='Descrição', y=['Valor Atual', 'Valor Meta'], 
                            title='Progresso das Metas Financeiras (Em Progresso)',
                            barmode='overlay', # ou 'group'
                            labels={'value': 'Valor (R$)', 'Descrição': 'Meta'},
                            color_discrete_map={'Valor Atual': '#4CAF50', 'Valor Meta': '#C0C0C0'}, # Verde para atual, cinza para meta
                            height=400)
            fig_goals.update_traces(marker_line_width=0) # Remove bordas das barras
            st.plotly_chart(fig_goals, use_container_width=True)
        else:
            st.info("Todas as suas metas estão concluídas ou não há metas em progresso para exibir o gráfico.")

    else:
        st.info("Nenhuma meta definida ainda. Vá para a seção 'Planejamento' para criar suas metas!")


    st.markdown("---")
    st.subheader("Últimas Transações")
    if not df_all_transactions.empty:
        # Exibe as 10 transações mais recentes
        display_columns = [
            'Data', 'Tipo', 'Descrição', 'Valor', 'Categoria', 'Status',
            'Responsavel', 'Banco', 'Forma Recebimento', 'Recorrente'
        ]
        # Formata o valor para exibição (negativo para despesas)
        df_display = df_all_transactions.head(10).copy()
        df_display['Valor_Exibicao'] = df_display.apply(lambda row: -row['Valor'] if row['Tipo'] == 'despesa' else row['Valor'], axis=1)
        df_display['Tipo_Exibicao'] = df_display['Tipo'].apply(lambda x: 'Despesa' if x == 'despesa' else 'Receita')
        
        st.dataframe(df_display[display_columns].style.format({'Valor_Exibicao': "R$ {:,.2f}"}), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma transação recente para exibir.")

def render_transactions_table(current_username, df_all_transactions):
    """Renderiza a tabela de todas as transações com funcionalidades de filtro, busca e edição."""
    st.header("📝 Todas as Transações")

    if df_all_transactions.empty:
        st.info("Nenhuma transação registrada ainda.")
        return

    # --- Filtros e Busca ---
    st.subheader("Filtros")
    col_search, col_type_filter = st.columns([2, 1])
    with col_search:
        search_query = st.text_input("Buscar por Descrição ou Categoria", placeholder="Ex: aluguel, salário, supermercado")
    with col_type_filter:
        type_filter = st.selectbox("Filtrar por Tipo", ["Todos", "Receita", "Despesa"])

    col_cat_filter, col_status_filter = st.columns(2)
    with col_cat_filter:
        all_categories = df_all_transactions['Categoria'].dropna().unique().tolist()
        category_filter = st.multiselect("Filtrar por Categoria", options=all_categories, default=all_categories)
    with col_status_filter:
        all_statuses = df_all_transactions['Status'].dropna().unique().tolist()
        status_filter = st.multiselect("Filtrar por Status (Despesa)", options=all_statuses, default=all_statuses)

    col_date_start, col_date_end = st.columns(2)
    with col_date_start:
        min_date_val = df_all_transactions['Data'].min().date() if not df_all_transactions.empty else datetime.now().date()
        date_start = st.date_input("Data Inicial", min_date_val)
    with col_date_end:
        max_date_val = df_all_transactions['Data'].max().date() if not df_all_transactions.empty else datetime.now().date()
        date_end = st.date_input("Data Final", datetime.now().date())

    df_filtered = df_all_transactions.copy()

    # Aplicar filtros
    if search_query:
        df_filtered = df_filtered[
            df_filtered['Descrição'].str.contains(search_query, case=False, na=False) |
            df_filtered['Categoria'].str.contains(search_query, case=False, na=False)
        ]
    
    if type_filter != "Todos":
        df_filtered = df_filtered[df_filtered['Tipo'] == type_filter.lower()]
    
    if category_filter:
        df_filtered = df_filtered[df_filtered['Categoria'].isin(category_filter)]
    
    if status_filter:
        # Apenas aplica o filtro de status para despesas ou se o tipo for "Despesa"
        if type_filter == "Despesa":
            df_filtered = df_filtered[df_filtered['Status'].isin(status_filter)]
        elif type_filter == "Todos":
            # Filtra despesas pelo status e concatena com receitas
            despesas_filtradas = df_filtered[(df_filtered['Tipo'] == 'despesa') & (df_filtered['Status'].isin(status_filter))]
            receitas = df_filtered[df_filtered['Tipo'] == 'receita']
            df_filtered = pd.concat([despesas_filtradas, receitas])

    # Filtrar por data
    df_filtered = df_filtered[
        (df_filtered['Data'].dt.date >= date_start) & 
        (df_filtered['Data'].dt.date <= date_end)
    ]
    
    # Adicionar coluna de exibição para valores
    df_filtered['Valor_Exibicao'] = df_filtered.apply(lambda row: -row['Valor'] if row['Tipo'] == 'despesa' else row['Valor'], axis=1)
    df_filtered['Tipo_Exibicao'] = df_filtered['Tipo'].apply(lambda x: 'Despesa' if x == 'despesa' else 'Receita')

    # Colunas a serem exibidas e formatadas
    display_cols_for_editor = [
        'ID', 'Data', 'Tipo_Exibicao', 'Descrição', 'Valor_Exibicao', 'Categoria', 'Status',
        'Responsavel', 'Banco', 'Forma Recebimento', 'Recorrente'
    ]
    
    st.subheader("Transações Encontradas")
    if not df_filtered.empty:
        # Obter opções dinâmicas para SelectboxColumns
        responsibles_options_for_editor = get_unique_responsibles(current_username)
        # Adicionar o username logado se ainda não estiver na lista
        if current_username not in responsibles_options_for_editor:
            responsibles_options_for_editor.insert(0, current_username)
        responsibles_options_for_editor = [r for r in responsibles_options_for_editor if r is not None] # Remover None

        banks_options_for_editor = [b for b in get_unique_banks(current_username) if b is not None] # Remover None
        
        edited_df = st.data_editor(
            df_filtered[display_cols_for_editor].rename(columns={'Tipo_Exibicao': 'Tipo', 'Valor_Exibicao': 'Valor'}),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "ID": st.column_config.NumberColumn("ID", help="Identificador único da transação", disabled=True),
                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "Tipo": st.column_config.Column("Tipo", disabled=True), # Não permitir mudar o tipo diretamente
                "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=["Alimentação", "Transporte", "Moradia", "Lazer", "Educação",
                                         "Saúde", "Contas Fixas", "Compras", "Outros", 
                                         "Venda de Produto", "Prestação de Serviço", "Salário", "Investimento", "Outro"],
                    required=True
                ),
                "Status": st.column_config.SelectboxColumn("Status", options=["A Pagar", "Pago"]),
                "Responsavel": st.column_config.SelectboxColumn("Responsável", options=responsibles_options_for_editor, required=False),
                "Banco": st.column_config.SelectboxColumn("Banco", options=banks_options_for_editor, required=False),
                "Forma Recebimento": st.column_config.SelectboxColumn("Forma Recebimento", options=["Parcela Única", "2x", "3x", "4x", "5x", "6x", "Mais de 6x"]),
                "Recorrente": st.column_config.SelectboxColumn("Recorrente?", options=["Não", "Sim"]),
                # Não exibir "Vezes Recorrencia" e "Datas Parcelas Receita" diretamente aqui para simplicidade
            }
        )

        st.markdown("---")
        st.subheader("Ações na Tabela")
        
        # Botões um abaixo do outro
        if st.button("Salvar Alterações na Tabela", use_container_width=True):
            rows_updated = 0
            for index, edited_row in edited_df.iterrows():
                original_row = df_filtered[df_filtered['ID'] == edited_row['ID']].iloc[0]
                
                valor_original_db = original_row['Valor']
                # Garante que o valor salvo no DB seja sempre positivo, independentemente de como foi exibido na tabela
                valor_editado_db = abs(edited_row['Valor']) 

                changes = {}
                if edited_row['Descrição'] != original_row['Descrição']:
                    changes['descricao'] = edited_row['Descrição']
                if valor_editado_db != valor_original_db:
                    changes['valor'] = valor_editado_db
                if edited_row['Categoria'] != original_row['Categoria']:
                    changes['categoria'] = edited_row['Categoria']
                if edited_row['Status'] != original_row['Status']:
                    changes['status'] = edited_row['Status']
                if edited_row['Responsavel'] != original_row['Responsavel']:
                    changes['responsavel'] = edited_row['Responsavel']
                if edited_row['Banco'] != original_row['Banco']:
                    changes['banco'] = edited_row['Banco']
                if edited_row['Forma Recebimento'] != original_row['Forma Recebimento']:
                    changes['forma_recebimento'] = edited_row['Forma Recebimento']
                if edited_row['Recorrente'] != original_row['Recorrente']:
                    changes['recorrente'] = edited_row['Recorrente']
                
                if edited_row['Data'].strftime("%Y-%m-%d") != original_row['Data'].strftime("%Y-%m-%d"):
                    changes['data'] = edited_row['Data'].strftime("%Y-%m-%d")

                if changes:
                    if update_transaction(edited_row['ID'], current_username, **changes): # Chamada para a função global
                        rows_updated += 1
            
            if rows_updated > 0:
                st.success(f"{rows_updated} transação(ões) atualizada(s) com sucesso! 🎉")
                st.rerun()
            else:
                st.info("Nenhuma alteração detectada para salvar.")
        
        st.warning("Para deletar, selecione o ID da transação.")
        trans_to_delete = st.selectbox("Selecione o ID da transação para excluir", options=edited_df['ID'].tolist(), key="delete_id_select")
        if st.button("Excluir Transação Selecionada", use_container_width=True):
            if delete_transaction(trans_to_delete, current_username): # Chamada para a função global
                st.success(f"Transação ID {trans_to_delete} excluída com sucesso.")
                st.rerun()
            else:
                st.error("Erro ao excluir transação ou ID não encontrado.")
    else:
        st.info("Nenhuma transação correspondente aos filtros.")

def render_detailed_analysis_section(df_all_transactions):
    """Renderiza a seção de análises detalhadas com gráficos."""
    st.header("📈 Análises Detalhadas")

    if df_all_transactions.empty:
        st.info("Nenhuma transação para analisar ainda.")
        return

    st.markdown("---")
    st.subheader("Análise de Gastos por Categoria (Despesas Pagas)")
    despesas_pagas_df = df_all_transactions[(df_all_transactions['Tipo'] == 'despesa') & (df_all_transactions['Status'] == 'Pago')].copy()

    if not despesas_pagas_df.empty:
        gastos_por_categoria = despesas_pagas_df.groupby('Categoria')['Valor'].sum().sort_values(ascending=False)
        st.dataframe(gastos_por_categoria.reset_index().style.format({'Valor': "R$ {:,.2f}"}), use_container_width=True, hide_index=True)

        fig_pie = px.pie(gastos_por_categoria.reset_index(),
                         values='Valor',
                         names='Categoria',
                         title='Distribuição de Despesas Pagas por Categoria',
                         hole=0.3)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Nenhuma despesa paga para análise por categoria.")

    st.markdown("---")
    st.subheader("Receitas por Responsável e Banco")
    receitas_df = df_all_transactions[df_all_transactions['Tipo'] == 'receita'].copy()

    if not receitas_df.empty:
        col_resp_chart, col_bank_chart = st.columns(2)
        with col_resp_chart:
            receitas_por_responsavel = receitas_df.groupby('Responsavel')['Valor'].sum().sort_values(ascending=False)
            if not receitas_por_responsavel.empty:
                st.subheader("Receitas por Responsável")
                st.dataframe(receitas_por_responsavel.reset_index().style.format({'Valor': "R$ {:,.2f}"}), use_container_width=True, hide_index=True)
                fig_resp = px.bar(receitas_por_responsavel.reset_index(), x='Responsavel', y='Valor',
                                  title='Total de Receitas por Responsável',
                                  labels={'Responsavel': 'Responsável', 'Valor': 'Valor (R$)'},
                                  color='Responsavel')
                st.plotly_chart(fig_resp, use_container_width=True)
            else:
                st.info("Nenhuma receita registrada por responsável para análise.")

        with col_bank_chart:
            receitas_por_banco = receitas_df.groupby('Banco')['Valor'].sum().sort_values(ascending=False)
            if not receitas_por_banco.empty:
                st.subheader("Receitas por Banco")
                st.dataframe(receitas_por_banco.reset_index().style.format({'Valor': "R$ {:,.2f}"}), use_container_width=True, hide_index=True)
                fig_bank = px.bar(receitas_por_banco.reset_index(), x='Banco', y='Valor',
                                  title='Total de Receitas por Banco',
                                  labels={'Banco': 'Banco', 'Valor': 'Valor (R$)'},
                                  color='Banco')
                st.plotly_chart(fig_bank, use_container_width=True)
            else:
                st.info("Nenhuma receita registrada por banco para análise.")
    else:
        st.info("Nenhuma receita para analisar ainda.")

    st.markdown("---")
    st.subheader("Projeção de Fluxo de Caixa Futuro (Próximos 3 Meses)")
    # Inclui o mês atual + 3 futuros
    future_months = [datetime.now().date() + pd.DateOffset(months=i) for i in range(4)] 
    
    projection_data = {}
    for month_date in future_months:
        month_key = month_date.strftime("%Y-%m")
        projection_data[month_key] = {'Receitas': 0.0, 'Despesas': 0.0, 'Saldo': 0.0}

    current_date = datetime.now().date()

    for index, row in df_all_transactions.iterrows():
        trans_date = row['Data'].date()
        trans_month_key = trans_date.strftime("%Y-%m")

        if row['Tipo'] == 'receita':
            # Adiciona receita ao mês da transação
            if trans_month_key in projection_data:
                projection_data[trans_month_key]['Receitas'] += row['Valor']
            
            # Se for parcelada, adiciona às datas futuras
            if row['Forma Recebimento'] not in ["Parcela Única", "Mais de 6x"] and row['Datas Parcelas Receita']:
                parcel_dates = json.loads(row['Datas Parcelas Receita'])
                for p_date_str in parcel_dates:
                    p_date = datetime.strptime(p_date_str, "%Y-%m-%d").date()
                    p_month_key = p_date.strftime("%Y-%m")
                    # Se a parcela for para um mês futuro e estiver no nosso range de projeção
                    if p_month_key in projection_data and p_date > current_date:
                        # Divide o valor total pela quantidade de parcelas para cada ocorrência
                        projection_data[p_month_key]['Receitas'] += row['Valor'] / len(parcel_dates) 
                        
        elif row['Tipo'] == 'despesa':
            # Adiciona despesa ao mês da transação (seja 'A Pagar' ou 'Pago')
            if row['Status'] == 'A Pagar' and trans_month_key in projection_data:
                projection_data[trans_month_key]['Despesas'] += row['Valor']
            elif row['Status'] == 'Pago' and trans_date >= datetime.now().date().replace(day=1) and trans_month_key in projection_data:
                projection_data[trans_month_key]['Despesas'] += row['Valor']
            
            # Se for recorrente, projeta para os próximos meses
            if row['Recorrente'] == 'Sim' and row['Vezes Recorrencia'] > 1:
                for i in range(1, row['Vezes Recorrencia']): 
                    future_date = trans_date + pd.DateOffset(months=i).date()
                    future_month_key = future_date.strftime("%Y-%m")
                    if future_month_key in projection_data and future_date > current_date:
                        projection_data[future_month_key]['Despesas'] += row['Valor']

    # Calcular saldos
    for month_key in projection_data:
        projection_data[month_key]['Saldo'] = projection_data[month_key]['Receitas'] - projection_data[month_key]['Despesas']

    proj_df = pd.DataFrame.from_dict(projection_data, orient='index')
    proj_df.index.name = 'Mês'
    st.dataframe(proj_df.style.format({
        'Receitas': "R$ {:,.2f}", 
        'Despesas': "R$ {:,.2f}", 
        'Saldo': "R$ {:,.2f}"
    }), use_container_width=True)

    fig_proj = px.bar(proj_df.reset_index(), x='Mês', y=['Receitas', 'Despesas', 'Saldo'],
                      title='Projeção Mensal de Fluxo de Caixa',
                      barmode='group',
                      color_discrete_map={'Receitas': 'green', 'Despesas': 'red', 'Saldo': 'blue'})
    st.plotly_chart(fig_proj, use_container_width=True)

def render_planning_section(current_username):
    """Renderiza a seção de Planejamento."""
    st.header("🎯 Planejamento Financeiro")
    st.info("Esta seção permite que você defina e acompanhe suas metas financeiras.")
    
    st.markdown("---")
    st.subheader("Definir Nova Meta")
    with st.expander("Clique para expandir e definir uma nova meta"):
        meta_descricao = st.text_input("Descrição da Meta", placeholder="Ex: Comprar carro, Viagem, Reserva de Emergência")
        meta_valor = st.number_input("Valor da Meta (R$)", min_value=0.01, format="%.2f")
        
        # Categorias para as metas (podem ser as mesmas das despesas/receitas ou um subconjunto)
        categorias_metas = [
            "Viagem", "Carro", "Casa", "Educação", "Saúde", 
            "Investimento", "Reserva de Emergência", "Outros"
        ]
        meta_categoria = st.selectbox("Categoria da Meta", categorias_metas)
        
        meta_data_limite = st.date_input("Data Limite para Atingir a Meta", datetime.now().date() + timedelta(days=365))
        
        if st.button("Salvar Meta", key="save_goal_button"):
            if meta_descricao and meta_valor > 0:
                add_goal(current_username, meta_descricao, meta_valor, meta_categoria, meta_data_limite.strftime("%Y-%m-%d"))
                st.success(f"Meta '{meta_descricao}' de R$ {meta_valor:,.2f} definida até {meta_data_limite.strftime('%d/%m/%Y')} na categoria '{meta_categoria}'.")
                st.rerun()
            else:
                st.error("Por favor, preencha a descrição e um valor válido para a meta.")

    st.markdown("---")
    st.subheader("Suas Metas Atuais")
    goals = get_goals(current_username)
    if goals:
        goals_df = pd.DataFrame(goals, columns=['ID', 'Descrição', 'Valor Meta', 'Categoria', 'Data Limite', 'Valor Atual', 'Status'])
        goals_df['Progresso (%)'] = (goals_df['Valor Atual'] / goals_df['Valor Meta'] * 100).round(2)
        goals_df['Progresso (%)'] = goals_df['Progresso (%)'].clip(upper=100) # Limita a 100%
        
        st.dataframe(goals_df[['ID', 'Descrição', 'Valor Meta', 'Valor Atual', 'Progresso (%)', 'Data Limite', 'Status']].style.format({
            'Valor Meta': "R$ {:,.2f}",
            'Valor Atual': "R$ {:,.2f}",
            'Progresso (%)': "{:.2f}%"
        }), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Ações nas Metas")
        
        # Ações de metas uma abaixo da outra
        goals_in_progress = goals_df[goals_df['Status'] == 'Em Progresso']
        if not goals_in_progress.empty:
            goal_to_complete_id = st.selectbox("Marcar meta como Concluída (ID)", options=goals_in_progress['ID'].tolist(), key="complete_goal_id_select")
            if st.button("Marcar como Concluída", use_container_width=True):
                if mark_goal_as_completed(goal_to_complete_id, current_username):
                    st.success(f"Meta ID {goal_to_complete_id} marcada como Concluída! 🎉")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Erro ao marcar meta como concluída ou ID não encontrado.")
        else:
            st.info("Nenhuma meta em progresso para marcar como concluída.")

        st.warning("Para deletar uma meta, selecione o ID da meta.")
        goal_to_delete_id = st.selectbox("Selecione o ID da meta para excluir", options=goals_df['ID'].tolist(), key="delete_goal_id_select")
        if st.button("Excluir Meta Selecionada", use_container_width=True, key="delete_goal_button_final"):
            if delete_goal(goal_to_delete_id, current_username):
                st.success(f"Meta ID {goal_to_delete_id} excluída com sucesso.")
                st.rerun()
            else:
                st.error("Erro ao excluir meta ou ID não encontrado.")
    else:
        st.info("Nenhuma meta definida ainda.")


# --- Inicialização dos Bancos de Dados ---
init_user_db()
init_transactions_db()
init_goals_db() # Inicializa o banco de dados de metas

# --- Gerenciamento de Sessão (Login) ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = None

def login_page():
    """Exibe a tela de login e registro centralizada com abas e título centralizado."""
    
    # Centraliza o título usando HTML e markdown com unsafe_allow_html=True
    st.markdown("<h1 style='text-align: center;'>🔑 Bem-vindo(a) ao Finanças OPPI</h1>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1]) # Usar colunas para centralizar o conteúdo principal
    with col2:
        tab_login, tab_register = st.tabs(["Fazer Login", "Criar Nova Conta"])

        with tab_login:
            st.markdown("### Entre na sua conta")
            username = st.text_input("Nome de Usuário", key="login_username")
            password = st.text_input("Senha", type='password', key="login_password")

            if st.button("Entrar", key="login_button", use_container_width=True):
                if verify_user(username, password):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.success(f"Login bem-sucedido! Bem-vindo(a), {username} 🎉")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Nome de usuário ou senha incorretos.")

        with tab_register:
            st.markdown("### Crie uma nova conta")
            new_username = st.text_input("Escolha um Nome de Usuário", key="register_username")
            new_password = st.text_input("Escolha uma Senha", type='password', key="register_password")
            confirm_password = st.text_input("Confirme a Senha", type='password', key="confirm_password")

            if st.button("Registrar Nova Conta", key="register_button", use_container_width=True):
                if not new_username or not new_password or not confirm_password:
                    st.warning("Por favor, preencha todos os campos.")
                elif new_password != confirm_password:
                    st.warning("As senhas não coincidem.")
                elif add_user(new_username, new_password):
                    st.success("Conta criada com sucesso! Faça login na aba 'Fazer Login'.")
                    st.balloons()
                else:
                    st.warning("Nome de usuário já existe. Escolha outro.")

# --- Lógica Principal da Aplicação ---
if st.session_state['logged_in']:
    st.sidebar.title(f"Olá, {st.session_state['username']}!")
    
    # Menu lateral para as funcionalidades (substituindo as abas superiores)
    app_menu = ["📊 Visão Geral", "📝 Transações", "➕ Adicionar Lançamento", "📈 Análises Detalhadas", "🎯 Planejamento"]
    selected_option = st.sidebar.radio("Navegação", app_menu)

    current_username = st.session_state['username']
    all_transactions_data = get_transactions(current_username) # Carrega todas as transações uma vez
    
    # Converte para DataFrame aqui para ser usado por todas as seções
    if all_transactions_data:
        df_all_transactions = pd.DataFrame(all_transactions_data, columns=[
            'ID', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Responsavel', 'Banco',
            'Forma Recebimento', 'Datas Parcelas Receita', 'Recorrente', 'Vezes Recorrencia', 'Status'
        ])
        df_all_transactions['Data'] = pd.to_datetime(df_all_transactions['Data'])
    else:
        df_all_transactions = pd.DataFrame(columns=[
            'ID', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Responsavel', 'Banco',
            'Forma Recebimento', 'Datas Parcelas Receita', 'Recorrente', 'Vezes Recorrencia', 'Status'
        ])

    # Renderiza a seção selecionada
    if selected_option == "📊 Visão Geral":
        render_overview_dashboard(current_username, df_all_transactions)
    elif selected_option == "📝 Transações":
        render_transactions_table(current_username, df_all_transactions)
    elif selected_option == "➕ Adicionar Lançamento":
        render_unified_transaction_form(current_username)
    elif selected_option == "📈 Análises Detalhadas":
        render_detailed_analysis_section(df_all_transactions)
    elif selected_option == "🎯 Planejamento":
        render_planning_section(current_username) # Passa o username para a seção de planejamento

    st.sidebar.markdown("---")
    if st.sidebar.button("Sair", use_container_width=True):
        st.session_state['logged_in'] = False
        st.session_state['username'] = None
        st.info("Você foi desconectado(a).")
        st.rerun()
else:
    login_page()

st.markdown("---")
st.markdown("Desenvolvido com 💜 e Streamlit para o controle financeiro familiar.")