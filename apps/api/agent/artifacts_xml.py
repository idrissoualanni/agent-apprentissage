from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constantes du format ─────────────────────────────────────────────────

ARTEFACT_TAG = "learning_artefact"
ARTEFACT_TYPES = ("quiz", "schema", "code", "chart", "feynman")

# Balise ouvrante/fermante, tolérante aux attributs et espaces.
_RE_BLOCK = re.compile(
    r"<learning_artefact\b(?P<attrs>[^>]*)>(?P<body>.*?)</learning_artefact>",
    re.DOTALL | re.IGNORECASE,
)
_RE_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


# ─── Extraction des blocs ─────────────────────────────────────────────────

def _parse_attrs(raw: str) -> dict:
    """Parse les attributs d'une balise ouvrante en dict (clés en minuscules)."""
    attrs = {}
    for key, value in _RE_ATTR.findall(raw or ""):
        attrs[key.lower()] = value.strip()
    return attrs


def _clean_xml(body: str) -> str:
    """Nettoie le corps XML avant parsing : CDATA, entités courantes."""
    body = body.strip()
    # Retire les déclarations CDATA que certains modèles ajoutent.
    body = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", body, flags=re.DOTALL)
    return body


def _parse_question(q_el) -> Optional[dict]:
    """Convertit un élément <question> en dict exploitable par le frontend."""
    text_el = q_el.find("text")
    question_text = (text_el.text or "").strip() if text_el is not None else ""

    options = [
        (o.text or "").strip() for o in q_el.findall("option") if (o.text or "").strip()
    ]

    correct_el = q_el.find("correct")
    correct_index = 0
    if correct_el is not None and (correct_el.text or "").strip() != "":
        raw = correct_el.text.strip()
        # Accepte un index numérique ou une lettre (A-D).
        if raw.upper() in ("A", "B", "C", "D"):
            correct_index = ord(raw.upper()) - ord("A")
        else:
            try:
                correct_index = int(raw)
            except ValueError:
                correct_index = 0

    expl_el = q_el.find("explanation")
    explanation = (expl_el.text or "").strip() if expl_el is not None else ""

    if not question_text or len(options) < 2:
        return None

    # Borner l'index correct.
    if not (0 <= correct_index < len(options)):
        correct_index = 0

    return {
        "question": question_text,
        "options": options[:4],
        "correct_index": correct_index,
        "explanation": explanation,
    }


def _artefact_from_match(attrs: dict, body: str) -> Optional[dict]:
    """Construit un artefact structuré depuis les attributs + corps XML."""
    a_type = (attrs.get("type") or "").lower()
    if a_type not in ARTEFACT_TYPES:
        logger.warning(f"artifacts_xml: type inconnu '{a_type}', bloc ignoré.")
        return None

    title = attrs.get("title") or "Artefact"
    metadata = {
        "identifier": attrs.get("identifier"),
        "competency_name": attrs.get("competency"),
        "level": attrs.get("level"),
        "interactive": (attrs.get("interactive") or "false").lower() == "true",
    }
    if attrs.get("competency_id"):
        try:
            metadata["competency_id"] = int(attrs["competency_id"])
        except ValueError:
            pass

    clean = _clean_xml(body)
    content = ""
    description = ""

    # On tente un parsing XML complet ; en cas d'échec on retombe sur du
    # regex ciblé pour ne pas perdre l'artefact.
    root = None
    try:
        root = ET.fromstring(f"<root>{clean}</root>")
    except ET.ParseError as e:
        logger.warning(f"artifacts_xml: XML invalide ({e}); fallback regex.")

    if a_type == "quiz":
        questions = []
        if root is not None:
            desc_el = root.find("description")
            if desc_el is not None:
                description = (desc_el.text or "").strip()
            for q_el in root.findall("question"):
                q = _parse_question(q_el)
                if q:
                    questions.append(q)
        else:
            questions = _fallback_parse_questions(clean)
            description = _fallback_tag(clean, "description")

        if not questions:
            return None
        metadata["description"] = description
        content = json.dumps(questions, ensure_ascii=False)

    elif a_type == "schema":
        if root is not None:
            m_el = root.find("mermaid")
            content = (m_el.text or "").strip() if m_el is not None else clean
            desc_el = root.find("description")
            description = (desc_el.text or "").strip() if desc_el is not None else ""
        else:
            content = _fallback_tag(clean, "mermaid") or clean
        metadata["description"] = description

    elif a_type == "code":
        language = attrs.get("language") or "python"
        if root is not None:
            c_el = root.find("code")
            content = (c_el.text or "").strip() if c_el is not None else clean
        else:
            content = _fallback_tag(clean, "code") or clean
        # Le frontend (CodeArtifact) affiche `content` tel quel dans un <pre>.
        # Le langage part dans les métadonnées.
        metadata["language"] = language

    elif a_type == "chart":
        if root is not None:
            d_el = root.find("data")
            raw_data = (d_el.text or "").strip() if d_el is not None else clean
        else:
            raw_data = _fallback_tag(clean, "data") or clean
        # Le contenu chart est du JSON ; on le valide puis le re-sérialise.
        try:
            parsed = json.loads(raw_data)
            content = json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            content = raw_data

    elif a_type == "feynman":
        if root is not None:
            inv_el = root.find("invitation")
            content = (inv_el.text or "").strip() if inv_el is not None else clean
        else:
            content = _fallback_tag(clean, "invitation") or clean

    return {
        "artifact_type": a_type,
        "title": title,
        "content": content,
        "metadata": metadata,
    }


# ─── Fallback regex (XML mal formé) ───────────────────────────────────────

def _fallback_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", body, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _fallback_parse_questions(body: str) -> list:
    """Parse des <question> via regex quand ElementTree échoue."""
    questions = []
    for q_match in re.finditer(
        r"<question>(.*?)</question>", body, re.DOTALL | re.IGNORECASE
    ):
        q_body = q_match.group(1)
        text = _fallback_tag(q_body, "text")
        options = [
            o.strip()
            for o in re.findall(r"<option>(.*?)</option>", q_body, re.DOTALL)
            if o.strip()
        ]
        correct_raw = _fallback_tag(q_body, "correct")
        correct_index = 0
        if correct_raw.upper() in ("A", "B", "C", "D"):
            correct_index = ord(correct_raw.upper()) - ord("A")
        else:
            try:
                correct_index = int(correct_raw)
            except ValueError:
                correct_index = 0
        explanation = _fallback_tag(q_body, "explanation")
        if text and len(options) >= 2:
            if not (0 <= correct_index < len(options)):
                correct_index = 0
            questions.append({
                "question": text,
                "options": options[:4],
                "correct_index": correct_index,
                "explanation": explanation,
            })
    return questions


# ─── API publique ─────────────────────────────────────────────────────────

def parse_learning_artefacts(text: str) -> tuple[str, list]:
    """Extrait les blocs <learning_artefact> d'un texte.

    Retourne un tuple ``(clean_text, artifacts)`` :
    - ``clean_text`` : le texte d'origine SANS les balises (remplacées par une
      courte référence lisible), prêt à être affiché dans le chat ;
    - ``artifacts`` : liste de dicts artefacts structurés (prêts pour l'état
      ``artifacts`` du graphe et pour le frontend).
    """
    if not text or f"<{ARTEFACT_TAG}" not in text.lower():
        return text, []

    artifacts = []
    clean_text = text

    for m in _RE_BLOCK.finditer(text):
        attrs = _parse_attrs(m.group("attrs"))
        body = m.group("body")
        artefact = _artefact_from_match(attrs, body)
        if artefact is None:
            continue
        artifacts.append(artefact)
        # Remplace le bloc XML par une référence courte dans le texte affiché.
        ref = f"→ Artefact interactif : {artefact['title']} ({artefact['artifact_type']})"
        clean_text = clean_text.replace(m.group(0), ref)

    # Resserre les lignes vides multiples laissées par les retraits.
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    return clean_text, artifacts


def has_artefact(text: str) -> bool:
    """True si le texte contient au moins une balise <learning_artefact>."""
    return bool(text) and f"<{ARTEFACT_TAG}" in text.lower()
