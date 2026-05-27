# Decisão Inteligente Cloud

Versão preparada para publicar no Streamlit Community Cloud com persistência no Supabase.

## Objetivo

Permitir que qualquer pessoa autorizada teste o aplicativo pelo celular, fora da rede da fábrica, sem depender de um computador ligado.

## Arquivos principais

- `app.py`: aplicativo Streamlit
- `db.py`: camada de persistência SQLite/Supabase
- `requirements.txt`: dependências para deploy
- `supabase_schema.sql`: tabelas necessárias no Supabase
- `.streamlit/config.toml`: configuração visual/servidor
- `.streamlit/secrets.example.toml`: modelo dos secrets

## Deploy resumido

1. Subir esta pasta para um repositório GitHub.
2. Criar ou abrir um projeto no Supabase.
3. Rodar o conteúdo de `supabase_schema.sql` no SQL Editor do Supabase.
4. No Streamlit Community Cloud, criar um app apontando para:

```text
app.py
```

5. Configurar os secrets no Streamlit:

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA_ANON_KEY"
```

6. Compartilhar o link `https://...streamlit.app`.

## Rodar localmente

```powershell
cd "C:\Users\rodri\OneDrive\Importações\Nuvem\Sistema_Decisao_inteligente\decisao_app_v8_cloud"
python -m streamlit run app.py
```

## Login inicial

O sistema cria automaticamente o usuário padrão se ele ainda não existir:

- usuário: `admin`
- senha: `admin123`

Depois do primeiro acesso, crie um usuário próprio e altere/remova o uso do admin padrão para testes externos.
