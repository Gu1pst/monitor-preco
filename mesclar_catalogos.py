import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


def carregar(caminho):
    if not caminho.exists():
        return {"versao": 1, "atualizadoEm": None, "produtos": {}}
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados.get("produtos"), dict):
        raise ValueError(f"Catálogo inválido: {caminho}")
    return dados


def limpar_registros_invalidos(produtos):
    removidos = 0
    termos_proibidos = (
        "kit-upgrade", "upgrade", "pc-gamer", "computador",
        "workstation", "open-box",
    )
    for lojas in produtos.values():
        if not isinstance(lojas, dict):
            continue
        for loja, registro in list(lojas.items()):
            if not isinstance(registro, dict):
                continue
            if (
                loja in {"Amazon", "KaBuM"}
                and registro.get("vendedorOficialNaDescoberta") is False
            ):
                lojas.pop(loja, None)
                removidos += 1
                continue
            try:
                caminho = urlsplit(str(registro.get("url", ""))).path.lower()
            except ValueError:
                caminho = ""
            if any(termo in caminho for termo in termos_proibidos):
                lojas.pop(loja, None)
                removidos += 1
    return removidos


def mesclar(base, arquivos):
    resultado = carregar(base)
    resultado["versao"] = 1
    removidos = limpar_registros_invalidos(resultado["produtos"])
    if removidos:
        print(f"Limpeza defensiva removeu {removidos} link(s) inválido(s).")
    for caminho in arquivos:
        parcial = carregar(caminho)
        lojas_processadas = parcial.get("lojasProcessadas", [])
        if not lojas_processadas:
            print(f"Ignorando catálogo parcial não validado: {caminho.name}")
            continue
        # Um catálogo parcial validado substitui completamente aquela loja.
        # Assim, links antigos, marketplace e produtos não redescobertos somem.
        for loja in lojas_processadas:
            for lojas_produto in resultado["produtos"].values():
                if isinstance(lojas_produto, dict):
                    lojas_produto.pop(loja, None)
        for nome, lojas in parcial["produtos"].items():
            if not isinstance(lojas, dict):
                continue
            destino = resultado["produtos"].setdefault(nome, {})
            destino.update(lojas)
    resultado.pop("lojasProcessadas", None)
    resultado["atualizadoEm"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    return resultado


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    argumentos = parser.parse_args()
    arquivos = sorted(argumentos.entrada.rglob("catalogo-*.json"))
    if not arquivos:
        raise RuntimeError("Nenhum catálogo parcial foi baixado")
    resultado = mesclar(argumentos.base, arquivos)
    argumentos.saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Catálogo unido com {len(resultado['produtos'])} produtos.")


if __name__ == "__main__":
    main()
