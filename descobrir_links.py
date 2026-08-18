import argparse
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from monitor_core import (
    CATALOGO_URLS_CAMINHO,
    LOJAS_VALIDAS,
    PRODUTOS,
    aguardar_conteudo_da_loja,
    analisar_disponibilidade,
    chave_texto,
    dominio_compativel_com_loja,
    iniciar_navegador,
    limpar_url_final_loja,
    verificar_vendedor_amazon,
    verificar_vendedor_kabum,
)


MARCAS = {
    "amd", "adata", "xpg", "corsair", "kingston", "gigabyte", "asus",
    "xfx", "asrock", "palit", "gainward", "msi",
}

VARIANTES = {
    "oc", "ice", "white", "branco", "black", "preto", "prime", "tuf",
    "swift", "mercury", "steel", "legend", "gaming", "infinity", "ventus",
    "python", "triple", "d35", "lpx", "fury", "beast",
}

ROTAS_NAO_PRODUTO_PICHAU = {
    "", "search", "hardware", "computadores", "marca", "categorias",
    "promocao", "monte-seu-pc", "minha-conta", "checkout", "carrinho",
}


def normalizar(valor):
    valor = unicodedata.normalize("NFKD", valor or "")
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    valor = re.sub(r"[^a-z0-9]+", " ", valor.lower()).strip()
    # As lojas alternam entre "16GB"/"16 GB" e "3200MHz"/"3200 MHz".
    return re.sub(r"\b(\d+)\s+(gb|mhz|ghz|tb)\b", r"\1\2", valor)


def tokens(valor):
    return set(normalizar(valor).split())


def termo_de_busca(item):
    return f"{item['nome']} {item.get('categoria', '')}".strip()


def url_de_busca(loja, termo):
    if loja == "Amazon":
        return f"https://www.amazon.com.br/s?k={quote_plus(termo)}"
    if loja == "KaBuM":
        slug = re.sub(r"[^a-z0-9]+", "-", normalizar(termo)).strip("-")
        return f"https://www.kabum.com.br/busca/{quote(slug)}"
    if loja == "Pichau":
        return f"https://www.pichau.com.br/search?q={quote_plus(termo)}"
    if loja == "Terabyte":
        return f"https://www.terabyteshop.com.br/busca?str={quote_plus(termo)}"
    raise ValueError(f"Loja desconhecida: {loja}")


def url_canonica_produto(loja, url):
    if not dominio_compativel_com_loja(loja, url):
        return None
    partes = urlsplit(url)
    caminho = partes.path.rstrip("/")

    if loja == "Amazon":
        asin = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", caminho, re.I)
        if not asin:
            return None
        return f"https://www.amazon.com.br/dp/{asin.group(1).upper()}"

    if loja in {"KaBuM", "Terabyte"}:
        if not re.search(r"/produto/\d+(?:/|$)", caminho, re.I):
            return None
        return urlunsplit((partes.scheme, partes.netloc, caminho, "", ""))

    primeiro_segmento = caminho.strip("/").split("/", 1)[0].lower()
    if primeiro_segmento in ROTAS_NAO_PRODUTO_PICHAU:
        return None
    return urlunsplit((partes.scheme, partes.netloc, caminho, "", ""))


def variantes_equivalentes(referencia, candidato, portugues, ingles):
    tem_referencia = portugues in referencia or ingles in referencia
    tem_candidato = portugues in candidato or ingles in candidato
    return tem_referencia == tem_candidato


def pontuar_identidade(item, texto_candidato):
    referencia = tokens(termo_de_busca(item))
    candidato = tokens(texto_candidato)
    if not referencia or not candidato:
        return -1

    obrigatorios = {
        token for token in referencia
        if any(c.isdigit() for c in token) or token in MARCAS or token in VARIANTES
    }
    # Cores em português/inglês são equivalentes.
    obrigatorios -= {"branco", "white", "preto", "black"}
    if not obrigatorios.issubset(candidato):
        return -1
    if not variantes_equivalentes(referencia, candidato, "branco", "white"):
        return -1
    if not variantes_equivalentes(referencia, candidato, "preto", "black"):
        return -1

    # Evita variantes próximas que representam produtos diferentes.
    for variante in ("oc", "ice", "triple", "tuf", "prime", "mercury"):
        if (variante in referencia) != (variante in candidato):
            return -1
    if "5700x" in referencia and "5700x3d" in candidato:
        return -1

    comuns = referencia & candidato
    cobertura = len(comuns) / len(referencia)
    precisao = len(comuns) / max(len(candidato), 1)
    return round((cobertura * 80) + (precisao * 20), 2)


def texto_do_link(elemento):
    partes = []
    for atributo in ("textContent", "title", "aria-label", "href"):
        try:
            valor = elemento.get_attribute(atributo)
        except WebDriverException:
            valor = ""
        if valor:
            partes.append(valor)
    return " ".join(partes)


def coletar_candidatos(driver, loja, item, limite=6):
    busca = url_de_busca(loja, termo_de_busca(item))
    print(f"    Busca: {busca}")
    try:
        driver.get(busca)
    except TimeoutException:
        pass
    aguardar_conteudo_da_loja(driver, segundos=8)

    try:
        WebDriverWait(driver, 10).until(
            lambda navegador: len(navegador.find_elements(By.TAG_NAME, "a")) > 5
        )
    except TimeoutException:
        pass

    melhores = {}
    for link in driver.find_elements(By.TAG_NAME, "a"):
        try:
            href = link.get_attribute("href") or ""
        except WebDriverException:
            continue
        canonica = url_canonica_produto(loja, href)
        if not canonica:
            continue
        representacao = f"{texto_do_link(link)} {urlsplit(canonica).path}"
        score = pontuar_identidade(item, representacao)
        if score < 45:
            continue
        anterior = melhores.get(canonica)
        if anterior is None or score > anterior:
            melhores[canonica] = score

    return sorted(melhores.items(), key=lambda par: par[1], reverse=True)[:limite]


def ler_texto_produto(driver):
    partes = []
    try:
        if driver.title:
            partes.append(driver.title)
    except WebDriverException:
        pass

    # Somente nome/título. O corpo contém produtos recomendados e pode incluir
    # variantes como OC, ICE ou White que não pertencem ao produto atual.
    for seletor in ("h1", "[itemprop='name']"):
        try:
            elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        except WebDriverException:
            elementos = []
        for elemento in elementos[:2]:
            try:
                texto = elemento.get_attribute("textContent") or elemento.text
            except WebDriverException:
                continue
            if texto:
                partes.append(texto[:5000])
    return " ".join(partes)


def avaliar_candidato(driver, loja, item, url, score_busca):
    try:
        driver.get(url)
    except TimeoutException:
        pass
    except WebDriverException:
        return None
    aguardar_conteudo_da_loja(driver, segundos=7)

    try:
        url_final = driver.current_url or url
        texto_body = driver.find_element(By.TAG_NAME, "body").text
    except WebDriverException:
        return None
    canonica = url_canonica_produto(loja, url_final)
    if not canonica:
        return None

    texto_produto = f"{ler_texto_produto(driver)} {urlsplit(canonica).path}"
    score_pagina = pontuar_identidade(item, texto_produto)
    if score_pagina < 45:
        return None

    oficial = None
    if loja == "Amazon":
        oficial, _ = verificar_vendedor_amazon(driver, texto_body)
    elif loja == "KaBuM":
        oficial, _ = verificar_vendedor_kabum(texto_body)

    disponibilidade = analisar_disponibilidade(texto_body)
    prioridade = score_pagina + min(score_busca, 100) / 10
    if oficial is True:
        prioridade += 30
    elif oficial is False:
        prioridade -= 15
    if disponibilidade is True:
        prioridade += 5
    elif disponibilidade is False:
        prioridade -= 2

    return {
        "url": limpar_url_final_loja(canonica),
        "score": round(score_pagina, 2),
        "vendedorOficialNaDescoberta": oficial,
        "disponivelNaDescoberta": disponibilidade,
        "prioridade": prioridade,
    }


def descobrir_url(driver, loja, item):
    candidatos = coletar_candidatos(driver, loja, item)
    if not candidatos:
        return None

    avaliados = []
    for url, score_busca in candidatos:
        resultado = avaliar_candidato(driver, loja, item, url, score_busca)
        if resultado:
            avaliados.append(resultado)
    if not avaliados:
        return None
    return max(avaliados, key=lambda registro: registro["prioridade"])


def carregar_catalogo(caminho):
    if not caminho.exists():
        return {"versao": 1, "produtos": {}}
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"versao": 1, "produtos": {}}
    if not isinstance(dados.get("produtos"), dict):
        dados["produtos"] = {}
    dados["versao"] = 1
    return dados


def salvar_catalogo(caminho, catalogo):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)


def executar(lojas, caminho_catalogo, limite_produtos=None):
    catalogo = carregar_catalogo(caminho_catalogo)
    produtos = PRODUTOS[:limite_produtos] if limite_produtos else PRODUTOS
    agora = datetime.now().astimezone().isoformat(timespec="seconds")

    for loja in lojas:
        print(f"\n===== Descobrindo links da {loja} =====")
        navegador = iniciar_navegador()
        try:
            for item in produtos:
                print(f"\n  {item['nome']}")
                try:
                    resultado = descobrir_url(navegador, loja, item)
                except WebDriverException as erro:
                    print(f"    Falha do navegador: {erro.__class__.__name__}")
                    resultado = None

                registros = catalogo["produtos"].setdefault(item["nome"], {})
                if resultado:
                    resultado.pop("prioridade", None)
                    resultado["descobertoEm"] = agora
                    registros[loja] = resultado
                    print(f"    Encontrado: {resultado['url']} (score {resultado['score']})")
                elif loja in registros:
                    print("    Não redescoberto; mantendo o link anterior.")
                else:
                    print("    Nenhum resultado seguro encontrado.")
                salvar_catalogo(caminho_catalogo, catalogo)
                time.sleep(1)
        finally:
            try:
                navegador.quit()
            except WebDriverException:
                pass

    catalogo["atualizadoEm"] = agora
    salvar_catalogo(caminho_catalogo, catalogo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loja", choices=tuple(LOJAS_VALIDAS.values()))
    parser.add_argument("--catalogo", type=Path, default=CATALOGO_URLS_CAMINHO)
    parser.add_argument("--limite-produtos", type=int)
    argumentos = parser.parse_args()
    loja_ambiente = os.environ.get("LOJA_ALVO", "").strip()
    loja = argumentos.loja or loja_ambiente
    lojas = (loja,) if loja else tuple(LOJAS_VALIDAS.values())
    executar(lojas, argumentos.catalogo, argumentos.limite_produtos)


if __name__ == "__main__":
    main()
