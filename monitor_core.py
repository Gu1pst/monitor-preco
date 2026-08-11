import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from time import perf_counter
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.util.retry import Retry


GOOGLE_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL", "").strip()
TIMEOUT_PAGINA_SEGUNDOS = 15
TIMEOUT_WEBHOOK_SEGUNDOS = 20
TIMEOUT_LOJA_SEGUNDOS = 18
TIMEOUT_PROMOTECH_CHROME_SEGUNDOS = 30
LOJAS_COM_VALIDACAO_DE_VENDEDOR = {"Amazon", "KaBuM"}

LOJAS_VALIDAS = {
    "amazon": "Amazon",
    "kabum": "KaBuM",
    "pichau": "Pichau",
    "terabyte": "Terabyte",
}

PRODUTOS = [
    {"categoria": "Ryzen 7 5700X", "precoMax": 900.00, "nome": "AMD Ryzen 7 5700X", "urlPromotech": "https://promotech.app.br/produtos/processador/modelo/stvux7zj"},
    {"categoria": "Memória RAM 16GB 3200MHz", "precoMax": 700.00, "nome": "ADATA XPG Gammix D35 16GB Branco", "urlPromotech": "https://promotech.app.br/produtos/memoria-ram/modelo/bxfnyqmq"},
    {"categoria": "Memória RAM 16GB 3200MHz", "precoMax": 700.00, "nome": "ADATA XPG Gammix D35 16GB Preto", "urlPromotech": "https://promotech.app.br/produtos/memoria-ram/modelo/j07q19ey"},
    {"categoria": "Memória RAM 16GB 3200MHz", "precoMax": 700.00, "nome": "Corsair Vengeance LPX 16GB Preto", "urlPromotech": "https://promotech.app.br/produtos/memoria-ram/modelo/rrye6ky7"},
    {"categoria": "Memória RAM 16GB 3200MHz", "precoMax": 700.00, "nome": "Kingston Fury Beast 16GB Preto KF432C16BB1/16", "urlPromotech": "https://promotech.app.br/produtos/memoria-ram/modelo/7op9shyp"},
    {"categoria": "Memória RAM 16GB 3200MHz", "precoMax": 700.00, "nome": "Kingston Fury Beast 16GB Preto KF432C16BB/16", "urlPromotech": "https://promotech.app.br/produtos/memoria-ram/modelo/fk07q2rg"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "Gigabyte RX 9060 XT 16GB Gaming OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/4x9dm8d4"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "Gigabyte RX 9060 XT 16GB Gaming OC ICE", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/kv7rix7p"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "ASUS RX 9060 XT 16GB Prime OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/zmdicmsq"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "XFX RX 9060 XT 16GB Swift White OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/477wijq6"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "ASRock RX 9060 XT 16GB Steel Legend OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/9mlqifpy"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "XFX RX 9060 XT 16GB Swift Triple Fan OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/outz1bfl"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "ASUS RX 9060 XT 16GB TUF OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/w61jqfhy"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "XFX RX 9060 XT 16GB Mercury OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/3sultokb"},
    {"categoria": "RX 9060 XT 16GB", "precoMax": 3000.00, "nome": "XFX RX 9060 XT 16GB Swift White Triple Fan OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/fubscl6a"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "Palit RTX 5060 Ti 16GB Infinity 3", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/620j23xx"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "Gainward RTX 5060 Ti 16GB Python III", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/a0j4png6"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "Palit RTX 5060 Ti 16GB Infinity 3 OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/dznzlwqx"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "ASUS RTX 5060 Ti 16GB TUF", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/m590gakb"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "ASUS RTX 5060 Ti 16GB TUF OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/2bleghqb"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "MSI RTX 5060 Ti 16GB Ventus 3X OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/gqrsje4y"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "ASUS RTX 5060 Ti 16GB Prime", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/lzc32cvp"},
    {"categoria": "RTX 5060 Ti 16GB", "precoMax": 3500.00, "nome": "ASUS RTX 5060 Ti 16GB Prime OC", "urlPromotech": "https://promotech.app.br/produtos/placa-de-video/modelo/sgxaixdw"},
]


PADRAO_VISTA = re.compile(r"R\$\s*([\d.]+,\d{2})\s*(?:à|a)\s+vista", re.IGNORECASE)
PADRAO_PARCELADO = re.compile(r"R\$\s*([\d.]+,\d{2})\s*parcelado", re.IGNORECASE)


class DesafioVercel(RuntimeError):
    pass


def criar_sessao():
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.7,
        # 429 da Vercel é um desafio, não uma falha transitória: não repetir.
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    sessao = requests.Session()
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    sessao.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/150.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }
    )
    return sessao


def normalizar_texto(valor):
    valor = unicodedata.normalize("NFKC", valor or "")
    return " ".join(valor.split())


def chave_texto(valor):
    valor = normalizar_texto(valor).lower()
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caractere)
    )


def detectar_versao_principal_chrome():
    versao_configurada = os.environ.get("CHROME_VERSION_MAIN", "").strip()
    if versao_configurada.isdigit():
        return int(versao_configurada)

    for nome in (
        "google-chrome-stable",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ):
        executavel = shutil.which(nome)
        if not executavel:
            continue

        try:
            resultado = subprocess.run(
                [executavel, "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        correspondencia = re.search(r"(\d+)\.", resultado.stdout)
        if correspondencia:
            return int(correspondencia.group(1))

    return None


def iniciar_navegador():
    versao_chrome = detectar_versao_principal_chrome()
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=pt-BR")
    options.add_argument("--window-size=1920,1080")

    if versao_chrome:
        # O headless inclui "HeadlessChrome" no User-Agent padrão. Usamos a
        # plataforma real do runner e a mesma versão principal do navegador.
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{versao_chrome}.0.0.0 Safari/537.36"
        )
        print(f"Chrome principal detectado: {versao_chrome}")
        navegador = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=versao_chrome,
        )
    else:
        print("Versão do Chrome não detectada; usando autodetecção.")
        navegador = uc.Chrome(options=options, use_subprocess=True)

    navegador.set_page_load_timeout(TIMEOUT_LOJA_SEGUNDOS)
    return navegador


def texto_do_elemento(driver, seletor):
    try:
        return driver.find_element(By.CSS_SELECTOR, seletor).text
    except WebDriverException:
        return ""


def aguardar_informacao_do_vendedor(driver):
    def informacao_apareceu(navegador):
        try:
            texto = chave_texto(navegador.find_element(By.TAG_NAME, "body").text)
        except WebDriverException:
            return False
        return any(
            termo in texto
            for termo in (
                "vendido",
                "robot check",
                "digite os caracteres",
                "nao sou um robo",
                "acesso negado",
            )
        )

    try:
        WebDriverWait(driver, 10).until(informacao_apareceu)
    except TimeoutException:
        pass


def verificar_vendedor_amazon(driver, texto_body):
    seletores_buybox = (
        "#tabular-buybox",
        "#merchant-info",
        "#shipsFromSoldByInsideBuyBox_feature_div",
        "#desktop_buybox",
    )
    texto_buybox = " ".join(texto_do_elemento(driver, seletor) for seletor in seletores_buybox)
    # Usa o bloco de compra atual para não confundir vendedores de outras ofertas da página.
    texto = chave_texto(texto_buybox if normalizar_texto(texto_buybox) else texto_body)

    enviado_vendido_juntos = re.search(
        r"enviado\s*/\s*vendido\s*:?\s*amazon\.com\.br", texto
    )
    enviado_amazon = re.search(
        r"enviado(?:\s+de|\s+por)?\s*:?\s*amazon\.com\.br", texto
    )
    vendido_amazon = re.search(
        r"vendido(?:\s+por)?\s*:?\s*amazon\.com\.br", texto
    )

    if enviado_vendido_juntos or (enviado_amazon and vendido_amazon):
        return True, "Enviado e vendido por Amazon.com.br"
    if "vendido por" in texto or "enviado de" in texto or "enviado por" in texto:
        return False, "Marketplace: o envio e/ou a venda não são da Amazon.com.br"
    return None, "A Amazon não exibiu as informações do vendedor"


def verificar_vendedor_kabum(texto_body):
    texto = chave_texto(texto_body)
    if re.search(r"vendido\s+e\s+entregue\s+por\s*:?\s*kabum!?", texto):
        return True, "Vendido e entregue por KaBuM!"
    if re.search(r"vendido\s+e\s+entregue\s+por", texto):
        return False, "Marketplace: não é vendido e entregue pela KaBuM!"
    return None, "A KaBuM não exibiu as informações do vendedor"


def verificar_vendedor_oficial(driver, oferta):
    loja = oferta["loja"]
    url = oferta["href"]

    for tentativa in range(1, 3):
        try:
            driver.get(url)
        except TimeoutException:
            # O carregamento de imagens/scripts pode expirar, embora o texto já esteja disponível.
            pass
        except WebDriverException as erro:
            if tentativa == 2:
                return False, url, f"Falha ao abrir a {loja}: {erro.__class__.__name__}"
            continue

        aguardar_informacao_do_vendedor(driver)
        try:
            texto_body = driver.find_element(By.TAG_NAME, "body").text
            url_final = driver.current_url or url
        except WebDriverException:
            texto_body = ""
            url_final = url

        texto_chave = chave_texto(texto_body)
        bloqueado = any(
            termo in texto_chave
            for termo in (
                "robot check",
                "digite os caracteres",
                "nao sou um robo",
                "acesso negado",
            )
        )
        if bloqueado:
            if tentativa == 2:
                return False, url_final, f"A {loja} bloqueou o acesso ou exibiu CAPTCHA"
            continue

        if loja == "Amazon":
            oficial, motivo = verificar_vendedor_amazon(driver, texto_body)
        else:
            oficial, motivo = verificar_vendedor_kabum(texto_body)

        if oficial is not None:
            return oficial, url_final, motivo

        if tentativa == 2:
            return False, url_final, motivo

    return False, url, f"Não foi possível validar o vendedor na {loja}"


def converter_preco(valor):
    return float(valor.replace(".", "").replace(",", "."))


def limpar_fragmento_url(url):
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, partes.query, ""))


def encontrar_card_da_oferta(link):
    atual = link
    for _ in range(12):
        atual = atual.parent
        if atual is None:
            break
        texto = normalizar_texto(atual.get_text(" ", strip=True))
        if PADRAO_VISTA.search(texto) and PADRAO_PARCELADO.search(texto):
            return atual
    return None


def identificar_loja(card, href):
    candidatos = [href]
    candidatos.extend(
        imagem.get("alt", "") + " " + imagem.get("src", "")
        for imagem in card.find_all("img")
    )
    candidatos.append(card.get_text(" ", strip=True))
    texto = chave_texto(" ".join(candidatos))

    for termo, nome in LOJAS_VALIDAS.items():
        if termo in texto:
            return nome
    return None


def obter_html_promotech(sessao, url_promotech, navegador=None):
    if navegador is None:
        resposta = sessao.get(url_promotech, timeout=TIMEOUT_PAGINA_SEGUNDOS)
        mitigacao = resposta.headers.get("x-vercel-mitigated", "").lower()
        if resposta.status_code == 429 or mitigacao == "challenge":
            raise DesafioVercel("A Vercel exigiu um navegador com JavaScript")
        resposta.raise_for_status()
        return resposta.text

    try:
        navegador.get(url_promotech)
    except TimeoutException:
        pass

    def pagina_do_produto_carregou(driver):
        try:
            texto = chave_texto(driver.find_element(By.TAG_NAME, "body").text)
        except WebDriverException:
            return False
        return "comprar" in texto or "historico de precos" in texto

    try:
        WebDriverWait(navegador, TIMEOUT_PROMOTECH_CHROME_SEGUNDOS).until(
            pagina_do_produto_carregou
        )
    except TimeoutException:
        pass

    try:
        texto_body = chave_texto(navegador.find_element(By.TAG_NAME, "body").text)
        html = navegador.page_source
    except WebDriverException as erro:
        raise RuntimeError(f"Falha ao ler o Promotech pelo Chrome: {erro}") from erro

    pagina_carregada = (
        "comprar" in texto_body or "historico de precos" in texto_body
    )
    if not pagina_carregada and "vercel security checkpoint" in texto_body:
        raise DesafioVercel("A Vercel também bloqueou o Chrome do GitHub")
    if not html:
        raise RuntimeError("O Promotech retornou uma página vazia pelo Chrome")
    return html


def extrair_ofertas_promotech(sessao, url_promotech, navegador=None):
    html = obter_html_promotech(sessao, url_promotech, navegador)
    soup = BeautifulSoup(html, "html.parser")

    ofertas = []
    lojas_processadas = set()

    for link in soup.find_all("a", href=True):
        if "comprar" not in chave_texto(link.get_text(" ", strip=True)):
            continue

        card = encontrar_card_da_oferta(link)
        if card is None:
            continue

        texto_card = normalizar_texto(card.get_text(" ", strip=True))
        vista = PADRAO_VISTA.search(texto_card)
        parcelado = PADRAO_PARCELADO.search(texto_card)
        if not vista or not parcelado:
            continue

        href = limpar_fragmento_url(urljoin(url_promotech, link["href"]))
        loja = identificar_loja(card, href)
        if loja is None or loja in lojas_processadas:
            continue

        ofertas.append(
            {
                "loja": loja,
                "href": href,
                "preco_vista": converter_preco(vista.group(1)),
                "preco_parcelado": converter_preco(parcelado.group(1)),
            }
        )
        lojas_processadas.add(loja)

    return ofertas


def enviar_oferta(sessao, item, oferta):
    preco_vista = oferta["preco_vista"]
    preco_parcelado = oferta["preco_parcelado"]
    situacao = "ABAIXO DO ALVO" if preco_vista <= item["precoMax"] else "ACIMA DO ALVO"

    pacote = {
        "nome": item["nome"],
        "categoria": item["categoria"],
        "loja": oferta["loja"],
        "precoVista": preco_vista,
        "precoParcelado": preco_parcelado,
        "precoMax": item["precoMax"],
        "link": oferta["href"],
        "situacao": situacao,
        "fonte": "Promotech",
    }

    resposta = sessao.post(
        GOOGLE_WEBHOOK_URL,
        json=pacote,
        timeout=TIMEOUT_WEBHOOK_SEGUNDOS,
    )
    resposta.raise_for_status()


def rotina_principal():
    if not GOOGLE_WEBHOOK_URL:
        raise RuntimeError(
            "Defina GOOGLE_WEBHOOK_URL nos Secrets do GitHub antes de executar o monitor."
        )

    inicio = perf_counter()
    agora = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S %z")
    print(f"Iniciando varredura em {agora}")

    sessao = criar_sessao()
    navegador = None
    navegador_indisponivel = False
    promotech_via_navegador = os.environ.get(
        "PROMOTECH_VIA_CHROME", ""
    ).strip().lower() in {"1", "true", "sim"}
    produtos_com_oferta = 0
    ofertas_salvas = 0
    falhas = 0

    if promotech_via_navegador:
        print("Promotech configurado para acesso direto pelo Chrome.")
        try:
            navegador = iniciar_navegador()
        except WebDriverException as erro:
            raise RuntimeError(f"Falha ao iniciar o Chrome: {erro}") from erro

    for item in PRODUTOS:
        print(f"\nMapeando: {item['nome']}")
        try:
            if promotech_via_navegador:
                ofertas = extrair_ofertas_promotech(
                    sessao, item["urlPromotech"], navegador
                )
            else:
                try:
                    ofertas = extrair_ofertas_promotech(
                        sessao, item["urlPromotech"]
                    )
                except DesafioVercel:
                    print("  Vercel bloqueou a requisição HTTP; alternando para o Chrome...")
                    if navegador is None:
                        navegador = iniciar_navegador()
                    promotech_via_navegador = True
                    ofertas = extrair_ofertas_promotech(
                        sessao, item["urlPromotech"], navegador
                    )
        except DesafioVercel as erro:
            falhas += 1
            print(f"  Bloqueio geral ao consultar o Promotech: {erro}")
            break
        except WebDriverException as erro:
            navegador_indisponivel = True
            falhas += 1
            print(f"  Falha no navegador ao consultar o Promotech: {erro}")
            break
        except requests.RequestException as erro:
            falhas += 1
            print(f"  Falha ao consultar o Promotech: {erro}")
            continue
        except RuntimeError as erro:
            falhas += 1
            print(f"  Falha ao processar o Promotech: {erro}")
            continue

        if not ofertas:
            print("  Nenhuma oferta das lojas configuradas foi encontrada.")
            continue

        produtos_com_oferta += 1
        for oferta in ofertas:
            print(
                f"  {oferta['loja']}: à vista R$ {oferta['preco_vista']:.2f} | "
                f"parcelado R$ {oferta['preco_parcelado']:.2f}"
            )

            if oferta["loja"] in LOJAS_COM_VALIDACAO_DE_VENDEDOR:
                if navegador_indisponivel:
                    falhas += 1
                    print("    Ignorada: navegador indisponível para validar o vendedor")
                    continue

                if navegador is None:
                    print("    Iniciando navegador para validar Amazon/KaBuM...")
                    try:
                        navegador = iniciar_navegador()
                    except WebDriverException as erro:
                        navegador_indisponivel = True
                        falhas += 1
                        print(f"    Falha ao iniciar o navegador: {erro}")
                        continue

                oficial, url_final, motivo = verificar_vendedor_oficial(navegador, oferta)
                if not oficial:
                    if not motivo.startswith("Marketplace:"):
                        falhas += 1
                    print(f"    Ignorada: {motivo}")
                    continue

                oferta["href"] = limpar_fragmento_url(url_final)
                print(f"    Vendedor confirmado: {motivo}")

            try:
                enviar_oferta(sessao, item, oferta)
                ofertas_salvas += 1
            except requests.RequestException as erro:
                falhas += 1
                print(f"    Falha ao salvar na planilha: {erro}")

    if navegador is not None:
        try:
            navegador.quit()
        except WebDriverException:
            pass

    duracao = perf_counter() - inicio
    print(
        f"\nConcluído em {duracao:.1f}s: {produtos_com_oferta} produtos, "
        f"{ofertas_salvas} ofertas salvas e {falhas} falhas."
    )

    if falhas:
        raise RuntimeError(f"A varredura terminou com {falhas} falha(s).")


if __name__ == "__main__":
    rotina_principal()
