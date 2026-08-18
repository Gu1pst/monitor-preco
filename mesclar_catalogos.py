import argparse
import json
from datetime import datetime
from pathlib import Path


def carregar(caminho):
    if not caminho.exists():
        return {"versao": 1, "atualizadoEm": None, "produtos": {}}
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados.get("produtos"), dict):
        raise ValueError(f"Catálogo inválido: {caminho}")
    return dados


def mesclar(base, arquivos):
    resultado = carregar(base)
    resultado["versao"] = 1
    for caminho in arquivos:
        parcial = carregar(caminho)
        for nome, lojas in parcial["produtos"].items():
            if not isinstance(lojas, dict):
                continue
            destino = resultado["produtos"].setdefault(nome, {})
            destino.update(lojas)
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
