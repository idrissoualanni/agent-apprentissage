"""Renderers HTML interactifs pour quiz, Feynman, artefacts et confirmations.

Ces fonctions retournent du HTML/CSS/JS prêt à être injecté via
``st.components.v1.html()`` dans Streamlit.
"""

import json
from typing import Optional


# ---------------------------------------------------------------------------
# Quiz Renderer
# ---------------------------------------------------------------------------

def render_quiz_html(questions: list, quiz_id: str = "quiz-1") -> str:
    """Génère un quiz HTML interactif avec sélection d'options et feedback immédiat.

    Args:
        questions: liste de dicts {"question": str, "options": list[str], "correct_index": int}
        quiz_id:   identifiant unique pour les clés JS
    """
    if not questions:
        return "<p>Aucune question disponible.</p>"

    cards_html = []
    for i, q in enumerate(questions):
        options_html = []
        for j, opt in enumerate(q.get("options", [])):
            options_html.append(
                f'<button class="quiz-option" data-q="{i}" data-idx="{j}">'
                f'<span class="opt-letter">{chr(65+j)}</span> {opt}</button>'
            )
        cards_html.append(f"""
        <div class="quiz-card" id="{quiz_id}-q{i}">
            <p class="quiz-question"><strong>{i+1}.</strong> {q['question']}</p>
            <div class="quiz-options">
                {''.join(options_html)}
            </div>
            <div class="quiz-feedback" id="{quiz_id}-fb{i}"></div>
        </div>""")

    correct_map = {str(i): q.get("correct_index", 0) for i, q in enumerate(questions)}

    html = f"""
    <style>
    #{quiz_id} {{ font-family: 'Segoe UI', system-ui, sans-serif; max-width: 680px; margin: 0 auto; }}
    .quiz-card {{
        background: #1e1e2e; border: 1px solid #313244; border-radius: 12px;
        padding: 20px; margin-bottom: 16px; transition: border-color 0.3s;
    }}
    .quiz-card.answered {{ border-color: #585b70; opacity: 0.85; }}
    .quiz-question {{ color: #cdd6f4; font-size: 15px; margin: 0 0 12px; line-height: 1.5; }}
    .quiz-options {{ display: flex; flex-direction: column; gap: 8px; }}
    .quiz-option {{
        display: flex; align-items: center; gap: 10px;
        background: #181825; border: 1px solid #45475a; border-radius: 8px;
        padding: 10px 14px; color: #bac2de; cursor: pointer;
        font-size: 14px; transition: all 0.2s; text-align: left; width: 100%;
    }}
    .quiz-option:hover {{ background: #313244; border-color: #89b4fa; color: #cdd6f4; }}
    .quiz-option.selected {{ border-color: #89b4fa; background: #1e1e2e; }}
    .quiz-option.correct {{ border-color: #a6e3a1; background: #1e3a2e; color: #a6e3a1; }}
    .quiz-option.wrong {{ border-color: #f38ba8; background: #3a1e2e; color: #f38ba8; }}
    .quiz-option:disabled {{ cursor: default; opacity: 0.7; }}
    .opt-letter {{
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; height: 26px; border-radius: 50%; background: #313244;
        color: #a6adc8; font-weight: 600; font-size: 13px; flex-shrink: 0;
    }}
    .quiz-feedback {{
        margin-top: 10px; padding: 8px 12px; border-radius: 8px;
        font-size: 13px; display: none;
    }}
    .quiz-feedback.show {{ display: block; }}
    .quiz-feedback.correct {{ background: #1e3a2e; color: #a6e3a1; border: 1px solid #a6e3a1; }}
    .quiz-feedback.wrong {{ background: #3a1e2e; color: #f38ba8; border: 1px solid #f38ba8; }}
    </style>

    <div id="{quiz_id}">
        {''.join(cards_html)}
    </div>

    <script>
    (function() {{
        const correct = {json.dumps(correct_map)};
        const qid = '{quiz_id}';
        let score = 0;
        let answered = 0;
        const total = Object.keys(correct).length;

        document.querySelectorAll('#' + qid + ' .quiz-option').forEach(btn => {{
            btn.addEventListener('click', function() {{
                const qi = this.dataset.q;
                const card = document.getElementById(qid + '-q' + qi);
                if (card.classList.contains('answered')) return;

                card.classList.add('answered');
                const chosen = parseInt(this.dataset.idx);
                const right = correct[qi];

                // Disable all buttons in this card
                card.querySelectorAll('.quiz-option').forEach(b => {{
                    b.disabled = true;
                    if (parseInt(b.dataset.idx) === right) b.classList.add('correct');
                }});

                const fb = document.getElementById(qid + '-fb' + qi);
                fb.classList.add('show');

                if (chosen === right) {{
                    this.classList.add('correct');
                    fb.textContent = 'Correct !';
                    fb.classList.add('correct');
                    score++;
                }} else {{
                    this.classList.add('wrong');
                    fb.textContent = 'Incorrect. La bonne réponse est indiquée en vert.';
                    fb.classList.add('wrong');
                }}

                answered++;
                if (answered === total) {{
                    const pct = Math.round((score / total) * 100);
                    const summary = document.createElement('div');
                    summary.className = 'quiz-card';
                    summary.style.cssText = 'text-align:center; border-color:#89b4fa;';
                    summary.innerHTML = '<p style="font-size:20px;color:#cdd6f4;margin:0;">' +
                        '<strong>Score : ' + score + '/' + total + '</strong> (' + pct + '%)</p>';
                    document.getElementById(qid).appendChild(summary);
                }}
            }});
        }});
    }})();
    </script>
    """
    return html


# ---------------------------------------------------------------------------
# Feynman Renderer
# ---------------------------------------------------------------------------

def render_feynman_html(topic: str, feedback: Optional[str] = None,
                        score: Optional[float] = None) -> str:
    """Zone d'écriture Feynman avec compteur de mots et feedback coloré."""
    score_section = ""
    if score is not None:
        color = "#a6e3a1" if score >= 0.7 else "#f9e2af" if score >= 0.4 else "#f38ba8"
        label = "Excellent" if score >= 0.7 else "À améliorer" if score >= 0.4 else "À retravailler"
        score_section = f"""
        <div class="feynman-score" style="border-color:{color};">
            <span style="color:{color};font-weight:700;">{label}</span>
            <span style="color:#6c7086;"> — {score:.0%}</span>
        </div>"""

    feedback_section = ""
    if feedback:
        feedback_section = f"""
        <div class="feynman-feedback">
            <strong>Evaluation :</strong><br>{feedback}
        </div>"""

    html = f"""
    <style>
    .feynman-box {{
        font-family: 'Segoe UI', system-ui, sans-serif; max-width: 680px; margin: 0 auto;
        background: #1e1e2e; border: 1px solid #313244; border-radius: 12px; padding: 20px;
    }}
    .feynman-title {{
        color: #89b4fa; font-size: 16px; font-weight: 600; margin-bottom: 6px;
    }}
    .feynman-hint {{
        color: #6c7086; font-size: 13px; margin-bottom: 14px; font-style: italic;
    }}
    .feynman-textarea {{
        width: 100%; min-height: 120px; background: #181825; border: 1px solid #45475a;
        border-radius: 8px; color: #cdd6f4; padding: 12px; font-size: 14px;
        font-family: inherit; resize: vertical; box-sizing: border-box;
    }}
    .feynman-textarea:focus {{ outline: none; border-color: #89b4fa; }}
    .feynman-counter {{
        text-align: right; color: #6c7086; font-size: 12px; margin-top: 4px;
    }}
    .feynman-score {{
        margin-top: 12px; padding: 10px 14px; border-radius: 8px;
        border: 1px solid; background: #181825;
    }}
    .feynman-feedback {{
        margin-top: 12px; padding: 12px 14px; border-radius: 8px;
        background: #181825; border: 1px solid #45475a;
        color: #bac2de; font-size: 14px; line-height: 1.5;
    }}
    </style>

    <div class="feynman-box">
        <div class="feynman-title">Methode Feynman — {topic}</div>
        <div class="feynman-hint">Explique comme si j'avais 12 ans. Utilise tes propres mots.</div>
        <textarea class="feynman-textarea" id="feynman-input"
            placeholder="Ecris ton explication ici..."></textarea>
        <div class="feynman-counter" id="feynman-counter">0 mots</div>
        {score_section}
        {feedback_section}
    </div>

    <script>
    (function() {{
        const ta = document.getElementById('feynman-input');
        const counter = document.getElementById('feynman-counter');
        ta.addEventListener('input', function() {{
            const words = this.value.trim().split(/\\s+/).filter(w => w.length > 0);
            counter.textContent = words.length + ' mot' + (words.length !== 1 ? 's' : '');
        }});
    }})();
    </script>
    """
    return html


# ---------------------------------------------------------------------------
# Artifact Renderer
# ---------------------------------------------------------------------------

def render_artifact_html(title: str, content: str, artifact_type: str = "schema") -> str:
    """Affiche un artefact pédagogique avec un rendu Markdown simple."""
    # Conversion Markdown basique -> HTML (titres, gras, listes, code)
    import re
    lines = content.split("\n")
    html_lines = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                html_lines.append("</code></pre>")
                in_code = False
            else:
                html_lines.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue
        # Headers
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            html_lines.append(f'<h{level} style="color:#89b4fa;">{m.group(2)}</h{level}>')
            continue
        # Bold
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # List items
        if re.match(r"^[-*]\s+", line):
            line = re.sub(r"^[-*]\s+", "<li>", line)
            html_lines.append(line + "</li>")
            continue
        # Code inline
        line = re.sub(r"`([^`]+)`", r'<code style="background:#313244;padding:2px 6px;border-radius:4px;color:#f5c2e7;">\1</code>', line)
        html_lines.append(f"<p>{line}</p>" if line.strip() else "<br>")

    body = "\n".join(html_lines)

    badge_colors = {
        "schema": "#89b4fa",
        "schéma": "#89b4fa",
        "mindmap": "#cba6f7",
        "timeline": "#f9e2af",
        "fiche": "#a6e3a1",
        "analogie": "#fab387",
    }
    color = badge_colors.get(artifact_type.lower(), "#89b4fa")

    return f"""
    <style>
    .artifact-box {{
        font-family: 'Segoe UI', system-ui, sans-serif; max-width: 720px; margin: 0 auto;
        background: #1e1e2e; border: 1px solid #313244; border-radius: 12px; padding: 24px;
    }}
    .artifact-header {{
        display: flex; align-items: center; gap: 10px; margin-bottom: 16px;
    }}
    .artifact-badge {{
        background: {color}22; color: {color}; border: 1px solid {color};
        padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600;
        text-transform: uppercase;
    }}
    .artifact-title {{
        color: #cdd6f4; font-size: 18px; font-weight: 600;
    }}
    .artifact-body {{ color: #bac2de; font-size: 14px; line-height: 1.7; }}
    .artifact-body h1, .artifact-body h2, .artifact-body h3 {{ margin-top: 16px; }}
    .artifact-body p {{ margin: 6px 0; }}
    .artifact-body li {{ margin-left: 16px; }}
    .artifact-body pre {{
        background: #181825; border: 1px solid #45475a; border-radius: 8px;
        padding: 12px; overflow-x: auto;
    }}
    .artifact-body code {{ font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 13px; }}
    </style>

    <div class="artifact-box">
        <div class="artifact-header">
            <span class="artifact-badge">{artifact_type}</span>
            <span class="artifact-title">{title}</span>
        </div>
        <div class="artifact-body">{body}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Confirmation Renderer
# ---------------------------------------------------------------------------

def render_confirmation_html(prompt: str, conf_type: str) -> str:
    """Banniere de confirmation stylisee (boutons gerees par Streamlit)."""
    icons = {
        "quiz": ":material/quiz:",
        "feynman": ":material/record_voice_over:",
        "artifact": ":material/draw:",
    }
    icon = icons.get(conf_type, ":material/help:")
    return f"""
    <style>
    .confirm-box {{
        font-family: 'Segoe UI', system-ui, sans-serif;
        background: linear-gradient(135deg, #1e1e2e, #181825);
        border: 1px solid #89b4fa; border-radius: 12px;
        padding: 20px 24px; text-align: center; max-width: 500px; margin: 0 auto;
    }}
    .confirm-icon {{ font-size: 32px; margin-bottom: 8px; }}
    .confirm-text {{ color: #cdd6f4; font-size: 15px; line-height: 1.5; }}
    </style>
    <div class="confirm-box">
        <div class="confirm-icon">{icon}</div>
        <div class="confirm-text">{prompt}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Progress / Calendar Renderer (bonus)
# ---------------------------------------------------------------------------

def render_calendar_html(revision_items: list) -> str:
    """Affiche un mini-calendrier de révision."""
    if not revision_items:
        return "<p>Aucune révision en attente.</p>"

    items_html = []
    for item in revision_items:
        box = item.get("leitner_box", 0)
        colors = ["#f38ba8", "#fab387", "#f9e2af", "#a6e3a1", "#94e2d5", "#89b4fa"]
        color = colors[min(box, len(colors)-1)]
        items_html.append(f"""
        <div class="rev-item" style="border-left: 3px solid {color};">
            <span class="rev-name">{item.get('nom', 'N/A')}</span>
            <span class="rev-meta">Box {box} — Score {item.get('score', 0):.0%}</span>
            <span class="rev-date">Revoir : {item.get('next_review', '?')}</span>
        </div>""")

    return f"""
    <style>
    .cal-box {{
        font-family: 'Segoe UI', system-ui, sans-serif; max-width: 500px; margin: 0 auto;
        background: #1e1e2e; border: 1px solid #313244; border-radius: 12px; padding: 16px;
    }}
    .rev-item {{
        padding: 10px 14px; margin-bottom: 8px; background: #181825;
        border-radius: 8px; display: flex; flex-direction: column; gap: 2px;
    }}
    .rev-name {{ color: #cdd6f4; font-weight: 600; font-size: 14px; }}
    .rev-meta {{ color: #6c7086; font-size: 12px; }}
    .rev-date {{ color: #89b4fa; font-size: 12px; }}
    </style>
    <div class="cal-box">
        <h3 style="color:#89b4fa;margin:0 0 12px;font-size:15px;">Plan de révision</h3>
        {''.join(items_html)}
    </div>
    """
