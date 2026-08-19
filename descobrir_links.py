import argparse
import base64
import html as html_stdlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
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


DOMINIOS_POR_LOJA = {
    "Amazon": "amazon.com.br",
    "KaBuM": "kabum.com.br",
    "Pichau": "pichau.com.br",
    "Terabyte": "terabyteshop.com.br",
}

PICHAU_SITEMAP_URL = "https://www.pichau.com.br/media/sitemap.xml"
_URLS_SITEMAP_PICHAU = None


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
    # Consultas longas fazem a busca da Pichau exigir palavras que nem sempre
    # aparecem no título. A identidade completa continua sendo validada depois.
    return item["nome"].strip()


def termo_de_identidade(item):
    # A busca usa um texto curto, mas a validação mantém categoria, capacidade,
    # frequência e demais detalhes que distinguem variantes parecidas.
    return f"{item['nome']} {item['categoria']}".strip()


def identidade_extra_compativel(item, texto_candidato):
    identidade = tokens(item.get("identidade", ""))
    return not identidade or identidade.issubset(tokens(texto_candidato))


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
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
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
    referencia = tokens(termo_de_identidade(item))
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


def url_de_busca_externa(loja, item):
    dominios = {
        "Amazon": "amazon.com.br",
        "KaBuM": "kabum.com.br",
        "Pichau": "pichau.com.br",
        "Terabyte": "terabyteshop.com.br",
    }
    consulta = f"site:{dominios[loja]} {termo_de_busca(item)}"
    return f"https://www.bing.com/search?q={quote_plus(consulta)}"


def decodificar_url_bing(valor):
    if not valor:
        return None
    valor = unquote(valor)
    if valor.startswith(("http://", "https://")):
        return valor
    if valor.startswith("a1"):
        valor = valor[2:]
    try:
        valor += "=" * (-len(valor) % 4)
        decodificado = base64.urlsafe_b64decode(valor).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return decodificado if decodificado.startswith("http") else None


def destino_de_link_externo(href):
    try:
        partes = urlsplit(href or "")
    except ValueError:
        return None
    host = (partes.hostname or "").lower()
    parametros = parse_qs(partes.query)
    if "bing.com" in host:
        return decodificar_url_bing((parametros.get("u") or [""])[0])
    if "google." in host:
        return (parametros.get("q") or [None])[0]
    if "duckduckgo.com" in host:
        return (parametros.get("uddg") or [None])[0]
    return href


def adicionar_candidato(melhores, loja, item, href, representacao):
    canonica = url_canonica_produto(loja, href)
    if not canonica:
        return
    caminho = normalizar(urlsplit(canonica).path)
    if any(
        termo in caminho
        for termo in (
            "kit upgrade", "computador", "pc gamer", "workstation",
            "open box",
        )
    ):
        return

    if loja != "Amazon":
        categoria = normalizar(item.get("categoria", ""))
        if "memoria ram" in categoria:
            termos_esperados = ("memoria",)
        elif "ryzen" in categoria or "processador" in categoria:
            termos_esperados = ("processador",)
        else:
            termos_esperados = ("placa de video", "vga")
        if not any(termo in caminho for termo in termos_esperados):
            return

    score = pontuar_identidade(
        item, f"{representacao} {urlsplit(canonica).path}"
    )
    if score < 45:
        return
    anterior = melhores.get(canonica)
    if anterior is None or score > anterior:
        melhores[canonica] = score


def candidatos_do_html(driver, loja, item, melhores):
    try:
        html = driver.page_source or ""
    except WebDriverException:
        return
    if not html:
        return

    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        adicionar_candidato(
            melhores,
            loja,
            item,
            destino_de_link_externo(link.get("href", "")),
            f"{link.get_text(' ', strip=True)} {link.get('title', '')}",
        )

    # Algumas vitrines deixam as URLs somente no estado JSON da aplicação.
    for correspondencia in re.finditer(
        r'https?:\\?/\\?/[^"]+|"(?:url_key|urlKey|request_path)"\s*:\s*"([^"]+)"',
        html,
        re.IGNORECASE,
    ):
        bruto = correspondencia.group(1) or correspondencia.group(0)
        bruto = bruto.replace("\\/", "/").strip('"')
        try:
            tem_esquema = bool(urlsplit(bruto).scheme)
        except ValueError:
            continue
        if not tem_esquema:
            bruto = (
                f"https://www.{DOMINIOS_POR_LOJA[loja]}/"
                f"{bruto.lstrip('/')}"
            )
        adicionar_candidato(melhores, loja, item, bruto, bruto)


def carregar_urls_sitemap_pichau():
    """Baixa uma única vez o catálogo público indicado no robots.txt."""
    global _URLS_SITEMAP_PICHAU
    if _URLS_SITEMAP_PICHAU is not None:
        return _URLS_SITEMAP_PICHAU

    resposta = requests.get(
        PICHAU_SITEMAP_URL,
        timeout=60,
        headers={
            "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    resposta.raise_for_status()
    _URLS_SITEMAP_PICHAU = [
        html_stdlib.unescape(url.strip())
        for url in re.findall(r"<loc>(.*?)</loc>", resposta.text, re.I | re.S)
        if "pichau.com.br/" in url
    ]
    if not _URLS_SITEMAP_PICHAU:
        raise RuntimeError("O sitemap público da Pichau veio vazio")
    print(f"    Sitemap da Pichau carregado: {len(_URLS_SITEMAP_PICHAU)} URLs")
    return _URLS_SITEMAP_PICHAU


def candidatos_do_sitemap_pichau(item, melhores):
    categoria = normalizar(item.get("categoria", ""))
    if "memoria ram" in categoria:
        prefixo = "/memoria-"
    elif "ryzen" in categoria or "processador" in categoria:
        prefixo = "/processador-"
    else:
        prefixo = "/placa-de-video-"

    for url in carregar_urls_sitemap_pichau():
        try:
            caminho = urlsplit(url).path.lower()
        except ValueError:
            continue
        # Evita kits, computadores completos e recomendações com o mesmo chip.
        if not caminho.startswith(prefixo):
            continue
        if not identidade_extra_compativel(item, caminho):
            continue
        adicionar_candidato(melhores, "Pichau", item, url, url)


def coletar_candidatos(driver, loja, item, limite=6):
    melhores = {}
    if loja == "Pichau":
        try:
            candidatos_do_sitemap_pichau(item, melhores)
        except (requests.RequestException, RuntimeError) as erro:
            print(f"    Falha ao consultar o sitemap da Pichau: {erro}")
        if melhores:
            return sorted(
                melhores.items(), key=lambda par: par[1], reverse=True
            )[:limite]

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

    for link in driver.find_elements(By.TAG_NAME, "a"):
        try:
            href = link.get_attribute("href") or ""
        except WebDriverException:
            continue
        adicionar_candidato(melhores, loja, item, href, texto_do_link(link))

    candidatos_do_html(driver, loja, item, melhores)

    if not melhores:
        busca_externa = url_de_busca_externa(loja, item)
        print(f"    Busca da loja sem resultado; tentando índice externo: {busca_externa}")
        try:
            driver.get(busca_externa)
        except TimeoutException:
            pass
        aguardar_conteudo_da_loja(driver, segundos=8)
        candidatos_do_html(driver, loja, item, melhores)

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
    if not identidade_extra_compativel(item, texto_produto):
        return None
    score_pagina = pontuar_identidade(item, texto_produto)
    if score_pagina < 45:
        return None

    oficial = None
    if loja == "Amazon":
        oficial, _ = verificar_vendedor_amazon(driver, texto_body)
    elif loja == "KaBuM":
        oficial, _ = verificar_vendedor_kabum(texto_body)
    if oficial is False:
        return None

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

    # O catálogo também funciona como a lista completa de itens monitorados.
    # Portanto, um produto sem URL descoberta ainda precisa aparecer com {}.
    for item in produtos:
        catalogo["produtos"].setdefault(item["nome"], {})
    salvar_catalogo(caminho_catalogo, catalogo)

    for loja in lojas:
        print(f"\n===== Descobrindo links da {loja} =====")
        encontrados = 0
        mantidos = 0
        ausentes = 0
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
                    encontrados += 1
                    print(f"    Encontrado: {resultado['url']} (score {resultado['score']})")
                elif loja in registros:
                    mantidos += 1
                    print("    Não redescoberto; mantendo o link anterior.")
                else:
                    ausentes += 1
                    print("    Nenhum resultado seguro encontrado.")
                salvar_catalogo(caminho_catalogo, catalogo)
                time.sleep(1)
        finally:
            try:
                navegador.quit()
            except WebDriverException:
                pass

        total_loja = sum(
            1
            for lojas_produto in catalogo["produtos"].values()
            if isinstance(lojas_produto, dict) and loja in lojas_produto
        )
        print(
            f"\nResumo {loja}: {encontrados} descobertos, {mantidos} mantidos, "
            f"{ausentes} ausentes e {total_loja} links no catálogo."
        )
        minimo_confiavel = {
            "Amazon": 2,
            "KaBuM": 2,
            "Pichau": 5,
            "Terabyte": 5,
        }[loja]
        if total_loja < minimo_confiavel:
            salvar_catalogo(caminho_catalogo, catalogo)
            raise RuntimeError(
                f"A descoberta da {loja} terminou com apenas {total_loja} "
                f"link(s), abaixo do mínimo seguro de {minimo_confiavel}; "
                "o job não será marcado como sucesso."
            )

        processadas = catalogo.setdefault("lojasProcessadas", [])
        if loja not in processadas:
            processadas.append(loja)
        salvar_catalogo(caminho_catalogo, catalogo)

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
