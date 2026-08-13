import os
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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

DOMINIOS_DAS_LOJAS = {
    "Amazon": ("amazon.com.br",),
    "KaBuM": ("kabum.com.br",),
    "Pichau": ("pichau.com.br",),
    "Terabyte": ("terabyteshop.com.br",),
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

MARCADORES_INDISPONIVEL = (
    "produto indisponivel",
    "produto esgotado",
    "indisponivel no momento",
    "nao esta mais disponivel",
    "nao sabemos quando este produto estara disponivel novamente",
    "avise-me quando chegar",
    "avise me quando chegar",
    "avise-me quando disponivel",
    "sem estoque",
)

MARCADORES_DISPONIVEL = (
    "adicionar ao carrinho",
    "comprar agora",
    "em estoque",
    "pronta entrega",
    "restam ",
)

MARCADORES_BLOQUEIO_LOJA = (
    "robot check",
    "digite os caracteres",
    "nao sou um robo",
    "acesso negado",
)

INICIO_DE_RECOMENDACOES = (
    "ops! ja que esgotou",
    "oportunidade - compre junto",
    "frequentemente comprados juntos",
    "clientes que visualizaram este item",
    "produtos que voce tambem pode gostar",
    "produtos relacionados",
    "quem viu este produto",
    "veja tambem",
    "caracteristicas gerais",
)


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


def detectar_chrome_instalado():
    versao_configurada = os.environ.get("CHROME_VERSION_MAIN", "").strip()
    executavel_configurado = os.environ.get("CHROME_BIN", "").strip()

    if versao_configurada.isdigit() and executavel_configurado:
        return int(versao_configurada), executavel_configurado

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
            return int(correspondencia.group(1)), executavel

    return None, None


def iniciar_navegador():
    versao_chrome, executavel_chrome = detectar_chrome_instalado()
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
        print(
            f"Chrome selecionado: versão {versao_chrome} "
            f"em {executavel_chrome}"
        )
        navegador = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=versao_chrome,
            browser_executable_path=executavel_chrome,
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


def dominio_compativel_com_loja(loja, url):
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    return any(
        hostname == dominio or hostname.endswith(f".{dominio}")
        for dominio in DOMINIOS_DAS_LOJAS.get(loja, ())
    )


def recortar_area_principal_do_produto(texto_body):
    texto = chave_texto(texto_body)
    limites = [
        texto.find(marcador)
        for marcador in INICIO_DE_RECOMENDACOES
        if texto.find(marcador) >= 0
    ]
    if limites:
        texto = texto[:min(limites)]
    return texto[:12000]


def analisar_disponibilidade(texto_body):
    """Retorna False quando indisponível, True quando disponível e None se incerto."""
    texto = recortar_area_principal_do_produto(texto_body)
    if any(marcador in texto for marcador in MARCADORES_INDISPONIVEL):
        return False
    if any(marcador in texto for marcador in MARCADORES_DISPONIVEL):
        return True
    return None


def pagina_da_loja_bloqueada(texto_body):
    texto = chave_texto(texto_body)
    return any(marcador in texto for marcador in MARCADORES_BLOQUEIO_LOJA)


def aguardar_conteudo_da_loja(driver, segundos=12):
    try:
        WebDriverWait(driver, segundos).until(
            lambda navegador: navegador.execute_script("return document.readyState")
            == "complete"
        )
    except TimeoutException:
        pass

    # Algumas lojas inserem o estoque depois do evento de carregamento.
    time.sleep(2)


def verificar_disponibilidade_loja(driver, oferta):
    """Valida disponibilidade diretamente na Pichau/Terabyte."""
    loja = oferta["loja"]
    url = oferta["href"]

    for tentativa in range(1, 3):
        try:
            driver.get(url)
        except TimeoutException:
            pass
        except WebDriverException as erro:
            if tentativa == 2:
                return "INCONCLUSIVO", url, f"Falha ao abrir a {loja}: {erro.__class__.__name__}"
            continue

        aguardar_conteudo_da_loja(driver)
        try:
            texto_body = driver.find_element(By.TAG_NAME, "body").text
            url_final = driver.current_url or url
        except WebDriverException:
            texto_body = ""
            url_final = url

        if not dominio_compativel_com_loja(loja, url_final):
            return (
                "LOJA_DIVERGENTE",
                url_final,
                f"O link da {loja} redirecionou para {urlsplit(url_final).hostname or 'outro site'}",
            )

        if pagina_da_loja_bloqueada(texto_body):
            if tentativa == 2:
                return "INCONCLUSIVO", url_final, f"A {loja} bloqueou o acesso ou exibiu CAPTCHA"
            continue

        disponibilidade = analisar_disponibilidade(texto_body)
        if disponibilidade is False:
            return "INDISPONIVEL", url_final, "Produto indisponível na página da loja"
        if disponibilidade is True:
            return "DISPONIVEL", url_final, "Produto disponível na página da loja"

        # Algumas páginas da Pichau não expõem o texto do botão de compra ao
        # Selenium, mas exibem normalmente uma condição válida de cartão.
        if extrair_preco_parcelado_da_loja(driver, oferta) is not None:
            return (
                "DISPONIVEL",
                url_final,
                "Oferta ativa confirmada pela condição de parcelamento",
            )

        if tentativa == 2:
            return "INCONCLUSIVO", url_final, f"A {loja} não exibiu a disponibilidade do produto"

    return "INCONCLUSIVO", url, f"Não foi possível validar a disponibilidade na {loja}"


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
                return False, url, f"Falha ao abrir a {loja}: {erro.__class__.__name__}", "INCONCLUSIVO"
            continue

        aguardar_informacao_do_vendedor(driver)
        aguardar_conteudo_da_loja(driver, segundos=5)
        try:
            texto_body = driver.find_element(By.TAG_NAME, "body").text
            url_final = driver.current_url or url
        except WebDriverException:
            texto_body = ""
            url_final = url

        if not dominio_compativel_com_loja(loja, url_final):
            dominio_final = urlsplit(url_final).hostname or "outro site"
            return (
                False,
                url_final,
                f"Marketplace: o link da {loja} redirecionou para {dominio_final}",
                "MARKETPLACE",
            )

        if pagina_da_loja_bloqueada(texto_body):
            if tentativa == 2:
                return False, url_final, f"A {loja} bloqueou o acesso ou exibiu CAPTCHA", "INCONCLUSIVO"
            continue

        if analisar_disponibilidade(texto_body) is False:
            return False, url_final, "Produto indisponível na página da loja", "INDISPONIVEL"

        if loja == "Amazon":
            oficial, motivo = verificar_vendedor_amazon(driver, texto_body)
        else:
            oficial, motivo = verificar_vendedor_kabum(texto_body)

        if oficial is not None:
            status = "DISPONIVEL" if oficial else "MARKETPLACE"
            return oficial, url_final, motivo, status

        if tentativa == 2:
            return False, url_final, motivo, "INCONCLUSIVO"

    return False, url, f"Não foi possível validar o vendedor na {loja}", "INCONCLUSIVO"


def converter_preco(valor):
    return float(valor.replace(".", "").replace(",", "."))


def converter_preco_da_loja(valor):
    """Converte tanto 1.234,56 quanto 1,234.56 sem confundir milhar/decimal."""
    valor = re.sub(r"[^\d.,]", "", valor or "")
    if not valor:
        raise ValueError("Preço vazio")

    if "," in valor and "." in valor:
        separador_decimal = "," if valor.rfind(",") > valor.rfind(".") else "."
        separador_milhar = "." if separador_decimal == "," else ","
        valor = valor.replace(separador_milhar, "").replace(separador_decimal, ".")
    elif "," in valor:
        partes = valor.split(",")
        valor = "".join(partes[:-1]) + "." + partes[-1] if len(partes[-1]) == 2 else "".join(partes)
    elif "." in valor:
        partes = valor.split(".")
        valor = "".join(partes[:-1]) + "." + partes[-1] if len(partes[-1]) == 2 else "".join(partes)

    try:
        return Decimal(valor)
    except InvalidOperation as erro:
        raise ValueError(f"Preço inválido: {valor}") from erro


def texto_da_area_de_preco(driver, loja):
    """Lê primeiro o bloco principal do produto, evitando recomendações."""
    seletores_por_loja = {
        "Amazon": (
            "#apex_desktop",
            "#corePrice_feature_div",
            "#corePriceDisplay_desktop_feature_div",
            "#installmentCalculator_feature_div",
            "#creditCardInstallmentCalculator_feature_div",
            "#desktop_buybox",
        ),
        "KaBuM": (
            "main",
            "[data-testid='product-detail']",
            "[class*='purchase']",
        ),
        "Pichau": (
            "main",
            "[class*='product-info']",
            "[class*='product_info']",
        ),
        "Terabyte": (
            "main",
            "#produto",
            "[class*='product']",
        ),
    }
    partes = []
    for seletor in seletores_por_loja.get(loja, ("main",)):
        texto = texto_do_elemento(driver, seletor)
        if texto:
            partes.append(recortar_area_principal_do_produto(texto))

    try:
        texto_body = driver.find_element(By.TAG_NAME, "body").text
    except WebDriverException:
        texto_body = ""

    # O corpo recortado é um fallback importante para classes que mudam de nome.
    partes.append(recortar_area_principal_do_produto(texto_body))
    return chave_texto(" ".join(partes))


def extrair_preco_parcelado_da_loja(driver, oferta):
    """Retorna (total, quantidade, valor_da_parcela) confirmado na loja."""
    loja = oferta["loja"]
    texto = texto_da_area_de_preco(driver, loja)
    preco_vista = Decimal(str(oferta["preco_vista"]))

    # Pichau e Terabyte normalmente mostram o total antes da frase das parcelas.
    # O total explícito tem prioridade porque o valor visual de cada parcela pode
    # ter arredondamento de centavos (12 x 117,55, por exemplo).
    padrao_total = re.compile(
        r"R\$\s*([\d.,]+)\s+(?:em\s+)?ate\s+(\d{1,2})\s*x\s+de\s+"
        r"R\$\s*([\d.,]+)(?=[^\d]|$)",
        re.IGNORECASE,
    )
    candidatos_explicitos = []
    for correspondencia in padrao_total.finditer(texto):
        try:
            total = converter_preco_da_loja(correspondencia.group(1))
            parcelas = int(correspondencia.group(2))
            valor_parcela = converter_preco_da_loja(correspondencia.group(3))
        except (ValueError, InvalidOperation):
            continue
        if parcelas < 2 or not (preco_vista * Decimal("0.70") <= total <= preco_vista * Decimal("2.50")):
            continue
        candidatos_explicitos.append((parcelas, total, valor_parcela))

    if candidatos_explicitos:
        parcelas, total, valor_parcela = max(candidatos_explicitos, key=lambda item: item[0])
        return float(total), parcelas, float(valor_parcela)

    # KaBuM e Amazon podem mostrar apenas "10x de R$ ... sem juros". Nesse
    # formato, o total correto é calculado com Decimal para evitar erro binário.
    padrao_parcela = re.compile(
        r"(\d{1,2})\s*x\s*(?:de\s*)?R\$\s*([\d.,]+)"
        r"(?=[^\d]|$)(?:(?!\d{1,2}\s*x).){0,45}?"
        r"(?:sem\s+juros|s\s*/?\s*juros|no\s+cartao)",
        re.DOTALL | re.IGNORECASE,
    )
    candidatos_calculados = []
    for correspondencia in padrao_parcela.finditer(texto):
        try:
            parcelas = int(correspondencia.group(1))
            valor_parcela = converter_preco_da_loja(correspondencia.group(2))
        except (ValueError, InvalidOperation):
            continue
        total = (Decimal(parcelas) * valor_parcela).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if parcelas < 2 or not (preco_vista * Decimal("0.70") <= total <= preco_vista * Decimal("2.50")):
            continue
        candidatos_calculados.append((parcelas, total, valor_parcela))

    if candidatos_calculados:
        parcelas, total, valor_parcela = max(candidatos_calculados, key=lambda item: item[0])
        return float(total), parcelas, float(valor_parcela)

    return None


def limpar_fragmento_url(url):
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, partes.query, ""))


def identificar_lojas_pelas_imagens(card):
    lojas = set()
    for imagem in card.find_all("img"):
        texto_imagem = chave_texto(
            f"{imagem.get('alt', '')} {imagem.get('src', '')}"
        )
        for termo, nome in LOJAS_VALIDAS.items():
            if termo in texto_imagem:
                lojas.add(nome)
    return lojas


def encontrar_card_da_oferta(link):
    atual = link
    for _ in range(12):
        atual = atual.parent
        if atual is None:
            break

        texto = normalizar_texto(atual.get_text(" ", strip=True))
        if not PADRAO_VISTA.search(texto) or not PADRAO_PARCELADO.search(texto):
            continue

        acoes = {
            chave_texto(acao.get_text(" ", strip=True))
            for acao in atual.find_all("a")
        }
        if not any("comprar" in acao for acao in acoes):
            continue
        if not any("parcelar" in acao for acao in acoes):
            continue

        # O resumo no topo mistura a melhor oferta à vista de uma loja com a
        # melhor parcelada de outra. Um card individual possui exatamente uma
        # logo de loja; ancestrais que reúnem várias ofertas são descartados.
        lojas = identificar_lojas_pelas_imagens(atual)
        if len(lojas) == 1:
            return atual, lojas.pop()

    return None, None


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

        card, loja = encontrar_card_da_oferta(link)
        if card is None:
            continue

        texto_card = normalizar_texto(card.get_text(" ", strip=True))
        vista = PADRAO_VISTA.search(texto_card)
        parcelado = PADRAO_PARCELADO.search(texto_card)
        if not vista or not parcelado:
            continue

        href = limpar_fragmento_url(urljoin(url_promotech, link["href"]))
        if loja in lojas_processadas:
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


def postar_webhook(sessao, pacote):
    for tentativa in range(1, 4):
        try:
            resposta = sessao.post(
                GOOGLE_WEBHOOK_URL,
                json=pacote,
                timeout=TIMEOUT_WEBHOOK_SEGUNDOS,
            )
            resposta.raise_for_status()

            try:
                retorno = resposta.json()
            except ValueError as erro:
                raise requests.RequestException(
                    "O Apps Script retornou uma resposta que não é JSON"
                ) from erro

            if retorno.get("erro"):
                raise requests.RequestException(
                    f"Apps Script recusou o registro: {retorno['erro']}"
                )
            return
        except requests.RequestException:
            if tentativa == 3:
                raise
            time.sleep(2)


def tipo_do_produto(item):
    url = item.get("urlPromotech", "")
    if "/processador/" in url:
        return "Processador"
    if "/memoria-ram/" in url:
        return "Memória RAM"
    if "/placa-de-video/" in url:
        return "Placa de vídeo"
    return item.get("categoria", "Outros")


def enviar_oferta(sessao, item, oferta):
    preco_vista = oferta["preco_vista"]
    preco_parcelado_total = oferta["preco_parcelado"]
    quantidade_parcelas = int(oferta["quantidade_parcelas"])
    valor_parcela = oferta["valor_parcela"]
    situacao = "ABAIXO DO ALVO" if preco_vista <= item["precoMax"] else "ACIMA DO ALVO"

    pacote = {
        "nome": item["nome"],
        "categoria": item["categoria"],
        "tipo": tipo_do_produto(item),
        "loja": oferta["loja"],
        "precoVista": preco_vista,
        # Mantém o valor de UMA parcela neste campo por compatibilidade com
        # versões anteriores do Apps Script.
        "precoParcelado": valor_parcela,
        "quantidadeParcelas": quantidade_parcelas,
        "valorParcela": valor_parcela,
        "precoParceladoTotal": preco_parcelado_total,
        "precoMax": item["precoMax"],
        "link": oferta["href"],
        "situacao": situacao,
        "status": "DISPONIVEL",
        "fonte": "Promotech",
    }

    postar_webhook(sessao, pacote)


def enviar_indisponibilidade(sessao, item, oferta):
    pacote = {
        "nome": item["nome"],
        "categoria": item["categoria"],
        "tipo": tipo_do_produto(item),
        "loja": oferta["loja"],
        "precoVista": 0,
        "precoParcelado": 0,
        "precoMax": item["precoMax"],
        "link": oferta["href"],
        "situacao": "INDISPONIVEL",
        "status": "INDISPONIVEL",
        "fonte": "Loja oficial",
    }
    postar_webhook(sessao, pacote)


def enviar_remocao_de_oferta(sessao, item, oferta, motivo):
    pacote = {
        "nome": item["nome"],
        "categoria": item["categoria"],
        "tipo": tipo_do_produto(item),
        "loja": oferta["loja"],
        "precoMax": item["precoMax"],
        "link": oferta.get("href", ""),
        "situacao": "IGNORADA",
        "status": "REMOVER",
        "motivo": motivo,
        "fonte": "Validação da loja",
    }
    postar_webhook(sessao, pacote)


def enviar_sincronizacao_do_produto(sessao, item, lojas_encontradas):
    pacote = {
        "nome": item["nome"],
        "categoria": item["categoria"],
        "tipo": tipo_do_produto(item),
        "precoMax": item["precoMax"],
        "status": "SINCRONIZAR",
        "lojasEncontradas": sorted(lojas_encontradas),
        "fonte": "Promotech",
    }
    postar_webhook(sessao, pacote)


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
    falhas_planilha = 0
    indisponiveis_registrados = 0
    validacoes_inconclusivas = 0
    marketplaces_ignorados = 0

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

        try:
            enviar_sincronizacao_do_produto(
                sessao, item, {oferta["loja"] for oferta in ofertas}
            )
        except requests.RequestException as erro:
            falhas_planilha += 1
            print(f"  Falha ao sincronizar lojas na planilha: {erro}")

        if not ofertas:
            print("  Nenhuma oferta das lojas configuradas foi encontrada.")
            continue

        produtos_com_oferta += 1
        for oferta in ofertas:
            print(
                f"  {oferta['loja']}: à vista R$ {oferta['preco_vista']:.2f} | "
                f"total parcelado informado pelo Promotech "
                f"R$ {oferta['preco_parcelado']:.2f}"
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

                oficial, url_final, motivo, status_loja = verificar_vendedor_oficial(
                    navegador, oferta
                )
                oferta["href"] = limpar_fragmento_url(url_final)

                if status_loja == "INDISPONIVEL":
                    print("    Produto indisponível na loja; atualizando a planilha.")
                    try:
                        enviar_indisponibilidade(sessao, item, oferta)
                        indisponiveis_registrados += 1
                    except requests.RequestException as erro:
                        falhas_planilha += 1
                        print(
                            "    Falha ao registrar indisponibilidade na planilha "
                            f"após 3 tentativas: {erro}"
                        )
                    continue

                if not oficial:
                    if status_loja == "MARKETPLACE":
                        marketplaces_ignorados += 1
                        try:
                            enviar_remocao_de_oferta(sessao, item, oferta, motivo)
                        except requests.RequestException as erro:
                            falhas_planilha += 1
                            print(
                                "    Falha ao remover marketplace da planilha "
                                f"após 3 tentativas: {erro}"
                            )
                    else:
                        validacoes_inconclusivas += 1
                        try:
                            enviar_remocao_de_oferta(sessao, item, oferta, motivo)
                        except requests.RequestException as erro:
                            falhas_planilha += 1
                            print(
                                "    Falha ao limpar validação inconclusiva da "
                                f"planilha após 3 tentativas: {erro}"
                            )
                    print(f"    Ignorada: {motivo}")
                    continue

                print(f"    Vendedor confirmado: {motivo}")

            else:
                if navegador is None:
                    print(f"    Iniciando navegador para validar a {oferta['loja']}...")
                    try:
                        navegador = iniciar_navegador()
                    except WebDriverException as erro:
                        navegador_indisponivel = True
                        falhas += 1
                        print(f"    Falha ao iniciar o navegador: {erro}")
                        continue

                status_loja, url_final, motivo = verificar_disponibilidade_loja(
                    navegador, oferta
                )
                oferta["href"] = limpar_fragmento_url(url_final)

                if status_loja == "INDISPONIVEL":
                    print("    Produto indisponível na loja; atualizando a planilha.")
                    try:
                        enviar_indisponibilidade(sessao, item, oferta)
                        indisponiveis_registrados += 1
                    except requests.RequestException as erro:
                        falhas_planilha += 1
                        print(
                            "    Falha ao registrar indisponibilidade na planilha "
                            f"após 3 tentativas: {erro}"
                        )
                    continue

                if status_loja == "LOJA_DIVERGENTE":
                    marketplaces_ignorados += 1
                    print(f"    Ignorada: {motivo}")
                    try:
                        enviar_remocao_de_oferta(sessao, item, oferta, motivo)
                    except requests.RequestException as erro:
                        falhas_planilha += 1
                        print(
                            "    Falha ao remover oferta divergente da planilha "
                            f"após 3 tentativas: {erro}"
                        )
                    continue

                if status_loja == "INCONCLUSIVO":
                    validacoes_inconclusivas += 1
                    print(f"    Ignorada: {motivo}")
                    try:
                        enviar_remocao_de_oferta(sessao, item, oferta, motivo)
                    except requests.RequestException as erro:
                        falhas_planilha += 1
                        print(
                            "    Falha ao limpar validação inconclusiva da "
                            f"planilha após 3 tentativas: {erro}"
                        )
                    continue

                print(f"    Disponibilidade confirmada na {oferta['loja']}.")

            confirmacao_parcelado = extrair_preco_parcelado_da_loja(
                navegador, oferta
            )
            if confirmacao_parcelado is None:
                validacoes_inconclusivas += 1
                print(
                    "    Ignorada: a loja não exibiu uma condição de "
                    "parcelamento sem juros que pudesse ser confirmada."
                )
                try:
                    enviar_remocao_de_oferta(
                        sessao,
                        item,
                        oferta,
                        "Parcelamento não confirmado diretamente na loja",
                    )
                except requests.RequestException as erro:
                    falhas_planilha += 1
                    print(
                        "    Falha ao limpar parcelamento não confirmado da "
                        f"planilha após 3 tentativas: {erro}"
                    )
                continue

            total_parcelado, quantidade_parcelas, valor_parcela = (
                confirmacao_parcelado
            )
            oferta["preco_parcelado"] = total_parcelado
            oferta["quantidade_parcelas"] = quantidade_parcelas
            oferta["valor_parcela"] = valor_parcela
            print(
                f"    Cartão confirmado na loja: {quantidade_parcelas}x de "
                f"R$ {valor_parcela:.2f} | total R$ {total_parcelado:.2f}"
            )

            try:
                enviar_oferta(sessao, item, oferta)
                ofertas_salvas += 1
            except requests.RequestException as erro:
                falhas_planilha += 1
                print(f"    Falha ao salvar na planilha após 3 tentativas: {erro}")

    if navegador is not None:
        try:
            navegador.quit()
        except WebDriverException:
            pass

    duracao = perf_counter() - inicio
    print(
        f"\nConcluído em {duracao:.1f}s: {produtos_com_oferta} produtos, "
        f"{ofertas_salvas} ofertas salvas, {marketplaces_ignorados} marketplaces "
        f"ignorados, {indisponiveis_registrados} indisponibilidades registradas, "
        f"{validacoes_inconclusivas} validações inconclusivas, "
        f"{falhas_planilha} falhas de planilha e {falhas} falhas reais de raspagem."
    )

    if falhas:
        raise RuntimeError(f"A varredura terminou com {falhas} falha(s).")


if __name__ == "__main__":
    rotina_principal()
