import hashlib
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Erro: SUPABASE_URL e SUPABASE_SERVICE_KEY precisam estar cadastrados nos secrets do GitHub.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarJuridicoAFA/1.0; +https://afanews.github.io/radar-juridico-afa/)"
}

GLOBAL_KEYWORDS = [
    "reforma tributária", "cbs", "ibs", "split payment", "imposto seletivo",
    "pgfn", "transação tributária", "dívida ativa", "cnd", "execução fiscal",
    "receita federal", "carf", "stf", "stj", "tst", "tributário", "icms", "iss",
    "pis", "cofins", "irpj", "csll", "lucro presumido", "per/dcomp", "ncm", "cfop",
    "trabalhista", "jornada", "pejotização", "terceirização", "sindicato", "mte",
    "anpd", "lgpd", "dados pessoais", "privacidade", "incidente de segurança",
    "cvm", "societário", "m&a", "fusão", "aquisição", "governança", "sócios",
    "contrato", "fornecedor", "recuperação de crédito", "inadimplência", "cobrança",
    "empresa", "empresas", "pequenas empresas", "médias empresas", "negócios",
]

CATEGORY_RULES = {
    "Reforma Tributária": ["reforma tributária", "cbs", "ibs", "split payment", "imposto seletivo", "iva dual"],
    "Contencioso Tributário": ["pgfn", "dívida ativa", "cnd", "execução fiscal", "transação tributária", "protesto de cda", "carf", "auto de infração"],
    "Tributário Consultivo": ["receita federal", "tributário", "icms", "iss", "pis", "cofins", "irpj", "csll", "per/dcomp", "ncm", "cfop", "obrigação acessória", "lucro presumido"],
    "Trabalhista Empresarial": ["tst", "mte", "trabalhista", "jornada", "pejotização", "terceirização", "vínculo de emprego", "controle de ponto", "sindicato", "nr-1"],
    "LGPD, Tecnologia e Compliance": ["anpd", "lgpd", "dados pessoais", "privacidade", "incidente de segurança", "vazamento de dados", "compliance", "inteligência artificial"],
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
        "business_impact": BUSINESS_IMPACT.get(area, "Impacto empresarial a validar."),
        "affected_routine": AFFECTED_ROUTINE.get(area, "rotina empresarial a validar"),
        "suggested_agenda": AGENDA_TEMPLATE.get(area, "Pauta empresarial a validar"),
        "suggested_angle": "Transformar o fato novo em leitura de negócio: onde o risco nasce, como se espalha e qual decisão a empresa precisa tomar.",
        "validation_question": "O fato está vigente, a interpretação está correta e há segurança técnica para publicar agora?",
        "fast_publish_risk": "Risco de publicar sem confirmar vigência, alcance da norma/decisão ou aplicabilidade ao público empresarial do AFA.",
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
    # Google News costuma retornar "Título - Fonte". Mantemos o título principal.
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def parse_feed_date(entry) -> Optional[str]:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def collect_from_google_news() -> List[Dict]:
    collected = []
    for query in GOOGLE_NEWS_QUERIES:
        feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:8]:
                title = text_norm(clean_google_title(entry.get("title", "")))
                link = entry.get("link", "")
                if not title or not link:
                    continue
                source_name = "Google News"
                try:
                    source_name = entry.source.title or source_name
                except Exception:
                    pass
                summary = text_norm(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" "))
                area = classify_area(title, summary, None)
                priority = priority_for(area, title, "portal")
                collected.append({
                    "source_id": None,
                    "title": title,
                    "url": link,
                    "source_name": source_name,
                    "published_at": parse_feed_date(entry) or now_iso(),
                    "summary": summary[:700] if summary else "Notícia encontrada via Google News RSS. Validar fonte original antes de publicar.",
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
            area = classify_area(title, "", source.get("priority_area"))
            priority = priority_for(area, title, source.get("type") or "")
            items.append({
                "source_id": source.get("id"),
                "title": title[:500],
                "url": url,
                "source_name": source.get("name") or "Fonte monitorada",
                "published_at": now_iso(),
                "summary": "Notícia encontrada na página pública da fonte. Validar o conteúdo original antes de publicar.",
                "detected_area": area,
                "priority": priority,
                "suggested_channel": channel_for(area, priority, title),
                "status": "Nova",
                "content_hash": md5(url),
            })
            if len(items) >= 10:
                break
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
            if not title or not link:
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
                "published_at": parse_feed_date(entry) or now_iso(),
                "summary": summary[:700] if summary else "Notícia encontrada via RSS. Validar o conteúdo original antes de publicar.",
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

        print(f"Fontes ativas: {len(sources)}")
        for source in sources:
            all_items.extend(collect_from_rss(source))
            all_items.extend(collect_from_page(source))
            time.sleep(0.7)

        all_items.extend(collect_from_google_news())
        all_items = dedupe(all_items)
        total_found = len(all_items)
        print(f"Notícias candidatas encontradas: {total_found}")

        for item in all_items:
            try:
                news_id = insert_news(item)
                if news_id:
                    insert_analysis(news_id, item.get("detected_area") or "Jurídico Empresarial", item.get("title") or "")
                    total_inserted += 1
                    print(f"Inserida: {item['title'][:90]}")
            except Exception as exc:
                print(f"Aviso: falha ao inserir item {item.get('url')}: {exc}")

        finish_fetch_run(run_id, "Concluído", total_found, total_inserted)
        print(f"Concluído. Encontradas: {total_found}. Inseridas: {total_inserted}.")
    except Exception as exc:
        finish_fetch_run(run_id, "Erro", total_found, total_inserted, str(exc))
        raise


if __name__ == "__main__":
    main()
