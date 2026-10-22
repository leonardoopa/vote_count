"""Leitura dos arquivos JSON do TSE: números, candidatos, nomes e cidades."""
import unicodedata


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "del"}


def nome_proprio(nome):
    """'SÃO JOÃO DEL REI' -> 'São João del Rei' (o TSE manda tudo em maiúsculas)."""
    palavras = nome.lower().split()
    return " ".join(
        p if (i and p in _MINUSCULAS) else p.title() for i, p in enumerate(palavras)
    )


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold().strip()


def municipios(config, uf):
    """Cidades da UF no arquivo de configuração do TSE, em ordem alfabética."""
    for abrangencia in config.get("abr", []):
        if abrangencia.get("cd") == uf:
            lista = [
                {"codigo": m["cd"], "nome": nome_proprio(m["nm"]), "capital": m.get("c") == "s"}
                for m in abrangencia.get("mu", [])
            ]
            return sorted(lista, key=lambda m: sem_acento(m["nome"]))
    return []


def cidade_por_codigo(lista, codigo):
    """A cidade com este código TSE na lista de `municipios`, ou None."""
    return next((m for m in lista if m["codigo"] == codigo), None)


def achar_municipio(lista, termo):
    """Cidade pelo nome, sem diferenciar acento nem caixa. Devolve (cidade, parecidas).

    Nome exato vence; senão vale um único nome que contenha o termo. Com mais de um,
    devolve `cidade=None` e as candidatas em `parecidas`.
    """
    alvo = sem_acento(termo)
    exatas = [m for m in lista if sem_acento(m["nome"]) == alvo]
    if exatas:
        return exatas[0], []
    parecidas = [m for m in lista if alvo and alvo in sem_acento(m["nome"])]
    return (parecidas[0], []) if len(parecidas) == 1 else (None, parecidas)


def inteiro(valor):
    return int(valor or 0)


def decimal(texto):
    """'12,34' -> 12.34: o TSE manda os percentuais com vírgula."""
    return float((texto or "0").replace(",", "."))


def milhar(valor):
    return f"{inteiro(valor):,}".replace(",", ".")


def numero_br(valor, casas=2):
    """12.3 -> '12,30'."""
    return f"{valor:.{casas}f}".replace(".", ",")


def candidatos(dados):
    """Candidatos do arquivo, do mais votado para o menos votado."""
    lista = [
        {**cand, "partido": partido["sg"]}
        for cargo in dados["carg"]
        for agrupamento in cargo["agr"]
        for partido in agrupamento["par"]
        for cand in partido["cand"]
    ]
    return sorted(lista, key=lambda c: (-inteiro(c["vap"]), c["nm"]))


def situacao(cand):
    marcas = []
    if cand.get("dvt") not in (None, "", "Válido"):
        marcas.append(cand["dvt"])
    if cand.get("st"):
        marcas.append(cand["st"])
    return " / ".join(marcas)
