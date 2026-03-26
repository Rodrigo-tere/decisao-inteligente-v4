# Decisão Inteligente V5

Aplicativo em Streamlit para tomada de decisão com:
- checklist rápido
- checklist robusto
- banco histórico em SQLite
- análise de padrões
- revisão de resultado real
- exportação CSV/JSON
- login local
- confiança percebida separada da confiança calculada
- gap de confiança salvo no banco

## Requisitos
- Python 3.9 ou superior

## Instalação
```bash
pip install -r requirements.txt
```

## Execução
```bash
streamlit run app.py
```

## Login padrão
- usuário: `admin`
- senha: `admin123`

## O que mudou na V5
- a pessoa informa a **confiança percebida**
- o sistema calcula a **confiança calculada** com base na estrutura da decisão
- o app mostra o **gap de confiança**
- o painel e a aba de padrões mostram sinais de calibração
