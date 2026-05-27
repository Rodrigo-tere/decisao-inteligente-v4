
import streamlit as st
from datetime import datetime, timedelta

from db import (
    init_db, migrate_db, seed_default_user, verify_login, create_user, update_password,
    insert_decision, list_decisions_df, get_decision, update_outcome,
    get_summary_stats, get_pattern_summary, get_monthly_summary, get_bias_breakdown,
    get_recommendation_breakdown, get_category_quality_summary, export_decisions_df,
    get_confidence_gap_summary, using_supabase
)

st.set_page_config(page_title="Decisão Inteligente Cloud", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")
init_db()
migrate_db()
seed_default_user()

st.markdown("""
<style>
.block-container {padding-top: 1rem; max-width: 1240px;}
.hero {background: linear-gradient(135deg,#0f172a 0%,#1f2937 48%,#0f766e 100%); color:white; padding:1.2rem; border-radius:10px; margin-bottom:1rem;}
.hero h1 {margin:0 0 .2rem 0; font-size:2rem;}
.card, .soft-card, .metric-card {background:#fff; border:1px solid #e5e7eb; border-radius:8px; padding:1rem; margin-bottom:.8rem;}
.metric-value {font-size:1.6rem; font-weight:800;}
.metric-label,.subtle {color:#64748b;}
.ok {background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; border-radius:8px; padding:.9rem 1rem; font-weight:700;}
.warn {background:#fffbeb; color:#92400e; border:1px solid #fde68a; border-radius:8px; padding:.9rem 1rem; font-weight:700;}
.stop {background:#fef2f2; color:#991b1b; border:1px solid #fecaca; border-radius:8px; padding:.9rem 1rem; font-weight:700;}
.pill {display:inline-block; padding:.2rem .65rem; border-radius:999px; background:#eff6ff; color:#1d4ed8; font-weight:700; font-size:.76rem; margin-right:.35rem;}
.stage {font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; color:#0f766e; font-weight:800;}
</style>
""", unsafe_allow_html=True)

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

def recommendation_detail(score, penalties):
    if score >= 80:
        next_step = "Execute com disciplina, defina o responsável e acompanhe a revisão."
    elif score >= 62:
        next_step = "Valide em escala pequena antes de comprometer recursos maiores."
    elif score >= 45:
        next_step = "Reforce dados, alternativas e riscos antes de decidir."
    else:
        next_step = "Adie ou reformule a decisão antes de avançar."
    main_risk = penalties[0] if penalties else "Nenhum risco crítico foi marcado pelo checklist."
    return main_risk, next_step

def system_confidence_from_score(score):
    return round(max(1.0, min(10.0, score / 10.0)), 1)

def confidence_gap_label(user_confidence, system_confidence):
    gap = round(float(user_confidence) - float(system_confidence), 1)
    if gap >= 2:
        return gap, "⚠️ Possível excesso de confiança", "warn", "Sua confiança pessoal está bem acima da confiança calculada pelo checklist."
    if gap <= -2:
        return gap, "🧊 Possível subconfiança", "warn", "Sua confiança pessoal está bem abaixo da confiança calculada pelo checklist."
    return gap, "✅ Confiança calibrada", "ok", "Sua percepção está relativamente alinhada com a leitura do sistema."

def quick_scoring(data):
    score = 100
    penalties = []
    emo = {"Alta": 20, "Média": 8, "Baixa": 0}
    score -= emo.get(data["emotion"], 0)
    if data["emotion"] != "Baixa":
        penalties.append("Emoção elevada no momento")
    if data["data"] == "Não":
        score -= 20
        penalties.append("Sem base suficiente em dados")
    risk = {"Alto": 20, "Médio": 8, "Baixo": 0}
    score -= risk.get(data["risk"], 0)
    if data["risk"] != "Baixo":
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
    if data["reversible"] == "Sim":
        score += 4
    if data["small_test"] == "Sim":
        score += 4
    if data["alignment"] == "Não":
        score -= 10
        penalties.append("Decisão desalinhada com seus objetivos")
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
        score -= 5; penalties.append("Tolerância ao risco apenas moderada")
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
    if len(data.get("second_order", "").strip()) < 15:
        score -= 6; penalties.append("Efeitos de segunda ordem pouco explorados")
    if len(data.get("success_criteria", "").strip()) < 15:
        score -= 6; penalties.append("Critério de sucesso pouco claro")

    bias_fields = [
        ("bias_confirmation","Viés de confirmação"),
        ("bias_herd","Efeito manada"),
        ("bias_loss","Aversão à perda"),
        ("bias_ego","Ego/excesso de confiança"),
        ("bias_anchor","Ancoragem"),
    ]
    active = 0
    for field, label in bias_fields:
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

def show_result_box(score, recommendation, css_class, summary, penalties, confidence):
    main_risk, next_step = recommendation_detail(score, penalties)
    st.markdown(f'<div class="{css_class}">{recommendation} · Score {score}/100<br><span style="font-weight:500">{summary}</span></div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        st.markdown(f'<div class="soft-card"><div class="stage">Principal atenção</div><b>{main_risk}</b></div>', unsafe_allow_html=True)
    with d2:
        st.markdown(f'<div class="soft-card"><div class="stage">Próximo passo sugerido</div><b>{next_step}</b></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="soft-card"><b>Confiança percebida</b><div class="metric-value">{confidence["user_confidence"]}/10</div><div class="subtle">O quanto você sente confiança nessa decisão.</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="soft-card"><b>Confiança calculada</b><div class="metric-value">{confidence["system_confidence"]}/10</div><div class="subtle">Score convertido para escala de 1 a 10.</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="{confidence["gap_class"]}">{confidence["gap_title"]} · Diferença {confidence["gap"]}<br><span style="font-weight:500">{confidence["gap_summary"]} Cálculo: confiança percebida menos confiança calculada.</span></div>', unsafe_allow_html=True)
    if penalties:
        st.markdown("**Pontos de atenção**")
        for p in penalties:
            st.write("•", p)

def humanize_value(value):
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if value in ("Sim", "Não", "Baixa", "Média", "Alta", "Baixo", "Médio", "Alto"):
        return value
    return value

def friendly_inputs(inputs):
    labels = {
        "emotion": "Emoção no momento",
        "data": "Dados suficientes",
        "risk": "Nível de risco",
        "alignment": "Alinhamento com objetivos",
        "cost_opportunity": "Custo de oportunidade avaliado",
        "worst_case": "Pior cenário considerado",
        "bias_alert": "Percepção de viés ou apego",
        "reversible": "Decisão reversível",
        "small_test": "Pode testar pequeno",
        "emotion_level": "Nível de emoção",
        "urgency_level": "Nível de urgência",
        "clarity_level": "Clareza do problema",
        "opportunity_cost_level": "Análise do custo de oportunidade",
        "downside_tolerance": "Tolerância ao pior cenário",
        "goal_alignment": "Alinhamento com objetivos de longo prazo",
        "confidence": "Confiança percebida",
        "review_days": "Prazo para revisão",
        "has_data": "Tem dados suficientes",
        "test_small": "Pode testar pequeno",
        "trusted_peer_review": "Considerou uma opinião confiável",
        "alternatives": "Alternativas consideradas",
        "inversion_plan": "Análise de inversão",
        "second_order": "Efeitos de segunda ordem",
        "success_criteria": "Critério de sucesso para revisão",
        "bias_confirmation": "Viés de confirmação",
        "bias_herd": "Efeito manada",
        "bias_loss": "Aversão à perda",
        "bias_anchor": "Ancoragem",
        "bias_ego": "Ego ou excesso de confiança",
    }
    hidden_when_false = {"bias_confirmation", "bias_herd", "bias_loss", "bias_anchor", "bias_ego"}
    rows = []
    for key, value in inputs.items():
        if key in hidden_when_false and not value:
            continue
        label = labels.get(key, key.replace("_", " ").title())
        if key == "review_days":
            value = f"{value} dias"
        rows.append({"Campo": label, "Resposta": humanize_value(value)})
    return rows

def pending_reviews_df(user_id):
    df = list_decisions_df(user_id)
    if df.empty or "review_due_at" not in df.columns:
        return df
    pending = df[df["outcome_quality"].isna()].copy()
    if pending.empty:
        return pending
    today = datetime.now().date()
    pending["review_date"] = pending["review_due_at"].astype(str)
    pending["days_to_review"] = pending["review_date"].apply(lambda d: (datetime.strptime(d[:10], "%Y-%m-%d").date() - today).days if d and d != "None" else None)
    return pending.sort_values(["days_to_review", "id"], ascending=[True, False])

def learning_status(row):
    if row.get("outcome_quality") == row.get("outcome_quality"):
        return "Revisada"
    due = str(row.get("review_due_at") or "")
    if not due:
        return "Sem data"
    try:
        delta = (datetime.strptime(due[:10], "%Y-%m-%d").date() - datetime.now().date()).days
    except Exception:
        return "A revisar"
    if delta < 0:
        return "Atrasada"
    if delta == 0:
        return "Revisar hoje"
    return f"Revisar em {delta} dias"

def login_screen():
    modo_banco = "Supabase ativo" if using_supabase() else "Modo local (sem Supabase configurado)"
    st.markdown(f'<div class="hero"><h1>🧠 Decisão Inteligente Cloud</h1><p>Central online de apoio cognitivo para decisões operacionais, revisão de resultados e aprendizado organizacional. <b>{modo_banco}</b>.</p></div>', unsafe_allow_html=True)
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown('<div class="card"><span class="pill">Ciclo decisório</span><span class="pill">Calibração</span><span class="pill">Memória operacional</span><h4>O que a versão Cloud entrega</h4><ul><li>Acesso por link em qualquer celular</li><li>Checklist rápido e robusto</li><li>Confiança percebida x calculada</li><li>Próximo passo sugerido</li><li>Revisões pendentes</li><li>Histórico rastreável em nuvem</li></ul></div>', unsafe_allow_html=True)
    with right:
        tab1, tab2 = st.tabs(["Entrar", "Criar usuário"])
        with tab1:
            with st.form("login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                ok = st.form_submit_button("Entrar", use_container_width=True)
            if ok:
                user = verify_login(u, p)
                if user:
                    st.session_state.user = user
                    st.rerun()
                st.error("Usuário ou senha inválidos.")
            st.caption("Usuário padrão: admin | Senha: admin123")
        with tab2:
            with st.form("reg"):
                u = st.text_input("Novo usuário")
                p1 = st.text_input("Nova senha", type="password")
                p2 = st.text_input("Confirmar senha", type="password")
                ok = st.form_submit_button("Criar usuário", use_container_width=True)
            if ok:
                if p1 != p2:
                    st.error("As senhas não conferem.")
                else:
                    created, msg = create_user(u, p1)
                    if created:
                        st.success(msg)
                    else:
                        st.error(msg)

def sidebar_top():
    with st.sidebar:
        st.markdown("## 🧠 Decisão Cloud")
        st.caption("Decidir, registrar, revisar e aprender")
        st.success(f'Conectado como **{st.session_state.user["username"]}**')
        if using_supabase():
            st.info("Persistência: Supabase")
        else:
            st.warning("Persistência: local temporária")
        page = st.radio("Navegação", ["🏠 Painel", "⚡ Checklist Rápido", "🧠 Checklist Robusto", "📌 Revisões", "🗂️ Histórico", "🔍 Padrões", "⚙️ Conta"], label_visibility="collapsed")
        if st.button("Sair", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    return page

def dashboard_page(user_id):
    stats = get_summary_stats(user_id)
    monthly = get_monthly_summary(user_id)
    rec_df = get_recommendation_breakdown(user_id)
    category_df = get_category_quality_summary(user_id)
    conf_gap = get_confidence_gap_summary(user_id)
    pending = pending_reviews_df(user_id)
    overdue_count = 0 if pending.empty else int((pending["days_to_review"] < 0).sum())

    st.markdown('<div class="hero"><h1>Painel de inteligência decisória</h1><p>Visão do ciclo: decisões registradas, revisões pendentes, qualidade real e calibração de confiança.</p></div>', unsafe_allow_html=True)
    cols = st.columns(6)
    cards = [
        ("Total de decisões", int(stats["total"]), "Base histórica acumulada"),
        ("Score médio", round(stats["avg_score"], 1), "Qualidade do raciocínio"),
        ("Pendentes", int(len(pending)), "Aguardando aprendizado real"),
        ("Atrasadas", overdue_count, "Revisões fora do prazo"),
        ("Revisadas", int(stats["reviewed"]), "Com resultado real registrado"),
        ("Qualidade real média", round(stats["avg_quality"], 1), "Média das revisões"),
    ]
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="subtle">{sub}</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="soft-card"><b>Calibração de confiança:</b> gap médio absoluto {conf_gap["avg_gap_abs"]:.1f} · excesso de confiança {conf_gap["overconfident_count"]} · subconfiança {conf_gap["underconfident_count"]} · calibradas {conf_gap["calibrated_count"]}</div>', unsafe_allow_html=True)

    if not pending.empty:
        st.markdown("### Próximas revisões")
        pending_show = pending[["id", "review_due_at", "title", "category", "score", "recommendation"]].head(5).copy()
        st.dataframe(pending_show, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("### Evolução mensal")
        if monthly.empty:
            st.info("Ainda não há dados.")
        else:
            st.line_chart(monthly.set_index("ano_mes")["quantidade"], height=280)
    with right:
        st.markdown("### Recomendações emitidas")
        if rec_df.empty:
            st.info("Sem recomendações.")
        else:
            st.bar_chart(rec_df.set_index("recommendation")["total"], height=280)

    if not category_df.empty:
        best = category_df.sort_values(["avg_quality", "total"], ascending=[False, False]).iloc[0]
        worst = category_df.sort_values(["avg_quality", "total"], ascending=[True, False]).iloc[0]
        st.markdown(f'<div class="soft-card"><b>Melhor categoria revisada:</b> {best["category"]} ({best["avg_quality"]:.1f}/10)<br><b>Categoria mais frágil:</b> {worst["category"]} ({worst["avg_quality"]:.1f}/10)</div>', unsafe_allow_html=True)

def quick_page(user_id):
    st.markdown('<div class="hero"><h1>Checklist rápido</h1><p>Uso imediato para momentos de pressão e decisões menores.</p></div>', unsafe_allow_html=True)
    with st.form("quick_form"):
        title = st.text_input("Título da decisão")
        category = st.selectbox("Categoria", ["Pessoal","Trabalho","Financeiro","Cliente","Operação","Investimento","Outro"])
        decision_text = st.text_area("Qual decisão você precisa tomar agora?", height=100)
        notes = st.text_area("Observações opcionais", height=80)
        c1, c2 = st.columns(2)
        with c1:
            emotion = st.radio("Como está sua emoção agora?", ["Baixa","Média","Alta"], horizontal=True)
            data = st.radio("Você tem dados suficientes?", ["Sim","Não"], horizontal=True)
            risk = st.radio("Qual o nível de risco?", ["Baixo","Médio","Alto"], horizontal=True)
            alignment = st.radio("Está alinhado com seus objetivos?", ["Sim","Não"], horizontal=True)
        with c2:
            cost_opportunity = st.radio("Você avaliou o custo de oportunidade?", ["Sim","Não"], horizontal=True)
            worst_case = st.radio("Você considerou o pior cenário?", ["Sim","Não"], horizontal=True)
            bias_alert = st.radio("Percebe algum viés ou apego?", ["Não","Sim"], horizontal=True)
            reversible = st.radio("É reversível?", ["Não","Sim"], horizontal=True)
            small_test = st.radio("Dá para testar pequeno?", ["Não","Sim"], horizontal=True)
            confidence = st.slider("Qual sua confiança percebida nessa decisão?", 1, 10, 6)
        submit = st.form_submit_button("Gerar recomendação", use_container_width=True)

    if submit and title.strip() and decision_text.strip():
        inputs = {
            "emotion": emotion, "data": data, "risk": risk, "alignment": alignment,
            "cost_opportunity": cost_opportunity, "worst_case": worst_case, "bias_alert": bias_alert,
            "reversible": reversible, "small_test": small_test, "confidence": confidence
        }
        score, penalties = quick_scoring(inputs)
        rec, cls, summary = recommendation_from_score(score)
        sys_conf = system_confidence_from_score(score)
        gap, gap_title, gap_class, gap_summary = confidence_gap_label(confidence, sys_conf)
        st.session_state.quick_result = {
            "title": title, "category": category, "decision_text": decision_text, "notes": notes, "inputs": inputs,
            "score": score, "recommendation": rec, "css_class": cls, "summary": summary, "penalties": penalties,
            "confidence": {"user_confidence": confidence, "system_confidence": sys_conf, "gap": gap, "gap_title": gap_title, "gap_class": gap_class, "gap_summary": gap_summary}
        }

    result = st.session_state.quick_result
    if result:
        show_result_box(result["score"], result["recommendation"], result["css_class"], result["summary"], result["penalties"], result["confidence"])
        a, b = st.columns(2)
        with a:
            if st.button("Salvar no banco de decisões", use_container_width=True):
                insert_decision(
                    user_id=user_id, mode="rápido", title=result["title"], category=result["category"],
                    decision_text=result["decision_text"], score=result["score"], recommendation=result["recommendation"],
                    inputs=result["inputs"], penalties=result["penalties"], notes=result["notes"], tags="",
                    review_due_at=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                    confidence_user=result["confidence"]["user_confidence"],
                    confidence_system=result["confidence"]["system_confidence"],
                    confidence_gap=result["confidence"]["gap"],
                )
                st.success("Decisão salva com sucesso.")
        with b:
            if st.button("Limpar resultado", use_container_width=True):
                st.session_state.quick_result = None
                st.rerun()

def robust_page(user_id):
    st.markdown('<div class="hero"><h1>Canvas de decisão robusta</h1><p>Estruture contexto, alternativas, riscos, segunda ordem, critérios de sucesso e revisão futura.</p></div>', unsafe_allow_html=True)
    with st.form("robust_form"):
        title = st.text_input("Título da decisão")
        category = st.selectbox("Categoria", ["Pessoal","Trabalho","Financeiro","Cliente","Operação","Investimento","Estratégia","Outro"])
        decision_text = st.text_area("Defina com clareza qual decisão precisa ser tomada", height=100)
        tags = st.text_input("Tags")
        notes = st.text_area("Contexto adicional", height=90)
        c1, c2 = st.columns(2)
        with c1:
            emotion_level = st.slider("Nível de emoção", 1, 10, 4)
            urgency_level = st.slider("Nível de urgência", 1, 10, 5)
            clarity_level = st.slider("Clareza do problema", 1, 10, 7)
            opportunity_cost_level = st.slider("Análise do custo de oportunidade", 1, 10, 6)
        with c2:
            downside_tolerance = st.slider("Tolerância ao pior cenário", 1, 10, 6)
            goal_alignment = st.slider("Alinhamento com objetivos de longo prazo", 1, 10, 7)
            confidence = st.slider("Sua confiança percebida", 1, 10, 6)
            review_days = st.slider("Revisar em quantos dias?", 1, 60, 14)
        has_data = st.checkbox("Tenho dados suficientes")
        reversible = st.checkbox("A decisão é reversível")
        test_small = st.checkbox("Posso testar pequeno")
        trusted_peer_review = st.checkbox("Considerei discutir com alguém confiável")
        alternatives = st.text_area("Quais alternativas reais existem?", height=90)
        worst_case = st.text_area("Descreva o pior cenário", height=90)
        inversion_plan = st.text_area("Se você quisesse fazer isso dar errado, o que aconteceria?", height=90)
        second_order = st.text_area("Quais efeitos de segunda ordem essa decisão pode gerar?", height=90)
        success_criteria = st.text_area("Como saberemos, na revisão, se essa decisão foi boa?", height=90)
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

    if submit and title.strip() and decision_text.strip():
        inputs = {
            "emotion_level": emotion_level, "urgency_level": urgency_level, "clarity_level": clarity_level,
            "opportunity_cost_level": opportunity_cost_level, "downside_tolerance": downside_tolerance,
            "goal_alignment": goal_alignment, "confidence": confidence, "review_days": review_days,
            "has_data": has_data, "reversible": reversible, "test_small": test_small, "trusted_peer_review": trusted_peer_review,
            "alternatives": alternatives, "worst_case": worst_case, "inversion_plan": inversion_plan,
            "second_order": second_order, "success_criteria": success_criteria,
            "bias_confirmation": bias_confirmation, "bias_herd": bias_herd, "bias_loss": bias_loss,
            "bias_anchor": bias_anchor, "bias_ego": bias_ego,
        }
        score, penalties, bias_names = robust_scoring(inputs)
        rec, cls, summary = recommendation_from_score(score)
        sys_conf = system_confidence_from_score(score)
        gap, gap_title, gap_class, gap_summary = confidence_gap_label(confidence, sys_conf)
        st.session_state.robust_result = {
            "title": title, "category": category, "decision_text": decision_text, "notes": notes, "tags": tags,
            "inputs": inputs, "score": score, "recommendation": rec, "css_class": cls, "summary": summary,
            "penalties": penalties, "bias_names": bias_names,
            "review_due_at": (datetime.now() + timedelta(days=review_days)).strftime("%Y-%m-%d"),
            "confidence": {"user_confidence": confidence, "system_confidence": sys_conf, "gap": gap, "gap_title": gap_title, "gap_class": gap_class, "gap_summary": gap_summary}
        }

    result = st.session_state.robust_result
    if result:
        show_result_box(result["score"], result["recommendation"], result["css_class"], result["summary"], result["penalties"], result["confidence"])
        if result["bias_names"]:
            st.info("Vieses identificados: " + ", ".join(result["bias_names"]))
        a, b = st.columns(2)
        with a:
            if st.button("Salvar análise robusta", use_container_width=True):
                insert_decision(
                    user_id=user_id, mode="robusto", title=result["title"], category=result["category"],
                    decision_text=result["decision_text"], score=result["score"], recommendation=result["recommendation"],
                    inputs=result["inputs"], penalties=result["penalties"], notes=result["notes"], tags=result["tags"],
                    review_due_at=result["review_due_at"],
                    confidence_user=result["confidence"]["user_confidence"],
                    confidence_system=result["confidence"]["system_confidence"],
                    confidence_gap=result["confidence"]["gap"],
                )
                st.success("Decisão robusta salva com sucesso.")
        with b:
            if st.button("Limpar resultado", use_container_width=True):
                st.session_state.robust_result = None
                st.rerun()

def reviews_page(user_id):
    st.markdown('<div class="hero"><h1>Revisões pendentes</h1><p>Feche o ciclo decisório registrando o resultado real e a lição aprendida.</p></div>', unsafe_allow_html=True)
    pending = pending_reviews_df(user_id)
    if pending.empty:
        st.success("Não há decisões pendentes de revisão.")
        return

    view = pending[["id", "review_due_at", "title", "category", "score", "recommendation", "confidence_gap"]].copy()
    view["status"] = pending.apply(learning_status, axis=1)
    st.dataframe(view, use_container_width=True, hide_index=True)

    selected_id = st.selectbox("Selecionar decisão para revisar", pending["id"].tolist())
    item = get_decision(int(selected_id))
    st.markdown(f'<div class="soft-card"><div class="stage">Decisão registrada</div><b>{item["title"]}</b><br>{item["decision_text"]}<br><br><b>Recomendação original:</b> {item["recommendation"]} · <b>Score:</b> {item["score"]}/100 · <b>Gap:</b> {item.get("confidence_gap","-")}</div>', unsafe_allow_html=True)

    with st.expander("Resumo do raciocínio original", expanded=False):
        rows = friendly_inputs(item.get("inputs") or {})
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        penalties = item.get("penalties") or []
        if penalties:
            st.markdown("**Pontos de atenção originais**")
            for penalty in penalties:
                st.write("•", penalty)

    with st.form("pending_review_form"):
        status = st.selectbox("Resultado real", ["Deu certo", "Parcial", "Deu errado", "Sem avaliação"], index=0)
        quality = st.slider("Qualidade da decisão na prática", 1, 10, 7)
        outcome_notes = st.text_area("O que aconteceu e qual aprendizado fica?", height=130)
        save = st.form_submit_button("Registrar revisão e aprendizado", use_container_width=True)
    if save:
        update_outcome(item["id"], status, quality, outcome_notes)
        st.success("Revisão registrada. O histórico agora ficou mais inteligente.")
        st.rerun()

def history_page(user_id):
    st.markdown('<div class="hero"><h1>Histórico decisório</h1><p>Consulte decisões, revise resultados, audite raciocínios e exporte a memória operacional.</p></div>', unsafe_allow_html=True)
    df = list_decisions_df(user_id)
    if df.empty:
        st.info("Ainda não há decisões salvas.")
        return
    with st.expander("Filtros e exportação", expanded=True):
        mode_filter = st.multiselect("Modo", sorted(df["mode"].dropna().unique().tolist()), default=sorted(df["mode"].dropna().unique().tolist()))
        category_filter = st.multiselect("Categoria", sorted(df["category"].dropna().unique().tolist()), default=sorted(df["category"].dropna().unique().tolist()))
        rec_filter = st.multiselect("Recomendação", sorted(df["recommendation"].dropna().unique().tolist()), default=sorted(df["recommendation"].dropna().unique().tolist()))
        search_text = st.text_input("Buscar por título, decisão ou tags")
        export_df = export_decisions_df(user_id)
        st.download_button("Baixar CSV", export_df.to_csv(index=False).encode("utf-8-sig"), "decisoes_cloud.csv", "text/csv", use_container_width=True)
    filtered = df[df["mode"].isin(mode_filter) & df["category"].isin(category_filter) & df["recommendation"].isin(rec_filter)].copy()
    if search_text.strip():
        s = search_text.lower().strip()
        filtered = filtered[
            filtered["title"].str.lower().str.contains(s, na=False) |
            filtered["decision_text"].str.lower().str.contains(s, na=False) |
            filtered["tags"].str.lower().str.contains(s, na=False)
        ]
    filtered["learning_status"] = filtered.apply(learning_status, axis=1)
    cols_show = ["id","created_at","mode","title","category","score","recommendation","confidence_gap","review_due_at","learning_status","outcome_status","outcome_quality"]
    st.dataframe(filtered[cols_show], use_container_width=True, hide_index=True)
    ids = filtered["id"].tolist()
    if not ids:
        return
    selected_id = st.selectbox("Selecionar decisão", ids)
    item = get_decision(int(selected_id))
    st.markdown(f'<div class="soft-card"><b>{item["title"]}</b><br><b>Score:</b> {item["score"]} | <b>Recomendação:</b> {item["recommendation"]}<br><b>Confiança percebida:</b> {item.get("confidence_user","-")} / 10 | <b>Confiança calculada:</b> {item.get("confidence_system","-")} / 10 | <b>Gap:</b> {item.get("confidence_gap","-")}<br><b>Decisão:</b> {item["decision_text"]}</div>', unsafe_allow_html=True)
    with st.expander("Resumo da análise"):
        rows = friendly_inputs(item.get("inputs") or {})
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        penalties = item.get("penalties") or []
        if penalties:
            st.markdown("**Pontos de atenção**")
            for penalty in penalties:
                st.write("•", penalty)
        else:
            st.success("Nenhum ponto de atenção relevante foi identificado.")
    with st.form("review_form"):
        status = st.selectbox("Resultado real", ["Sem avaliação","Deu certo","Parcial","Deu errado"], index=0)
        quality = st.slider("Qualidade da decisão na prática", 1, 10, int(item["outcome_quality"]) if item.get("outcome_quality") else 7)
        outcome_notes = st.text_area("O que aconteceu na prática?", value=item.get("outcome_notes") or "", height=100)
        save = st.form_submit_button("Salvar revisão", use_container_width=True)
    if save:
        update_outcome(item["id"], status, quality, outcome_notes)
        st.success("Revisão salva com sucesso.")
        st.rerun()

def patterns_page(user_id):
    st.markdown('<div class="hero"><h1>Análise de padrões</h1><p>Entenda vieses, categorias e calibração de confiança.</p></div>', unsafe_allow_html=True)
    summary = get_pattern_summary(user_id)
    bias_df = get_bias_breakdown(user_id)
    category_quality = get_category_quality_summary(user_id)
    conf_gap = get_confidence_gap_summary(user_id)
    c1, c2, c3 = st.columns(3)
    items = [("Categoria mais frequente", summary["top_category"]), ("Modo mais usado", summary["top_mode"]), ("Alerta mais recorrente", summary["top_penalty"])]
    for col, item in zip([c1,c2,c3], items):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{item[0]}</div><div class="metric-value" style="font-size:1.1rem">{item[1]}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="soft-card"><b>Gap médio absoluto:</b> {conf_gap["avg_gap_abs"]:.1f}<br><b>Excesso de confiança:</b> {conf_gap["overconfident_count"]}<br><b>Subconfiança:</b> {conf_gap["underconfident_count"]}<br><b>Calibradas:</b> {conf_gap["calibrated_count"]}</div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown("### Vieses mais marcados")
        if bias_df.empty:
            st.info("Ainda não há dados suficientes.")
        else:
            st.bar_chart(bias_df.set_index("bias_name")["total"], height=300)
            st.dataframe(bias_df, use_container_width=True, hide_index=True)
    with right:
        st.markdown("### Qualidade por categoria")
        if category_quality.empty:
            st.info("Ainda não há revisões suficientes.")
        else:
            st.bar_chart(category_quality.set_index("category")["avg_quality"], height=300)
            st.dataframe(category_quality, use_container_width=True, hide_index=True)

def account_page(user):
    st.markdown('<div class="hero"><h1>Conta</h1><p>Gerencie sua senha local.</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="soft-card"><b>Usuário:</b> {user["username"]}<br><b>ID:</b> {user["id"]}</div>', unsafe_allow_html=True)
    with st.form("pwd"):
        current = st.text_input("Senha atual", type="password")
        new = st.text_input("Nova senha", type="password")
        confirm = st.text_input("Confirmar nova senha", type="password")
        ok = st.form_submit_button("Atualizar senha", use_container_width=True)
    if ok:
        if new != confirm:
            st.error("As novas senhas não conferem.")
        else:
            done, msg = update_password(user["username"], current, new)
            if done:
                st.success(msg)
            else:
                st.error(msg)

def main():
    if not st.session_state.user:
        login_screen()
        return
    page = sidebar_top()
    uid = int(st.session_state.user["id"])
    if page == "🏠 Painel":
        dashboard_page(uid)
    elif page == "⚡ Checklist Rápido":
        quick_page(uid)
    elif page == "🧠 Checklist Robusto":
        robust_page(uid)
    elif page == "📌 Revisões":
        reviews_page(uid)
    elif page == "🗂️ Histórico":
        history_page(uid)
    elif page == "🔍 Padrões":
        patterns_page(uid)
    else:
        account_page(st.session_state.user)

if __name__ == "__main__":
    main()
