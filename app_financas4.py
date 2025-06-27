import streamlit as st
import hashlib
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import json

# NOVO: Importações para Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Configurações da Página Streamlit (DEVE SER O PRIMEIRO COMANDO STREAMLIT) ---
st.set_page_config(
    page_title="Finanças da Família 💰",
    page_icon="💸",
    layout="wide"
)

# --- Configurações do Google Sheets ---
# ALERTA: Substitua estes nomes pelos nomes EXATOS da sua planilha e abas no Google Sheets.
# EX: Se sua planilha se chama "Meu Controle Financeiro", use GOOGLE_SHEET_NAME = "Meu Controle Financeiro"
GOOGLE_SHEET_NAME = "app_financas" # <<< VERIFIQUE E AJUSTE ESTE NOME PARA O DA SUA PLANILHA NO DRIVE
USERS_WORKSHEET_NAME = "users"
TRANSACTIONS_WORKSHEET_NAME = "transacoes"
GOALS_WORKSHEET_NAME = "goals" # Se você criou a aba de metas, caso contrário, comente esta linha e suas referências

# --- Conexão e Autenticação com Google Sheets (Usando st.secrets) ---
@st.cache_resource # Use st.cache_resource para evitar reconexões a cada rerun
def get_sheets_client():
    try:
        # st.secrets["gcp_service_account"] é a forma segura de acessar suas credenciais
        # que você configurará no painel do Streamlit Cloud (NÃO no GitHub!)
        creds_info = st.secrets["gcp_service_account"]
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        return spreadsheet
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets. Verifique suas credenciais e compartilhamento da planilha. Erro: {e}")
        st.stop() # Interrompe a execução se não conseguir conectar
        
spreadsheet = get_sheets_client()
users_sheet = spreadsheet.worksheet(USERS_WORKSHEET_NAME)
transactions_sheet = spreadsheet.worksheet(TRANSACTIONS_WORKSHEET_NAME)
goals_sheet = spreadsheet.worksheet(GOALS_WORKSHEET_NAME) # Certifique-se que esta aba existe na sua planilha!


# --- Funções de Ajuda para Segurança (Hashing) ---
def make_hashes(password):
    """Cria um hash SHA256 da senha para armazenamento seguro."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Verifica se a senha fornecida corresponde ao hash armazenado."""
    return make_hashes(password) == hashed_text

# --- Funções do Banco de Dados para Usuários (AGORA PARA GOOGLE SHEETS) ---
# init_user_db não é mais necessário da mesma forma, pois as abas são criadas manualmente.
# No entanto, vamos garantir que as planilhas existam ao tentar acessá-las no get_sheets_client.

def add_user(username, password):
    """Adiciona um novo usuário ao Google Sheet 'users'."""
    hashed_password = make_hashes(password)
    try:
        # Verifica se o usuário já existe antes de adicionar
        all_users = users_sheet.get_all_records()
        df_users = pd.DataFrame(all_users)
        if not df_users.empty and username in df_users['username'].values:
            return False # Usuário já existe
        
        users_sheet.append_row([username, hashed_password])
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar usuário ao Google Sheet: {e}")
        return False

def verify_user(username, password):
    """Verifica as credenciais do usuário no Google Sheet 'users'."""
    try:
        all_users = users_sheet.get_all_records()
        df_users = pd.DataFrame(all_users)
        
        if df_users.empty:
            return False # Ninguém cadastrado
        
        user_row = df_users[df_users['username'] == username]
        if not user_row.empty:
            hashed_password_db = user_row['password'].iloc[0]
            return check_hashes(password, hashed_password_db)
        return False
    except Exception as e:
        st.error(f"Erro ao verificar usuário no Google Sheet: {e}")
        return False

# --- Funções do Banco de Dados para Transações Financeiras (AGORA PARA GOOGLE SHEETS) ---
# init_transactions_db não é mais necessário.

def add_transaction(username, data, descricao, valor, tipo, categoria=None,
                    responsavel=None, banco=None, forma_recebimento=None, datas_parcelas_receita=None,
                    recorrente=None, vezes_recorrencia=None, status=None):
    """Adiciona uma nova transação ao Google Sheet 'transacoes'."""
    try:
        # Geração de ID simples: pega o último ID e incrementa
        # Isso pode não ser robusto para múltiplos usuários simultâneos em alta escala,
        # mas funciona para um app familiar.
        all_transactions = transactions_sheet.get_all_records()
        df_temp = pd.DataFrame(all_transactions)
        next_id = 1
        if not df_temp.empty and 'id' in df_temp.columns and pd.api.types.is_numeric_dtype(df_temp['id']):
            next_id = df_temp['id'].max() + 1
        
        row = [
            next_id,
            data,
            descricao,
            valor,
            tipo,
            categoria,
            username, # Salva o username para vincular a transação
            responsavel,
            banco,
            datas_parcelas_receita, # Já deve ser uma string JSON ou None
            recorrente,
            vezes_recorrencia,
            status
        ]
        transactions_sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar transação ao Google Sheet: {e}")
        st.exception(e) # Para debug
        return False

def get_transactions(username):
    """Recupera todas as transações de um usuário específico do Google Sheet 'transacoes'."""
    try:
        # Pega todos os registros e converte para DataFrame
        all_records = transactions_sheet.get_all_records()
        df = pd.DataFrame(all_records)
        
        if df.empty:
            return pd.DataFrame(columns=[
                'ID', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Username', 'Responsavel', 'Banco',
                'Forma Recebimento', 'Datas Parcelas Receita', 'Recorrente', 'Vezes Recorrencia', 'Status'
            ]) # Retorna DataFrame vazio com as colunas esperadas
        
        # Garante que as colunas tenham nomes amigáveis (ajustando de volta ao padrão do código)
        # É importante que os cabeçalhos na planilha sejam EXATOS aos nomes minúsculos aqui
        df.columns = [col.lower().replace(' ', '_') for col in df.columns]

        # Filtrar pelo username (coluna 'username' deve existir e ser preenchida na planilha)
        if 'username' in df.columns:
            df = df[df['username'] == username]
        else:
            st.warning("Coluna 'username' não encontrada na planilha 'transacoes'. A filtragem por usuário pode não funcionar corretamente.")
        
        # Converter tipos de dados, pois gspread lê tudo como string
        df['data'] = pd.to_datetime(df['data'], errors='coerce') # 'coerce' transforma em NaT se o formato for inválido
        df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
        df['vezes_recorrencia'] = pd.to_numeric(df['vezes_recorrencia'], errors='coerce').fillna(0).astype(int) # Preenche NaN com 0 para int

        # Renomear colunas para o formato que o resto do código espera (Capitalizado, com espaços)
        df.columns = [col.replace('_', ' ').title() for col in df.columns]

        return df
    except Exception as e:
        st.error(f"Erro ao obter transações do Google Sheet: {e}")
        st.exception(e) # Para debug
        return pd.DataFrame() # Retorna DataFrame vazio em caso de erro

def delete_transaction(transaction_id, username):
    """Exclui uma transação específica do Google Sheet 'transacoes'."""
    try:
        # gspread não tem delete por valor. Precisa encontrar o número da linha.
        # Ler todas as transações, encontrar o ID e deletar a linha.
        all_records = transactions_sheet.get_all_values() # Pega todos os valores como lista de listas
        
        # Encontra o índice da linha de cabeçalho
        header = all_records[0]
        try:
            id_col_idx = header.index('id') # Encontra o índice da coluna 'id' (minúsculo)
            user_col_idx = header.index('username') # Encontra o índice da coluna 'username'
        except ValueError:
            st.error("Colunas 'id' ou 'username' não encontradas na planilha 'transacoes'.")
            return False

        # Itera pelas linhas (começando da 1, pois 0 é o cabeçalho)
        # O número da linha na planilha é o índice na lista + 1
        row_to_delete_idx = -1
        for i, row in enumerate(all_records[1:]): 
            if i < len(all_records) - 1: # Garante que não está fora do limite
                current_id = None
                current_username_row = None
                try:
                    current_id = int(row[id_col_idx])
                    current_username_row = row[user_col_idx]
                except (ValueError, IndexError):
                    continue # Pula linhas com ID inválido ou fora do range

                if current_id == transaction_id and current_username_row == username:
                    row_to_delete_idx = i + 2 # +1 para pular cabeçalho, +1 para converter para índice baseado em 1 da planilha
                    break
        
        if row_to_delete_idx != -1:
            transactions_sheet.delete_rows(row_to_delete_idx)
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao excluir transação do Google Sheet: {e}")
        st.exception(e)
        return False

def update_transaction(transaction_id, username, **kwargs):
    """Atualiza uma transação específica no Google Sheet 'transacoes'."""
    try:
        all_records = transactions_sheet.get_all_values() # Pega todos os valores como lista de listas
        header = all_records[0] # Cabeçalhos
        
        # Mapeia nomes de colunas do Python para os nomes da planilha (minúsculas)
        col_map = {k.lower(): k for k in header} 

        row_index_in_sheet = -1 # Índice da linha na planilha (baseado em 1)
        update_cells = [] # Lista de (linha, coluna, novo_valor)

        # Encontra a linha da transação e prepara as atualizações
        for i, row_data in enumerate(all_records[1:]): # Começa do índice 1 para pular cabeçalho
            try:
                # Obtenha o ID e username da linha atual, usando o índice da coluna
                current_id_idx = header.index('id')
                current_username_idx = header.index('username')
                
                current_id = int(row_data[current_id_idx])
                current_username_row = row_data[current_username_idx]

                if current_id == transaction_id and current_username_row == username:
                    row_index_in_sheet = i + 2 # +1 para pular cabeçalho, +1 para converter para índice baseado em 1 da planilha
                    
                    # Para cada alteração solicitada, encontre a coluna e prepare a atualização
                    for key, value in kwargs.items():
                        col_name_in_sheet = key.lower() # Converte para minúscula para comparar com cabeçalho
                        if col_name_in_sheet in col_map: # Verifica se a coluna existe na planilha
                            col_index_in_sheet = header.index(col_name_in_sheet) + 1 # Coluna baseada em 1
                            update_cells.append({
                                'range': gspread.utils.rowcol_to_a1(row_index_in_sheet, col_index_in_sheet),
                                'values': [[value]]
                            })
                    break
            except (ValueError, IndexError) as e:
                # Isso pode acontecer se houver linhas mal formatadas ou vazias
                print(f"Skipping malformed row: {row_data}. Error: {e}")
                continue


        if row_index_in_sheet != -1 and update_cells:
            # st.error(f"Atualizando: {update_cells}") # Para debug
            transactions_sheet.batch_update(update_cells)
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao atualizar transação no Google Sheet: {e}")
        st.exception(e)
        return False


def get_summary_current_month(username):
    """Calcula o resumo de receitas e despesas para o mês atual para um usuário específico (Google Sheet)."""
    df = get_transactions(username) # Já retorna DataFrame filtrado e formatado
    if df.empty:
        return 0.0, 0.0, 0.0

    current_year_month = datetime.now().strftime("%Y-%m")
    
    # Certifica-se de que a coluna 'Data' é datetime e 'Tipo' e 'Status' são strings
    df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    df['Tipo'] = df['Tipo'].astype(str)
    df['Status'] = df['Status'].astype(str)

    # Filtrar pelo mês atual
    df_current_month = df[df['Data'].dt.strftime("%Y-%m") == current_year_month].copy()

    total_receitas = df_current_month[df_current_month['Tipo'].str.lower() == 'receita']['Valor'].sum()
    total_despesas_pagas = df_current_month[(df_current_month['Tipo'].str.lower() == 'despesa') & (df_current_month['Status'].str.lower() == 'pago')]['Valor'].sum()
    total_despesas_apagar = df_current_month[(df_current_month['Tipo'].str.lower() == 'despesa') & (df_current_month['Status'].str.lower() == 'a pagar')]['Valor'].sum()

    return float(total_receitas), float(total_despesas_pagas), float(total_despesas_apagar)

# --- Funções do Banco de Dados para Metas (AGORA PARA GOOGLE SHEETS) ---
# init_goals_db não é mais necessário.

def add_goal(username, descricao, valor_meta, categoria, data_limite):
    """Adiciona uma nova meta ao Google Sheet 'goals'."""
    try:
        all_goals = goals_sheet.get_all_records()
        df_temp = pd.DataFrame(all_goals)
        next_id = 1
        if not df_temp.empty and 'id' in df_temp.columns and pd.api.types.is_numeric_dtype(df_temp['id']):
            next_id = df_temp['id'].max() + 1
            
        row = [next_id, username, descricao, valor_meta, categoria, data_limite, 0.0, 'Em Progresso']
        goals_sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar meta ao Google Sheet: {e}")
        st.exception(e)
        return False

def get_goals(username):
    """Recupera todas as metas de um usuário específico do Google Sheet 'goals'."""
    try:
        all_records = goals_sheet.get_all_records()
        df = pd.DataFrame(all_records)

        if df.empty:
             return pd.DataFrame(columns=[
                'ID', 'Username', 'Descricao', 'Valor Meta', 'Categoria', 'Data Limite', 'Valor Atual', 'Status'
            ]) # Retorna DataFrame vazio com as colunas esperadas
        
        # Garante que as colunas tenham nomes amigáveis
        df.columns = [col.lower().replace(' ', '_') for col in df.columns]

        if 'username' in df.columns:
            df = df[df['username'] == username]
        else:
            st.warning("Coluna 'username' não encontrada na planilha 'goals'. Filtragem por usuário pode não funcionar.")

        # Converte tipos
        df['valor_meta'] = pd.to_numeric(df['valor_meta'], errors='coerce')
        df['valor_atual'] = pd.to_numeric(df['valor_atual'], errors='coerce')
        df['data_limite'] = pd.to_datetime(df['data_limite'], errors='coerce')

        # Renomear colunas para o formato que o resto do código espera (Capitalizado, com espaços)
        df.columns = [col.replace('_', ' ').title() for col in df.columns]

        return df
    except Exception as e:
        st.error(f"Erro ao obter metas do Google Sheet: {e}")
        st.exception(e)
        return pd.DataFrame()

def update_goal_progress(goal_id, username, amount):
    """Atualiza o progresso (valor_atual) de uma meta no Google Sheet 'goals'."""
    try:
        all_records = goals_sheet.get_all_values()
        header = all_records[0]
        
        id_col_idx = header.index('id')
        user_col_idx = header.index('username')
        valor_atual_col_idx = header.index('valor_atual')
        
        row_index_in_sheet = -1
        current_valor_atual = 0.0

        for i, row_data in enumerate(all_records[1:]):
            try:
                current_id = int(row_data[id_col_idx])
                current_username_row = row_data[user_col_idx]
                if current_id == goal_id and current_username_row == username:
                    row_index_in_sheet = i + 2 # Linha na planilha (baseado em 1)
                    current_valor_atual = float(row_data[valor_atual_col_idx])
                    break
            except (ValueError, IndexError):
                continue
        
        if row_index_in_sheet != -1:
            new_valor_atual = current_valor_atual + amount
            goals_sheet.update_cell(row_index_in_sheet, valor_atual_col_idx + 1, new_valor_atual) # Coluna baseada em 1
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao atualizar progresso da meta no Google Sheet: {e}")
        st.exception(e)
        return False

def mark_goal_as_completed(goal_id, username):
    """Marca uma meta como concluída e define valor_atual como valor_meta no Google Sheet 'goals'."""
    try:
        all_records = goals_sheet.get_all_values()
        header = all_records[0]
        
        id_col_idx = header.index('id')
        user_col_idx = header.index('username')
        valor_meta_col_idx = header.index('valor_meta')
        status_col_idx = header.index('status')
        valor_atual_col_idx = header.index('valor_atual') # Também precisa atualizar
        
        row_index_in_sheet = -1
        valor_meta_for_goal = 0.0

        for i, row_data in enumerate(all_records[1:]):
            try:
                current_id = int(row_data[id_col_idx])
                current_username_row = row_data[user_col_idx]
                if current_id == goal_id and current_username_row == username:
                    row_index_in_sheet = i + 2 # Linha na planilha (baseado em 1)
                    valor_meta_for_goal = float(row_data[valor_meta_col_idx])
                    break
            except (ValueError, IndexError):
                continue
        
        if row_index_in_sheet != -1:
            # Prepara as atualizações
            updates = [
                {'range': gspread.utils.rowcol_to_a1(row_index_in_sheet, status_col_idx + 1), 'values': [["Concluída"]]},
                {'range': gspread.utils.rowcol_to_a1(row_index_in_sheet, valor_atual_col_idx + 1), 'values': [[valor_meta_for_goal]]}
            ]
            goals_sheet.batch_update(updates)
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao marcar meta como concluída no Google Sheet: {e}")
        st.exception(e)
        return False

def delete_goal(goal_id, username):
    """Exclui uma meta específica do Google Sheet 'goals'."""
    try:
        all_records = goals_sheet.get_all_values()
        header = all_records[0]
        
        id_col_idx = header.index('id')
        user_col_idx = header.index('username')
        
        row_to_delete_idx = -1
        for i, row in enumerate(all_records[1:]):
            try:
                current_id = int(row[id_col_idx])
                current_username_row = row[user_col_idx]
                if current_id == goal_id and current_username_row == username:
                    row_to_delete_idx = i + 2
                    break
            except (ValueError, IndexError):
                continue

        if row_to_delete_idx != -1:
            goals_sheet.delete_rows(row_to_delete_idx)
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao excluir meta do Google Sheet: {e}")
        st.exception(e)
        return False

# Funções para gerenciar Nomes e Bancos (AGORA PARA GOOGLE SHEETS)
def get_unique_responsibles(username):
    """Obtém todos os responsáveis únicos para um usuário do Google Sheet 'transacoes'."""
    df = get_transactions(username)
    if df.empty or 'Responsavel' not in df.columns:
        return []
    # Usar .dropna().unique().tolist() para evitar valores nulos e obter uma lista
    return df['Responsavel'].dropna().unique().tolist()

def get_unique_banks(username):
    """Obtém todos os bancos únicos para um usuário do Google Sheet 'transacoes'."""
    df = get_transactions(username)
    if df.empty or 'Banco' not in df.columns:
        return []
    return df['Banco'].dropna().unique().tolist()


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
    goals_df = get_goals(current_username) # Get goals returns a DataFrame now
    if not goals_df.empty: # Check if DataFrame is not empty
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
                      color_discrete_map={'Receitas': 'green', 'Despesa': 'red', 'Saldo': 'blue'})
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
    goals_df = get_goals(current_username) # Get goals returns a DataFrame now
    if not goals_df.empty: # Check if DataFrame is not empty
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


# --- Inicialização dos Bancos de Dados (REMOVIDAS POIS AGORA USA GOOGLE SHEETS) ---
# init_user_db()
# init_transactions_db()
# init_goals_db()

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
    # A função get_transactions já foi adaptada para o Google Sheets
    df_all_transactions = get_transactions(current_username) 
    
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