import logging

def parse_price(price_str: str) -> float | None:
    """Converte uma string de preço (ex: 'R$1.234,56') para float."""
    if not price_str:
        return None
    try:
        # Remove "R$", espaços, troca a vírgula por ponto e converte
        cleaned_price = price_str.replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(cleaned_price)
    except (ValueError, TypeError):
        logging.warning(f"Não foi possível extrair o preço de: {price_str}")
        return None