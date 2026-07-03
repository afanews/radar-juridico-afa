import os
import sys
from datetime import datetime, timezone

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Erro: SUPABASE_URL ou SUPABASE_SERVICE_KEY não configurados.")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def supabase_delete_all(table: str) -> None:
    # id=not.is.null funciona como filtro universal, pois id é obrigatório nas tabelas.
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=not.is.null"
    response = requests.delete(url, headers=HEADERS, timeout=60)
    if response.status_code not in (200, 204):
        raise RuntimeError(
            f"Falha ao apagar tabela {table}: {response.status_code} {response.text}"
        )


def supabase_insert(table: str, payload: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"Falha ao inserir log em {table}: {response.status_code} {response.text}"
        )


def main() -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    print("Iniciando limpeza total de notícias do Radar...")

    # Primeiro apaga análises vinculadas, depois notícias.
    supabase_delete_all("editorial_analysis")
    print("editorial_analysis apagada.")

    supabase_delete_all("news_items")
    print("news_items apagada.")

    finished_at = datetime.now(timezone.utc).isoformat()
    try:
        supabase_insert(
            "fetch_runs",
            {
                "run_type": "clear_all_news",
                "started_at": started_at,
                "finished_at": finished_at,
                "status": "Success",
                "total_found": 0,
                "total_inserted": 0,
                "error_message": "Limpeza manual executada pelo GitHub Actions.",
            },
        )
    except Exception as exc:
        # A limpeza já aconteceu; falha de log não deve fazer o job falhar.
        print(f"Aviso: limpeza concluída, mas falhou ao registrar log: {exc}")

    print("Limpeza concluída com sucesso.")


if __name__ == "__main__":
    main()
