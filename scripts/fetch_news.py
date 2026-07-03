import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "96"))
MAX_ITEMS_PER_PAGE_SOURCE = int(os.getenv("MAX_ITEMS_PER_PAGE_SOURCE", "4"))
MAX_ITEMS_PER_GOOGLE_QUERY = int(os.getenv("MAX_ITEMS_PER_GOOGLE_QUERY", "6"))

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Erro: SUPABASE_URL e SUPABASE_SERVICE_KEY precisam estar cadastrados nos secrets do GitHub.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarJuridicoAFA/1.1; +https://afanews.github.io/radar-juridico-afa/)"
}

GLOBAL_KEYWORDS = [
    "reforma tributária", "cbs", "ibs", "split payment", "imposto seletivo",
    "pgfn", "transação tributária", "dívida ativa", "cnd", "execução fiscal",
    "receita federal", "carf", "stf", "stj", "tst", "tributário", "icms", "iss",
    "pis", "cofins", "irpj", "csll", "lucro presumido", "per/dcomp", "ncm", "cfop",
    "trabalhista", "jornada", "pejotização", "terceirização", "sindicato", "mte",
    "anpd", "lgpd", "dados pessoais", "proteção de dados", "incidente de segurança",
    "cvm", "societário", "m&a", "fusão", "aquisição", "governança", "sócios",
    "contrato", "fornecedor", "recuperação de crédito", "inadimplência", "cobrança",
    "empresa", "empresas", "pequenas empresas", "médias empresas", "negócios",
]

EXCLUDED_TERMS = [
    "declaração de privacidade", "política de privacidade", "privacy policy", "termos de uso",
    "termos e condições", "cookies", "preferências de cookies", "login", "entrar", "cadastro",
    "assine", "minha conta", "fale conosco", "trabalhe conosco", "central de ajuda",
    "publicidade", "anuncie", "newsletter", "podcasts", "web stories", "mapa do site",
    "quem somos", "expediente", "rss", "termos de serviço",
]

CATEGORY_RULES = {
    "Reforma Tributária": ["reforma tributária", "cbs", "ibs", "split payment", "imposto seletivo", "iva dual"],
    "Contencioso Tributário": ["pgfn", "dívida ativa", "cnd", "execução fiscal", "transação tributária", "protesto de cda", "carf", "auto de infração"],
    "Tributário Consultivo": ["receita federal", "tributário", "icms", "iss", "pis", "cofins", "irpj", "csll", "per/dcomp", "ncm", "cfop", "obrigação acessória", "lucro presumido"],
    "Trabalhista Empresarial": ["tst", "mte", "trabalhista", "jornada", "pejotização", "terceirização", "vínculo de emprego", "controle de ponto", "sindicato", "nr-1"],
    "LGPD, Tecnologia e Compliance": ["anpd", "lgpd", "dados pessoais", "proteção de dados", "incidente de segurança", "vazamento de dados", "compliance", "inteligência artificial"],
    "Societário, M&A e Governança": ["cvm", "societário", "m&a", "fusão", "aquisição", "governança", "sócios", "companhias abertas", "investidor", "mercado de capitais"],
    "Cível Empresarial e Contratos": ["contrato", "fornecedor", "stj", "cível", "consumidor", "recuperação de crédito", "inadimplência", "responsabilidade civil", "marketplace"],
    "Legal Ops": ["legal ops", "legal operations", "jurimetria", "legal analytics", "departamento jurídico", "gestão jurídica", "dashboard jurídico"],
}

BUSINESS_IMPACT = {
    "Reforma Tributária": "Pode afetar preço, margem, contratos, ERP, créditos tributários e fluxo de caixa durante a transição.",
    "Contencioso Tributário": "Pode impactar CND, caixa, regularidade fiscal, passivo, garantias, financiamento e capacidade de pagamento.",
    "Tributário Consultivo": "Pode alterar rotinas fiscais, obrigações acessórias, cadastro de produtos, apuração e risco de inconsistência no ERP.",
    "Trabalhista Empresarial": "Pode exigir revisão de práticas de RH, controles de jornada, contratos, políticas internas e documentação de prova.",
    "LGPD, Tecnologia e Compliance": "Pode afetar atendimento, marketing, fornecedores, governança de dados, resposta a incidentes e reputação.",
    "Societário, M&A e Governança": "Pode impactar acordo de sócios, governança, captação, due diligence, valuation e decisões de crescimento.",
    "Cível Empresarial e Contratos": "Pode afetar contratos, fornecedores, inadimplência, responsabilidade na cadeia, margem e continuidade operacional.",
    "Legal Ops": "Pode melhorar previsibilidade, eficiência jurídica, controle de carteira, indicadores e visão executiva para decisão.",
}

AFFECTED_ROUTINE = {
    "Reforma Tributária": "ERP, cadastro fiscal, contratos, precificação, financeiro, comercial e TI",
    "Contencioso Tributário": "caixa, CND, jurídico, financeiro, garantias, passivo e governança fiscal",
    "Tributário Consultivo": "ERP, nota fiscal, cadastro fiscal, compras, fiscal, contábil e financeiro",
    "Trabalhista Empresarial": "RH, DP, liderança, controle de ponto, contratos, políticas internas e jurídico trabalhista",
    "LGPD, Tecnologia e Compliance": "marketing, atendimento, TI, fornecedores, segurança da informação e governança de dados",
    "Societário, M&A e Governança": "societário, conselho, investidores, contratos, captação, due diligence e governança",
    "Cível Empresarial e Contratos": "contratos, compras, fornecedores, comercial, cobrança, jurídico e operação",
    "Legal Ops": "jurídico interno, carteira contenciosa, indicadores, orçamento, relatórios e board",
}

AGENDA_TEMPLATE = {
    "Reforma Tributária": "O impacto da Reforma Tributária que começa no cadastro, no contrato e no caixa",
    "Contencioso Tributário": "A decisão fiscal que pode travar CND, crédito e capacidade de crescimento",
    "Tributário Consultivo": "O risco fiscal que nasce na rotina e aparece na margem",
    "Trabalhista Empresarial": "A rotina de RH que pode virar passivo quando não deixa prova",
    "LGPD, Tecnologia e Compliance": "O dado tratado na operação que pode virar risco reputacional e regulatório",
    "Societário, M&A e Governança": "O risco societário que o investidor encontra antes de pagar o preço cheio",
    "Cível Empresarial e Contratos": "O contrato que protege a operação antes do conflito aparecer",
    "Legal Ops": "O jurídico que transforma carteira, dados e indicadores em decisão de negócio",
}


AREA_EDITORIAL = {
    "Reforma Tributária": {
        "rotina": "ERP, cadastro fiscal, precificação, contratos, crédito tributário, financeiro e TI",
        "impacto": "preço, margem, crédito, capital de giro e previsibilidade da transição",
        "cena": "Uma empresa trata a mudança como tema apenas fiscal e descobre depois que o impacto estava no cadastro, no contrato e no caixa.",
        "decisao": "simular cenários, revisar contratos e testar sistemas antes que o impacto chegue ao resultado",
    },
    "Contencioso Tributário": {
        "rotina": "CND, dívida ativa, garantias, execução fiscal, jurídico, financeiro e negociação com credores",
        "impacto": "caixa, regularidade fiscal, financiamento, licitação, M&A e capacidade de pagamento",
        "cena": "A empresa olha apenas para o desconto ou para a tese, mas o problema aparece quando uma CND, uma garantia ou um bloqueio trava a operação.",
        "decisao": "priorizar passivos críticos, medir efeito no caixa e validar a estratégia antes de aderir ou litigar",
    },
    "Tributário Consultivo": {
        "rotina": "cadastro fiscal, nota fiscal, obrigação acessória, apuração, ERP, compras, fiscal e financeiro",
        "impacto": "risco fiscal, crédito tributário, margem, preço e retrabalho operacional",
        "cena": "O erro não nasce na autuação. Nasce quando cadastro, documento fiscal, compra e apuração deixam de conversar.",
        "decisao": "revisar dados críticos, priorizar itens de maior impacto e integrar fiscal, TI, compras e financeiro",
    },
    "Trabalhista Empresarial": {
        "rotina": "RH, DP, liderança, jornada, contratos, políticas internas, terceiros e documentação de prova",
        "impacto": "passivo trabalhista, cultura, custo operacional, previsibilidade e reputação interna",
        "cena": "A rotina parece resolvida no dia a dia, até que a empresa precisa provar jornada, autonomia, treinamento ou conduta de liderança.",
        "decisao": "revisar práticas, alinhar líderes e documentar a rotina antes do conflito aparecer",
    },
    "LGPD, Tecnologia e Compliance": {
        "rotina": "atendimento, marketing, WhatsApp comercial, fornecedores, TI, segurança da informação e governança de dados",
        "impacto": "reputação, sanções, continuidade operacional, confiança do cliente e resposta a incidentes",
        "cena": "O dado coletado em uma venda, campanha ou atendimento pode virar risco quando não há controle sobre finalidade, acesso e fornecedor.",
        "decisao": "mapear fluxos de dados, revisar fornecedores e definir resposta rápida para incidentes",
    },
    "Societário, M&A e Governança": {
        "rotina": "acordo de sócios, governança, documentação societária, captação, due diligence e conselho",
        "impacto": "valuation, entrada de investidor, conflito societário, sucessão e crescimento",
        "cena": "O comprador não olha só faturamento. Ele desconta risco quando encontra documentos frágeis, governança informal ou passivos escondidos.",
        "decisao": "organizar documentos, clarear regras societárias e tratar governança como ativo de crescimento",
    },
    "Cível Empresarial e Contratos": {
        "rotina": "contratos, compras, fornecedores, cobrança, marketplaces, comercial, operação e atendimento ao cliente",
        "impacto": "margem, inadimplência, continuidade operacional, responsabilidade na cadeia e preservação de ativos",
        "cena": "O contrato parece formalidade até a cadeia falhar, o fornecedor romper, o cliente não pagar ou a margem desaparecer.",
        "decisao": "revisar cláusulas críticas, garantias, prazos, responsabilidades e plano de saída da relação",
    },
    "Legal Ops": {
        "rotina": "carteira contenciosa, contratos, depósitos judiciais, dashboards, KPIs, orçamento jurídico e board",
        "impacto": "eficiência jurídica, recuperação de valores, previsibilidade, custo e tomada de decisão",
        "cena": "O jurídico deixa dinheiro e informação parados quando não transforma processos, contratos e depósitos em dados para decisão.",
        "decisao": "estruturar indicadores, priorizar carteira e levar visão executiva para o board",
    },
}


def safe_topic(title: str) -> str:
    text = re.sub(r"\s+[-|–]\s+[^-|–]{2,90}$", "", text_norm(title))
    text = re.sub(r"^(Exclusivo|Opinião|Análise|Entenda|Veja|Saiba)[:\s-]+", "", text, flags=re.I)
    if len(text) > 110:
        text = text[:107].rstrip() + "..."
    return text or "a atualização monitorada"


def editorial_profile(area: str) -> Dict[str, str]:
    return AREA_EDITORIAL.get(area) or {
        "rotina": "contratos, operação, financeiro, jurídico e governança",
        "impacto": "risco, caixa, margem, reputação e tomada de decisão",
        "cena": "A notícia só importa para a empresa quando altera uma rotina, um controle, um contrato ou uma decisão.",
        "decisao": "validar impacto prático, priorizar riscos e transformar o tema em ação de negócio",
    }


def agenda_for(area: str, title: str) -> str:
    topic = safe_topic(title)
    p = editorial_profile(area)
    # Títulos com cara de pauta AFA: menos "notícia", mais rotina empresarial.
    if area == "Reforma Tributária":
        return f"{topic}: o impacto que pode chegar ao ERP, ao contrato e ao caixa"
    if area == "Contencioso Tributário":
        return f"{topic}: quando o risco fiscal deixa de ser processo e vira decisão de caixa"
    if area == "Tributário Consultivo":
        return f"{topic}: o risco fiscal que pode nascer na rotina operacional"
    if area == "Trabalhista Empresarial":
        return f"{topic}: o detalhe de RH que pode virar passivo sem prova"
    if area == "LGPD, Tecnologia e Compliance":
        return f"{topic}: o risco de dados que aparece no atendimento, no marketing ou no fornecedor"
    if area == "Societário, M&A e Governança":
        return f"{topic}: por que governança também pesa no valor da empresa"
    if area == "Cível Empresarial e Contratos":
        return f"{topic}: o contrato ou a cobrança que pode afetar margem e continuidade"
    if area == "Legal Ops":
        return f"{topic}: como transformar risco jurídico em dado para decisão"
    return f"{topic}: o que muda na rotina empresarial e merece validação jurídica"


def business_impact_for(area: str, title: str) -> str:
    p = editorial_profile(area)
    topic = safe_topic(title)
    return (
        f"A atualização sobre {topic} deve ser lida pelo impacto prático em {p['rotina']}. "
        f"O ponto empresarial é medir efeito em {p['impacto']}, antes de tratar o tema apenas como notícia jurídica."
    )


def angle_for(area: str, title: str) -> str:
    p = editorial_profile(area)
    topic = safe_topic(title)
    return (
        f"Cena AFA: {p['cena']} A pauta deve partir de {topic} para mostrar onde o risco nasce, "
        f"como ele se espalha pela operação e qual decisão a empresa precisa tomar: {p['decisao']}."
    )


def validation_question_for(area: str, title: str) -> str:
    topic = safe_topic(title)
    return (
        f"Sobre {topic}: o fato está vigente, a fonte é suficiente, há aplicabilidade para empresas brasileiras "
        f"e existe algum ponto técnico que limite uma publicação imediata pelo AFA?"
    )


def source_summary_for(source_name: str, title: str, area: str) -> str:
    p = editorial_profile(area)
    topic = safe_topic(title)
    return (
        f"{source_name} publicou atualização sobre {topic}. Para o AFA, o valor editorial está em traduzir "
        f"o fato para a rotina da empresa: {p['rotina']}. Validar a fonte original antes de publicar."
    )

GOOGLE_NEWS_QUERIES = [
    "reforma tributária CBS IBS split payment empresas",
    "PGFN transação tributária CND dívida ativa empresas",
    "Receita Federal norma tributária empresas",
    "STJ decisão empresas contratos recuperação de crédito",
    "STF julgamento tributário empresas",
    "TST jornada pejotização terceirização empresas",
    "ANPD LGPD sanção dados pessoais empresas",
    "CVM governança M&A mercado de capitais empresas",
    "contratos empresariais fornecedores inadimplência",
    "Legal Ops jurídico empresas dashboard indicadores",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_norm(value: str) -> str:
    value = value or ""
    return re.sub(r"\s+", " ", value).strip()


def md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def parse_date_value(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # ISO comum: 2026-07-02T10:20:00Z
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # RFC comum em RSS: Wed, 02 Jul 2026 13:20:00 GMT
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Formato brasileiro simples: 02/07/2026 ou 02/07/2026 10:20
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", raw)
    if match:
        day, month, year, hour, minute = match.groups()
        return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=timezone.utc)

    # Fallback: tenta usar o parser interno do feedparser
    try:
        parsed = feedparser._parse_date(raw)  # type: ignore[attr-defined]
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass

    return None


def parse_feed_date(entry) -> Optional[str]:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    for key in ["published", "updated", "created"]:
        dt = parse_date_value(entry.get(key))
        if dt:
            return dt.isoformat()
    return None


def is_recent_iso(iso_value: Optional[str]) -> bool:
    dt = parse_date_value(iso_value)
    if not dt:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    return dt >= cutoff


def is_noise(title: str, url: str = "", summary: str = "") -> bool:
    content = f"{title} {url} {summary}".lower()
    return any(term in content for term in EXCLUDED_TERMS)


def supabase_request(method: str, path: str, *, params=None, json=None, extra_headers=None):
    url = f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}"
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    response = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {method} {path} falhou: {response.status_code} {response.text[:500]}")
    if response.text:
        return response.json()
    return None


def create_fetch_run(run_type: str = "scheduled") -> str:
    data = supabase_request(
        "POST",
        "fetch_runs",
        json={"run_type": run_type, "status": "Rodando", "started_at": now_iso()},
        extra_headers={"Prefer": "return=representation"},
    )
    return data[0]["id"]


def finish_fetch_run(run_id: str, status: str, total_found: int, total_inserted: int, error_message: Optional[str] = None):
    payload = {
        "status": status,
        "finished_at": now_iso(),
        "total_found": total_found,
        "total_inserted": total_inserted,
        "error_message": error_message,
    }
    supabase_request("PATCH", "fetch_runs", params={"id": f"eq.{run_id}"}, json=payload)


def get_sources() -> List[Dict]:
    return supabase_request(
        "GET",
        "sources",
        params={"active": "eq.true", "select": "id,name,url,rss_url,type,priority_area,keywords"},
    ) or []


def url_exists(url: str) -> Optional[str]:
    rows = supabase_request("GET", "news_items", params={"url": f"eq.{url}", "select": "id"}) or []
    if rows:
        return rows[0]["id"]
    return None


def insert_news(item: Dict) -> Optional[str]:
    existing_id = url_exists(item["url"])
    if existing_id:
        return None
    data = supabase_request(
        "POST",
        "news_items",
        json=item,
        extra_headers={"Prefer": "return=representation"},
    )
    return data[0]["id"] if data else None


def insert_analysis(news_item_id: str, area: str, title: str):
    payload = {
        "news_item_id": news_item_id,
        "business_impact": business_impact_for(area, title),
        "affected_routine": AFFECTED_ROUTINE.get(area, editorial_profile(area)["rotina"]),
        "suggested_agenda": agenda_for(area, title),
        "suggested_angle": angle_for(area, title),
        "validation_question": validation_question_for(area, title),
        "fast_publish_risk": "Risco de publicar rápido demais: tratar a atualização como regra definitiva sem confirmar vigência, alcance, exceções e aderência ao público empresarial do AFA.",
        "lawyer_status": "Pendente",
    }
    supabase_request("POST", "editorial_analysis", json=payload, extra_headers={"Prefer": "return=minimal"})


def matches_keywords(title: str, summary: str = "", source_keywords: str = "") -> bool:
    content = f"{title} {summary}".lower()
    keywords = GLOBAL_KEYWORDS[:]
    if source_keywords:
        keywords.extend([k.strip().lower() for k in source_keywords.split(",") if k.strip()])
    return any(k.lower() in content for k in keywords)


def classify_area(title: str, summary: str, source_area: Optional[str] = None) -> str:
    content = f"{title} {summary}".lower()
    best_area = source_area or "Jurídico Empresarial"
    best_score = 0
    for area, words in CATEGORY_RULES.items():
        score = sum(1 for word in words if word.lower() in content)
        if score > best_score:
            best_area = area
            best_score = score
    return best_area


def priority_for(area: str, title: str, source_type: str = "") -> str:
    text = title.lower()
    high_terms = ["lei", "decreto", "portaria", "instrução normativa", "resolução", "edital", "stf", "stj", "tst", "pgfn", "receita federal", "anpd", "cnd", "reforma tributária", "split payment"]
    if area in ["Reforma Tributária", "Contencioso Tributário"]:
        return "Alta"
    if source_type == "oficial" and any(term in text for term in high_terms):
        return "Alta"
    if any(term in text for term in high_terms):
        return "Alta"
    return "Média"


def channel_for(area: str, priority: str, title: str) -> str:
    text = title.lower()
    if priority == "Alta" and area in ["Reforma Tributária", "Contencioso Tributário", "Tributário Consultivo"]:
        return "Newsletter"
    if "guia" in text or "como" in text or "entenda" in text:
        return "Instagram carrossel"
    if area in ["Societário, M&A e Governança", "Legal Ops"]:
        return "LinkedIn"
    if priority == "Alta":
        return "LinkedIn"
    return "Stories"


def clean_google_title(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def extract_jsonld_dates(soup: BeautifulSoup) -> Optional[datetime]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key in ["datePublished", "dateCreated", "dateModified", "uploadDate"]:
                    dt = parse_date_value(item.get(key))
                    if dt:
                        return dt
                for value in item.values():
                    if isinstance(value, (dict, list)):
                        stack.extend(value if isinstance(value, list) else [value])
    return None


def extract_published_date_from_html(html: str) -> Optional[datetime]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        {"property": "article:published_time"},
        {"property": "og:published_time"},
        {"name": "date"},
        {"name": "pubdate"},
        {"name": "publishdate"},
        {"name": "timestamp"},
        {"name": "DC.date.issued"},
        {"itemprop": "datePublished"},
        {"itemprop": "dateCreated"},
        {"itemprop": "dateModified"},
    ]
    for attrs in selectors:
        tag = soup.find("meta", attrs=attrs)
        if tag:
            dt = parse_date_value(tag.get("content"))
            if dt:
                return dt
    for time_tag in soup.find_all("time"):
        dt = parse_date_value(time_tag.get("datetime") or time_tag.get_text(" "))
        if dt:
            return dt
    dt = extract_jsonld_dates(soup)
    if dt:
        return dt
    # Último recurso: procura uma data BR no texto próximo ao topo.
    top_text = text_norm(soup.get_text(" "))[:2500]
    return parse_date_value(top_text)


def get_article_date(url: str) -> Optional[datetime]:
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        response.raise_for_status()
        return extract_published_date_from_html(response.text)
    except Exception:
        return None


def collect_from_google_news() -> List[Dict]:
    collected = []
    for query in GOOGLE_NEWS_QUERIES:
        feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:MAX_ITEMS_PER_GOOGLE_QUERY]:
                title = text_norm(clean_google_title(entry.get("title", "")))
                link = entry.get("link", "")
                published_at = parse_feed_date(entry)
                summary = text_norm(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" "))
                if not title or not link:
                    continue
                if not published_at or not is_recent_iso(published_at):
                    print(f"Ignorada por data antiga/ausente: {title[:80]}")
                    continue
                if is_noise(title, link, summary):
                    print(f"Ignorada por ruído: {title[:80]}")
                    continue
                if not matches_keywords(title, summary, ""):
                    continue
                source_name = "Google News"
                try:
                    source_name = entry.source.title or source_name
                except Exception:
                    pass
                area = classify_area(title, summary, None)
                priority = priority_for(area, title, "portal")
                collected.append({
                    "source_id": None,
                    "title": title,
                    "url": link,
                    "source_name": source_name,
                    "published_at": published_at,
                    "summary": summary[:700] if summary else source_summary_for(source_name, title, area),
                    "detected_area": area,
                    "priority": priority,
                    "suggested_channel": channel_for(area, priority, title),
                    "status": "Nova",
                    "content_hash": md5(link),
                })
        except Exception as exc:
            print(f"Aviso: falha ao buscar Google News para '{query}': {exc}")
        time.sleep(1)
    return collected


def is_probably_article(url: str, title: str, source_url: str) -> bool:
    if not url or not title or len(title) < 25:
        return False
    if is_noise(title, url):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        return False
    bad_parts = ["/login", "/signin", "/cadastro", "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "whatsapp", "mailto:"]
    if any(part in url.lower() for part in bad_parts):
        return False
    if url.rstrip("/") == source_url.rstrip("/"):
        return False
    return True


def collect_from_page(source: Dict) -> List[Dict]:
    source_url = source.get("url") or ""
    items = []
    try:
        response = requests.get(source_url, headers=HTTP_HEADERS, timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        seen = set()
        candidates = []
        for link_tag in soup.find_all("a", href=True):
            title = text_norm(link_tag.get_text(" "))
            url = urljoin(source_url, link_tag.get("href"))
            url = url.split("#")[0]
            if url in seen:
                continue
            seen.add(url)
            if not is_probably_article(url, title, source_url):
                continue
            if not matches_keywords(title, "", source.get("keywords") or ""):
                continue
            candidates.append((title, url))
            if len(candidates) >= 12:
                break

        for title, url in candidates:
            published_dt = get_article_date(url)
            if not published_dt:
                print(f"Ignorada sem data publicada: {source.get('name')} | {title[:80]}")
                continue
            published_at = published_dt.isoformat()
            if not is_recent_iso(published_at):
                print(f"Ignorada por ser antiga: {source.get('name')} | {published_at} | {title[:80]}")
                continue
            area = classify_area(title, "", source.get("priority_area"))
            priority = priority_for(area, title, source.get("type") or "")
            items.append({
                "source_id": source.get("id"),
                "title": title[:500],
                "url": url,
                "source_name": source.get("name") or "Fonte monitorada",
                "published_at": published_at,
                "summary": source_summary_for(source.get('name') or 'Fonte monitorada', title, area),
                "detected_area": area,
                "priority": priority,
                "suggested_channel": channel_for(area, priority, title),
                "status": "Nova",
                "content_hash": md5(url),
            })
            if len(items) >= MAX_ITEMS_PER_PAGE_SOURCE:
                break
            time.sleep(0.3)
    except Exception as exc:
        print(f"Aviso: falha ao buscar página {source.get('name')}: {exc}")
    return items


def collect_from_rss(source: Dict) -> List[Dict]:
    rss_url = source.get("rss_url")
    if not rss_url:
        return []
    items = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:12]:
            title = text_norm(entry.get("title", ""))
            link = entry.get("link", "")
            summary = text_norm(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" "))
            published_at = parse_feed_date(entry)
            if not title or not link:
                continue
            if not published_at or not is_recent_iso(published_at):
                continue
            if is_noise(title, link, summary):
                continue
            if not matches_keywords(title, summary, source.get("keywords") or ""):
                continue
            area = classify_area(title, summary, source.get("priority_area"))
            priority = priority_for(area, title, source.get("type") or "")
            items.append({
                "source_id": source.get("id"),
                "title": title[:500],
                "url": link,
                "source_name": source.get("name") or "RSS",
                "published_at": published_at,
                "summary": summary[:700] if summary else source_summary_for(source.get('name') or 'RSS', title, area),
                "detected_area": area,
                "priority": priority,
                "suggested_channel": channel_for(area, priority, title),
                "status": "Nova",
                "content_hash": md5(link),
            })
    except Exception as exc:
        print(f"Aviso: falha ao buscar RSS {source.get('name')}: {exc}")
    return items


def dedupe(items: Iterable[Dict]) -> List[Dict]:
    seen = set()
    result = []
    for item in items:
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    run_type = "manual_or_scheduled"
    run_id = create_fetch_run(run_type)
    total_found = 0
    total_inserted = 0
    try:
        sources = get_sources()
        all_items = []

        print(f"Filtro de atualidade: últimas {MAX_AGE_HOURS} horas")
        print(f"Fontes ativas: {len(sources)}")
        for source in sources:
            all_items.extend(collect_from_rss(source))
            all_items.extend(collect_from_page(source))
            time.sleep(0.7)

        all_items.extend(collect_from_google_news())
        all_items = dedupe(all_items)
        total_found = len(all_items)
        print(f"Notícias candidatas recentes encontradas: {total_found}")

        for item in all_items:
            try:
                if not is_recent_iso(item.get("published_at")):
                    continue
                news_id = insert_news(item)
                if news_id:
                    insert_analysis(news_id, item.get("detected_area") or "Jurídico Empresarial", item.get("title") or "")
                    total_inserted += 1
                    print(f"Inserida: {item['title'][:90]}")
            except Exception as exc:
                print(f"Aviso: falha ao inserir item {item.get('url')}: {exc}")

        finish_fetch_run(run_id, "Concluído", total_found, total_inserted)
        print(f"Concluído. Recentes encontradas: {total_found}. Inseridas: {total_inserted}.")
    except Exception as exc:
        finish_fetch_run(run_id, "Erro", total_found, total_inserted, str(exc))
        raise


if __name__ == "__main__":
    main()
