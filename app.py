from datetime import datetime, timedelta

import streamlit as st

from db import (
    init_db,
    migrate_db,
    seed_default_user,
    verify_login,
    create_user,
    update_password,
    insert_decision,
    list_decisions_df,
    get_decision,
    update_outcome,
    get_summary_stats,
    get_pattern_summary,
    get_monthly_summary,
    get_bias_breakdown,
    get_recommendation_breakdown,
    get_category_quality_summary,
    export_decisions_df,
    get_confidence_gap_summary,
)

st.set_page_config(page_title="Decisão Inteligente V5", page_icon="🧠", layout="wide")
init_db()
migrate_db()
seed_default_user()

CSS = """
<style>
.block-container {padding-top:1rem; padding-bottom:1rem; max-width:1200px;}
.hero {background: linear-gradient(135deg, #0f172a 0%, #111827 45%, #1d4ed8 100%); color:white; padding:1.2rem; border-radius:24px; margin-bottom:1rem; box-shadow:0 12px 30px rgba(15,23,42,.18);}
.hero h1 {margin:0 0 .3rem 0; font-size:2rem; line-height:1.1;}
.hero p {margin:0; opacity:.95;}
.card, .soft-card, .metric-card {background:#fff; border:1px solid #e5e7eb; border-radius:20px; padding:1rem; box-shadow:0 4px 18px rgba(15,23,42,.05); margin-bottom:.8rem;}
.metric-label {font-size:.9rem; color:#64748b; margin-bottom:.3rem;}
.metric-value {font-size:1.8rem; font-weight:800; color:#0f172a;}
.metric-sub {font-size:.82rem; color:#64748b;}
.pill {display:inline-block; padding:.2rem .65rem; border-radius:999px; background:#eff6ff; color:#1d4ed8; font-weight:700; font-size:.76rem; margin-right:.35rem; margin-bottom:.2rem;}
.ok, .warn, .stop {border-radius:16px; padding:.9rem 1rem; font-weight:700; margin:.4rem 0 .8rem 0;}
.ok {background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0;}
.warn {background:#fffbeb; color:#92400e; border:1px solid #fde68a;}
.stop {background:#fef2f2; color:#991b1b; border:1px solid #fecaca;}
.step-title {font-size:1rem; font-weight:800; color:#0f172a; margin-bottom:.3rem;}
.subtle {color:#64748b; font-size:.88rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None
if "quick_result" not in st.session_state:
    st.session_state.quick_result = None
if "robust_result" not in st.session_state:
    st.session_state.robust_result = None


def recommendation_from_score(score):
    if score >= 80:
        return "✅ Seguir", "ok", "Os sinais estão favoráveis. Siga com disciplina e monitore a execução."
    if score >= 62:
        return "🧪 Testar pequeno", "warn", "A ideia pode ser boa, mas o ideal é validar em escala menor primeiro."
    if score >= 45:
        return "⚠️ Reavaliar", "warn", "Ainda há fragilidades relevantes. Colete mais dados e refine a decisão."
    return "🛑 Pausar", "stop", "O cenário está vulnerável. Melhor evitar, adiar ou reformular antes de agir."


def system_confidence_from_score(score):
    return round(max(1.0, min(10.0, score / 10.0)), 1)


def confidence_gap_label(user_confidence, system_confidence):
    gap = round(float(user_confidence) - float(system_confidence), 1)
    if gap >= 2.0:
        return gap, "⚠️ Possível excesso de confiança", "warn", "Sua confiança percebida está acima do que a estrutura da decisão sugere."
    if gap <= -2.0:
        return gap, "🧊 Possível subconfiança", "warn", "Você está menos confiante do que os sinais objetivos sugerem."
    return gap, "✅ Confiança calibrada", "ok", "Sua percepção está relativamente alinhada com a leitura do sistema."


def quick_scoring(data):
    score = 100
    penalties = []
    emo_map = {"Alta": 20, "Média": 8, "Baixa": 0}
    risk_map = {"Alto": 20, "Médio": 8, "Baixo": 0}
    score -= emo_map.get(data["emotion"], 0)
    if emo_map.get(data["emotion"], 0):
        penalties.append("Emoção elevada no momento")
    if data["data"] == "Não":
        score -= 20
        penalties.append("Sem base suficiente em dados")
    score -= risk_map.get(data["risk"], 0)
    if risk_map.get(data["risk"], 0):
        penalties.append("Risco relevante")
    if data["cost_opportunity"] == "Não":
        score -= 12
        penalties.append("Custo de oportunidade não foi avaliado")
    if data["worst_case"] == "Não":
        score -= 12
        penalties.append("Pior cenário não foi considerado")
    if data["bias_alert"] == "Sim":
        score -= 14
        penalties.append("Há indícios de viés influenciando a decisão")
    if data["alignment"] == "Não":
        score -= 10
        penalties.append("Decisão desalinhada com objetivos")
    if data["reversible"] == "Sim":
        score += 4
    if data["small_test"] == "Sim":
        score += 4
    return max(0, min(100, score)), penalties


def robust_scoring(data):
    score = 100
    penalties = []
    bias_names = []
    if data["emotion_level"] >= 8:
        score -= 18; penalties.append("Emoção muito alta")
    elif data["emotion_level"] >= 5:
        score -= 8; penalties.append("Emoção moderada")
    if data["urgency_level"] >= 8:
        score -= 12; penalties.append("Urgência excessiva")
    elif data["urgency_level"] >= 6:
        score -= 6; penalties.append("Pressa relevante")
    if not data["has_data"]:
        score -= 18; penalties.append("Decisão sem base robusta em dados")
    if data["clarity_level"] <= 4:
        score -= 14; penalties.append("Problema mal definido")
    elif data["clarity_level"] <= 6:
        score -= 6; penalties.append("Clareza parcial")
    if data["opportunity_cost_level"] <= 3:
        score -= 12; penalties.append("Custo de oportunidade pouco explorado")
    elif data["opportunity_cost_level"] <= 6:
        score -= 5; penalties.append("Custo de oportunidade parcialmente analisado")
    if data["downside_tolerance"] <= 4:
        score -= 12; penalties.append("Baixa tolerância ao pior cenário")
    elif data["downside_tolerance"] <= 6:
        score -= 5; penalties.append("Tolerância ao risco moderada")
    if data["goal_alignment"] <= 4:
        score -= 12; penalties.append("Baixo alinhamento com objetivos de longo prazo")
    elif data["goal_alignment"] <= 6:
        score -= 5; penalties.append("Alinhamento apenas parcial com objetivos")
    if len(data["alternatives"].strip()) < 15:
        score -= 8; penalties.append("Alternativas pouco analisadas")
    if len(data["worst_case"].strip()) < 15:
        score -= 8; penalties.append("Pior cenário pouco explorado")
    if len(data["inversion_plan"].strip()) < 15:
        score -= 8; penalties.append("Inversão pouco explorada")
    fields = [
        ("bias_confirmation", "Viés de confirmação"),
        ("bias_herd", "Efeito manada"),
        ("bias_loss", "Aversão à perda"),
        ("bias_ego", "Ego/excesso de confiança"),
        ("bias_anchor", "Ancoragem"),
    ]
    active = 0
    for field, label in fields:
        if data[field]:
            active += 1
            bias_names.append(label)
    if active >= 3:
        score -= 20; penalties.append("Vários vieses ativos")
    elif active == 2:
        score -= 12; penalties.append("Dois vieses relevantes")
    elif active == 1:
        score -= 6; penalties.append("Um viés relevante")
    if data["reversible"]:
        score += 4
    if data["test_small"]:
        score += 4
    if data["trusted_peer_review"]:
        score += 3
    return max(0, min(100, score)), penalties, bias_names


def show_result_box(score, recommendation, css_class, summary, penalties, confidence=None):
    st.markdown(f'<div class="{css_class}">{recommendation} · Score {score}/100<br><span style="font-weight:500">{summary}</span></div>', unsafe_allow_html=True)
    if confidence:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="soft-card"><div class="step-title">Confiança percebida</div><div style="font-size:1.5rem;font-weight:800">{confidence["user_confidence"]}/10</div><div class="subtle">Percepção subjetiva da pessoa.</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="soft-card"><div class="step-title">Confiança calculada</div><div style="font-size:1.5rem;font-weight:800">{confidence["system_confidence"]}/10</div><div class="subtle">Estimativa baseada na estrutura da decisão.</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="{confidence["gap_class"]}">{confidence["gap_title"]} · Gap {confidence["gap"]}<br><span style="font-weight:500">{confidence["gap_summary"]}</span></div>', unsafe_allow_html=True)
    if penalties:
        st.markdown("**Pontos de atenção**")
        for p in penalties:
            st.write("•", p)
    else:
        st.success("Nenhum alerta principal identificado.")


def login_screen():
    st.markdown('<div class="hero"><h1>🧠 Decisão Inteligente V5</h1><p>Checklist profissional para decisões do dia a dia e decisões estratégicas, com confiança percebida x confiança calculada.</p></div>', unsafe_allow_html=True)
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown('<div class="card"><span class="pill">Mobile First</span><span class="pill">Banco de decisões</span><span class="pill">Calibração</span><h4 style="margin-top:.65rem;">O que esta versão entrega</h4><ul><li>Versão rápida</li><li>Versão robusta</li><li>Histórico e revisão</li><li>Análise de padrões</li><li>Gap de confiança</li></ul></div>', unsafe_allow_html=True)
    with right:
        tab1, tab2 = st.tabs(["Entrar", "Criar usuário"])
        with tab1:
            with st.form("login_form"):
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                submitted = st.form_submit_button("Entrar", use_container_width=True)
            if submitted:
                user = verify_login(username, password)
                if user:
                    st.session_state.user = user
                    st.success("Login realizado com sucesso.")
                    st.rerun()
                st.error("Usuário ou senha inválidos.")
            st.caption("Usuário padrão: admin | Senha: admin123")
        with tab2:
            with st.form("register_form"):
                new_user = st.text_input("Novo usuário")
                new_pass = st.text_input("Nova senha", type="password")
                confirm_pass = st.text_input("Confirmar senha", type="password")
                add_btn = st.form_submit_button("Criar usuário", use_container_width=True)
            if add_btn:
                if not new_user or not new_pass:
                    st.warning("Preencha usuário e senha.")
                elif new_pass != confirm_pass:
                    st.warning("As senhas não conferem.")
                else:
                    ok, msg = create_user(new_user, new_pass)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)


def sidebar_top():
    with st.sidebar:
        st.markdown("## 🧠 Decisão V5")
        st.caption("Seu copiloto para decisões melhores")
        st.success(f'Conectado como **{st.session_state.user["username"]}**')
        page = st.radio("Navegação", ["🏠 Painel", "⚡ Checklist Rápido", "🧠 Checklist Robusto", "🗂️ Histórico", "🔍 Padrões", "⚙️ Conta"], label_visibility="collapsed")
        st.divider()
        st.caption("Dica: no celular, adicione o link à tela inicial depois do deploy.")
        if st.button("Sair", use_container_width=True):
            st.session_state.user = None
            st.session_state.quick_result = None
            st.session_state.robust_result = None
            st.rerun()
    return page


def dashboard_page(user_id):
    stats = get_summary_stats(user_id)
    monthly = get_monthly_summary(user_id)
    rec_df = get_recommendation_breakdown(user_id)
    category_df = get_category_quality_summary(user_id)
    conf_gap = get_confidence_gap_summary(user_id)
    st.markdown('<div class="hero"><h1>Painel de decisão</h1><p>Veja volume, qualidade percebida, revisões e calibração da confiança.</p></div>', unsafe_allow_html=True)
    cards = [
        ("Total de decisões", int(stats["total"]), "Base histórica acumulada"),
        ("Score médio", round(stats["avg_score"], 1), "Qualidade média do raciocínio antes de agir"),
        ("Revisadas", int(stats["reviewed"]), "Decisões com resultado real registrado"),
        ("Qualidade real média", round(stats["avg_quality"], 1), "Média das revisões feitas depois"),
        ("Gap médio de confiança", round(conf_gap.get("avg_gap_abs", 0), 1), "Diferença média entre percepção e sistema"),
    ]
    cols = st.columns(5, gap="small")
    for col, item in zip(cols, cards):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{item[0]}</div><div class="metric-value">{item[1]}</div><div class="metric-sub">{item[2]}</div></div>', unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.markdown('<div class="card"><div class="step-title">Evolução mensal</div><div class="subtle">Quantidade de decisões registradas por mês.</div></div>', unsafe_allow_html=True)
        if monthly.empty:
            st.info("Ainda não há dados suficientes para exibir a evolução mensal.")
        else:
            st.line_chart(monthly.set_index("ano_mes")["quantidade"], height=280)
    with right:
        st.markdown('<div class="card"><div class="step-title">Recomendações emitidas</div><div class="subtle">Distribuição das orientações finais do sistema.</div></div>', unsafe_allow_html=True)
        if rec_df.empty:
            st.info("Sem recomendações registradas ainda.")
        else:
            st.bar_chart(rec_df.set_index("recommendation")["total"], height=280)
    if not category_df.empty:
        best = category_df.sort_values(["avg_quality", "total"], ascending=[False, False]).iloc[0]
        worst = category_df.sort_values(["avg_quality", "total"], ascending=[True, False]).iloc[0]
        st.markdown(f'<div class="soft-card"><div class="step-title">Insight inicial</div><p style="margin:.2rem 0 .4rem 0;"><b>Melhor categoria revisada:</b> {best["category"]} ({best["avg_quality"]:.1f}/10)</p><p style="margin:.2rem 0;"><b>Categoria mais frágil:</b> {worst["category"]} ({worst["avg_quality"]:.1f}/10)</p></div>', unsafe_allow_html=True)


def quick_page(user_id):
    st.markdown('<div class="hero"><h1>Checklist rápido</h1><p>Uso imediato para momentos de pressão, resposta rápida e decisões pequenas ou médias.</p></div>', unsafe_allow_html=True)
    with st.form("quick_form"):
        st.markdown("### Contexto")
        title = st.text_input("Título da decisão")
        category = st.selectbox("Categoria", ["Pessoal", "Trabalho", "Financeiro", "Cliente", "Operação", "Investimento", "Outro"])
        decision_text = st.text_area("Qual decisão você precisa tomar agora?", height=100)
        notes = st.text_area("Observações opcionais", height=80)
        st.markdown("### Radar rápido")
        col1, col2 = st.columns(2)
        with col1:
            emotion = st.radio("Como está sua emoção agora?", ["Baixa", "Média", "Alta"], horizontal=True)
            data = st.radio("Você tem dados suficientes?", ["Sim", "Não"], horizontal=True)
            risk = st.radio("Qual o nível de risco?", ["Baixo", "Médio", "Alto"], horizontal=True)
            alignment = st.radio("Está alinhado com seus objetivos?", ["Sim", "Não"], horizontal=True)
        with col2:
            cost_opportunity = st.radio("Você avaliou o custo de oportunidade?", ["Sim", "Não"], horizontal=True)
            worst_case = st.radio("Você considerou o pior cenário?", ["Sim", "Não"], horizontal=True)
            bias_alert = st.radio("Percebe algum viés ou apego?", ["Não", "Sim"], horizontal=True)
            reversible = st.radio("É reversível?", ["Não", "Sim"], horizontal=True)
            small_test = st.radio("Dá para testar pequeno?", ["Não", "Sim"], horizontal=True)
            confidence = st.slider("Qual sua confiança percebida nessa decisão?", 1, 10, 6, help="Essa é a sua sensação subjetiva. O sistema também calculará uma confiança objetiva com base nas respostas.")
        submit = st.form_submit_button("Gerar recomendação", use_container_width=True)
    if submit:
        if not title.strip() or not decision_text.strip():
            st.warning("Preencha ao menos o título e a descrição da decisão.")
        else:
            inputs = {"emotion": emotion, "data": data, "risk": risk, "alignment": alignment, "cost_opportunity": cost_opportunity, "worst_case": worst_case, "bias_alert": bias_alert, "reversible": reversible, "small_test": small_test, "confidence": confidence}
            score, penalties = quick_scoring(inputs)
            recommendation, css_class, summary = recommendation_from_score(score)
            system_conf = system_confidence_from_score(score)
            gap, gap_title, gap_class, gap_summary = confidence_gap_label(confidence, system_conf)
            st.session_state.quick_result = {
                "title": title, "category": category, "decision_text": decision_text, "notes": notes, "inputs": inputs,
                "score": score, "recommendation": recommendation, "css_class": css_class, "summary": summary,
                "penalties": penalties,
                "confidence": {"user_confidence": confidence, "system_confidence": system_conf, "gap": gap, "gap_title": gap_title, "gap_class": gap_class, "gap_summary": gap_summary},
            }
    result = st.session_state.quick_result
    if result:
        st.markdown("### Resultado")
        show_result_box(result["score"], result["recommendation"], result["css_class"], result["summary"], result["penalties"], confidence=result.get("confidence"))
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Salvar no banco de decisões", use_container_width=True, key="save_quick"):
                insert_decision(user_id, "rápido", result["title"], result["category"], result["decision_text"], result["score"], result["recommendation"], result["inputs"], result["penalties"], result["notes"], "", (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), result["confidence"]["user_confidence"], result["confidence"]["system_confidence"], result["confidence"]["gap"])
                st.success("Decisão rápida salva com sucesso.")
        with c2:
            if st.button("Limpar resultado", use_container_width=True, key="clear_quick"):
                st.session_state.quick_result = None
                st.rerun()


def robust_page(user_id):
    st.markdown('<div class="hero"><h1>Checklist robusto</h1><p>Para decisões estratégicas, com blocos de raciocínio mais profundos.</p></div>', unsafe_allow_html=True)
    with st.form("robust_form"):
        st.markdown("### Etapa 1 · Contexto")
        title = st.text_input("Título da decisão")
        category = st.selectbox("Categoria", ["Pessoal", "Trabalho", "Financeiro", "Cliente", "Operação", "Investimento", "Estratégia", "Outro"])
        decision_text = st.text_area("Defina com clareza qual decisão precisa ser tomada", height=100)
        tags = st.text_input("Tags (separadas por vírgula)")
        notes = st.text_area("Contexto adicional", height=90)
        st.markdown("### Etapa 2 · Qualidade do raciocínio")
        col1, col2 = st.columns(2)
        with col1:
            emotion_level = st.slider("Nível de emoção", 1, 10, 4)
            urgency_level = st.slider("Nível de urgência", 1, 10, 5)
            clarity_level = st.slider("Quão claro está o problema?", 1, 10, 7)
            opportunity_cost_level = st.slider("Quanto você analisou o custo de oportunidade?", 1, 10, 6)
        with col2:
            downside_tolerance = st.slider("Sua tolerância ao pior cenário", 1, 10, 6)
            goal_alignment = st.slider("Alinhamento com seus objetivos de longo prazo", 1, 10, 7)
            confidence = st.slider("Sua confiança percebida", 1, 10, 6, help="Essa é sua percepção subjetiva. O sistema calculará separadamente uma confiança objetiva.")
            review_days = st.slider("Revisar esta decisão em quantos dias?", 1, 60, 14)
        has_data = st.checkbox("Tenho dados suficientes para sustentar a decisão")
        reversible = st.checkbox("A decisão é reversível")
        test_small = st.checkbox("Posso testar pequeno antes de escalar")
        trusted_peer_review = st.checkbox("Já considerei discutir com alguém confiável")
        st.markdown("### Etapa 3 · Exploração")
        alternatives = st.text_area("Quais alternativas reais existem?", height=90)
        worst_case = st.text_area("Descreva o pior cenário com honestidade", height=90)
        inversion_plan = st.text_area("Se você quisesse fazer isso dar errado, o que aconteceria?", height=90)
        st.markdown("### Etapa 4 · Radar de vieses")
        b1, b2, b3 = st.columns(3)
        with b1:
            bias_confirmation = st.checkbox("Viés de confirmação")
            bias_herd = st.checkbox("Efeito manada")
        with b2:
            bias_loss = st.checkbox("Aversão à perda")
            bias_anchor = st.checkbox("Ancoragem")
        with b3:
            bias_ego = st.checkbox("Ego / excesso de confiança")
        submit = st.form_submit_button("Gerar recomendação robusta", use_container_width=True)
    if submit:
        if not title.strip() or not decision_text.strip():
            st.warning("Preencha ao menos o título e a descrição da decisão.")
        else:
            inputs = {
                "emotion_level": emotion_level, "urgency_level": urgency_level, "clarity_level": clarity_level,
                "opportunity_cost_level": opportunity_cost_level, "downside_tolerance": downside_tolerance,
                "goal_alignment": goal_alignment, "confidence": confidence, "review_days": review_days,
                "has_data": has_data, "reversible": reversible, "test_small": test_small, "trusted_peer_review": trusted_peer_review,
                "alternatives": alternatives, "worst_case": worst_case, "inversion_plan": inversion_plan,
                "bias_confirmation": bias_confirmation, "bias_herd": bias_herd, "bias_loss": bias_loss,
                "bias_anchor": bias_anchor, "bias_ego": bias_ego,
            }
            score, penalties, bias_names = robust_scoring(inputs)
            recommendation, css_class, summary = recommendation_from_score(score)
            system_conf = system_confidence_from_score(score)
            gap, gap_title, gap_class, gap_summary = confidence_gap_label(confidence, system_conf)
            st.session_state.robust_result = {
                "title": title, "category": category, "decision_text": decision_text, "notes": notes, "tags": tags, "inputs": inputs,
                "score": score, "recommendation": recommendation, "css_class": css_class, "summary": summary,
                "penalties": penalties, "bias_names": bias_names, "review_due_at": (datetime.now() + timedelta(days=review_days)).strftime("%Y-%m-%d"),
                "confidence": {"user_confidence": confidence, "system_confidence": system_conf, "gap": gap, "gap_title": gap_title, "gap_class": gap_class, "gap_summary": gap_summary},
            }
    result = st.session_state.robust_result
    if result:
        st.markdown("### Resultado")
        show_result_box(result["score"], result["recommendation"], result["css_class"], result["summary"], result["penalties"], confidence=result.get("confidence"))
        if result["bias_names"]:
            st.info("Vieses identificados: " + ", ".join(result["bias_names"]))
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Salvar análise robusta", use_container_width=True, key="save_robust"):
                insert_decision(user_id, "robusto", result["title"], result["category"], result["decision_text"], result["score"], result["recommendation"], result["inputs"], result["penalties"], result["notes"], result["tags"], result["review_due_at"], result["confidence"]["user_confidence"], result["confidence"]["system_confidence"], result["confidence"]["gap"])
                st.success("Decisão robusta salva com sucesso.")
        with c2:
            if st.button("Limpar resultado", use_container_width=True, key="clear_robust"):
                st.session_state.robust_result = None
                st.rerun()


def history_page(user_id):
    st.markdown('<div class="hero"><h1>Histórico</h1><p>Consulte decisões anteriores, filtre, revise o resultado real e exporte seus dados.</p></div>', unsafe_allow_html=True)
    df = list_decisions_df(user_id)
    if df.empty:
        st.info("Ainda não há decisões salvas.")
        return
    with st.expander("Filtros e exportação", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            mode_filter = st.multiselect("Modo", sorted(df["mode"].dropna().unique().tolist()), default=sorted(df["mode"].dropna().unique().tolist()))
        with c2:
            category_filter = st.multiselect("Categoria", sorted(df["category"].dropna().unique().tolist()), default=sorted(df["category"].dropna().unique().tolist()))
        with c3:
            rec_filter = st.multiselect("Recomendação", sorted(df["recommendation"].dropna().unique().tolist()), default=sorted(df["recommendation"].dropna().unique().tolist()))
        search_text = st.text_input("Buscar por título, decisão ou tags")
        only_due = st.checkbox("Mostrar apenas revisões vencidas ou de hoje")
        export_df = export_decisions_df(user_id)
        st.download_button("Baixar CSV", data=export_df.to_csv(index=False).encode("utf-8-sig"), file_name="decisoes_v5.csv", mime="text/csv", use_container_width=True)
        st.download_button("Baixar JSON", data=export_df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8"), file_name="decisoes_v5.json", mime="application/json", use_container_width=True)
    filtered = df.copy()
    filtered = filtered[filtered["mode"].isin(mode_filter)]
    filtered = filtered[filtered["category"].isin(category_filter)]
    filtered = filtered[filtered["recommendation"].isin(rec_filter)]
    if search_text.strip():
        s = search_text.strip().lower()
        filtered = filtered[filtered["title"].str.lower().str.contains(s, na=False) | filtered["decision_text"].str.lower().str.contains(s, na=False) | filtered["tags"].fillna("").str.lower().str.contains(s, na=False)]
    if only_due:
        today = datetime.now().strftime("%Y-%m-%d")
        filtered = filtered[(filtered["review_due_at"].fillna("") <= today) & (filtered["review_due_at"].fillna("") != "")]
    st.dataframe(filtered[["id", "created_at", "mode", "title", "category", "score", "recommendation", "confidence_user", "confidence_system", "confidence_gap", "review_due_at", "outcome_status", "outcome_quality"]], use_container_width=True, hide_index=True)
    if filtered.empty:
        st.warning("Nenhum registro encontrado com os filtros atuais.")
        return
    selected_id = st.selectbox("Selecionar decisão para detalhe e revisão", filtered["id"].tolist())
    item = get_decision(int(selected_id))
    st.markdown(f'<div class="soft-card"><p style="margin:0 0 .35rem 0;"><b>{item["title"]}</b> · <span class="pill">{item["mode"]}</span> <span class="pill">{item["category"]}</span></p><p style="margin:0 0 .35rem 0;"><b>Score:</b> {item["score"]} | <b>Recomendação:</b> {item["recommendation"]}</p><p style="margin:0 0 .35rem 0;"><b>Confiança percebida:</b> {item.get("confidence_user") if item.get("confidence_user") is not None else "-"} / 10 | <b>Confiança calculada:</b> {item.get("confidence_system") if item.get("confidence_system") is not None else "-"} / 10 | <b>Gap:</b> {item.get("confidence_gap") if item.get("confidence_gap") is not None else "-"}</p><p style="margin:0 0 .35rem 0;"><b>Revisar até:</b> {item.get("review_due_at") or "-"}</p><p style="margin:0;"><b>Decisão:</b> {item["decision_text"]}</p></div>', unsafe_allow_html=True)
    with st.expander("Ver entradas e pontos de atenção"):
        st.json(item["inputs"])
        st.write("Pontos de atenção:", item["penalties"])
    with st.form("review_form"):
        options = ["Sem avaliação", "Deu certo", "Parcial", "Deu errado"]
        current = item.get("outcome_status") if item.get("outcome_status") in options else "Sem avaliação"
        status = st.selectbox("Resultado real", options, index=options.index(current))
        quality = st.slider("Qualidade da decisão na prática", 1, 10, int(item["outcome_quality"]) if item.get("outcome_quality") else 7)
        outcome_notes = st.text_area("O que aconteceu na prática?", value=item.get("outcome_notes") or "", height=100)
        save_review = st.form_submit_button("Salvar revisão", use_container_width=True)
    if save_review:
        update_outcome(item["id"], status, quality, outcome_notes)
        st.success("Revisão salva com sucesso.")
        st.rerun()


def patterns_page(user_id):
    st.markdown('<div class="hero"><h1>Análise de padrões</h1><p>Entenda onde você decide melhor, onde tropeça mais e como sua confiança se calibra com o tempo.</p></div>', unsafe_allow_html=True)
    summary = get_pattern_summary(user_id)
    bias_df = get_bias_breakdown(user_id)
    category_quality = get_category_quality_summary(user_id)
    rec_df = get_recommendation_breakdown(user_id)
    conf_gap = get_confidence_gap_summary(user_id)
    c1, c2, c3 = st.columns(3)
    insights = [
        ("Categoria mais frequente", summary.get("top_category", "-"), "Onde você mais toma decisões"),
        ("Modo mais usado", summary.get("top_mode", "-"), "Rápido ou robusto"),
        ("Alerta mais recorrente", summary.get("top_penalty", "-"), "Principal fragilidade do processo"),
    ]
    for col, item in zip([c1, c2, c3], insights):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{item[0]}</div><div class="metric-value" style="font-size:1.2rem">{item[1]}</div><div class="metric-sub">{item[2]}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="soft-card"><div class="step-title">Calibração de confiança</div><p style="margin:.2rem 0;"><b>Gap médio absoluto:</b> {conf_gap.get("avg_gap_abs", 0):.1f}</p><p style="margin:.2rem 0;"><b>Excesso de confiança:</b> {conf_gap.get("overconfident_count", 0)}</p><p style="margin:.2rem 0;"><b>Subconfiança:</b> {conf_gap.get("underconfident_count", 0)}</p><p style="margin:.2rem 0;"><b>Calibradas:</b> {conf_gap.get("calibrated_count", 0)}</p></div>', unsafe_allow_html=True)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### Vieses mais marcados")
        if bias_df.empty:
            st.info("Ainda não há dados suficientes para vieses.")
        else:
            st.bar_chart(bias_df.set_index("bias_name")["total"], height=320)
            st.dataframe(bias_df, use_container_width=True, hide_index=True)
    with right:
        st.markdown("### Qualidade por categoria")
        if category_quality.empty:
            st.info("Ainda não há revisões suficientes para análise por categoria.")
        else:
            st.bar_chart(category_quality.set_index("category")["avg_quality"], height=320)
            st.dataframe(category_quality, use_container_width=True, hide_index=True)
    if not rec_df.empty:
        top_rec = rec_df.sort_values("total", ascending=False).iloc[0]
        msg = [f'A recomendação mais emitida até agora é **{top_rec["recommendation"]}**.']
        if not category_quality.empty:
            best = category_quality.sort_values(["avg_quality", "total"], ascending=[False, False]).iloc[0]
            worst = category_quality.sort_values(["avg_quality", "total"], ascending=[True, False]).iloc[0]
            msg.append(f'Sua melhor faixa de resultado real aparece em **{best["category"]}**.')
            msg.append(f'A categoria que mais pede cautela hoje é **{worst["category"]}**.')
        if not bias_df.empty:
            msg.append(f'O viés mais marcado no histórico é **{bias_df.sort_values("total", ascending=False).iloc[0]["bias_name"]}**.')
        st.markdown("\n\n".join(msg))


def account_page(user):
    st.markdown('<div class="hero"><h1>Conta</h1><p>Gerencie senha local e veja informações básicas do seu perfil.</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="soft-card"><p style="margin:0;"><b>Usuário:</b> {user["username"]}</p><p style="margin:.25rem 0 0 0;"><b>ID:</b> {user["id"]}</p></div>', unsafe_allow_html=True)
    with st.form("password_form"):
        current_password = st.text_input("Senha atual", type="password")
        new_password = st.text_input("Nova senha", type="password")
        confirm_password = st.text_input("Confirmar nova senha", type="password")
        save_pass = st.form_submit_button("Atualizar senha", use_container_width=True)
    if save_pass:
        if new_password != confirm_password:
            st.error("As novas senhas não conferem.")
        elif len(new_password.strip()) < 4:
            st.error("Use pelo menos 4 caracteres.")
        else:
            ok, msg = update_password(user["username"], current_password, new_password)
            if ok:
                st.success(msg)
            else:
                st.error(msg)


def main():
    if not st.session_state.user:
        login_screen()
        return
    page = sidebar_top()
    user_id = int(st.session_state.user["id"])
    if page == "🏠 Painel":
        dashboard_page(user_id)
    elif page == "⚡ Checklist Rápido":
        quick_page(user_id)
    elif page == "🧠 Checklist Robusto":
        robust_page(user_id)
    elif page == "🗂️ Histórico":
        history_page(user_id)
    elif page == "🔍 Padrões":
        patterns_page(user_id)
    elif page == "⚙️ Conta":
        account_page(st.session_state.user)


if __name__ == "__main__":
    main()
