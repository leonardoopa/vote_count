"""Validação da query: só valores conhecidos chegam à URL do TSE; o resto vira erro 400."""
from contador.tse import catalogo

TOP_PADRAO, TOP_MAXIMO = 15, 100


def validar(consulta):
    """Só valores conhecidos chegam à URL do TSE; qualquer outra coisa vira erro 400."""
    pegar = lambda nome, padrao="": consulta.get(nome, [padrao])[0]
    cargo = pegar("cargo", "presidente")
    uf = pegar("uf", "br" if cargo == "presidente" else "").lower()
    ambiente = pegar("ambiente", "oficial")
    turno, top = pegar("turno", "1"), pegar("top", str(TOP_PADRAO))
    if cargo not in catalogo.CARGOS:
        raise ValueError("cargo inválido")
    if not catalogo.uf_valida(cargo, uf):
        raise ValueError("uf inválida para este cargo")
    if ambiente not in catalogo.AMBIENTES:
        raise ValueError("ambiente inválido")
    if turno not in ("1", "2") or not top.isdigit():
        raise ValueError("turno ou top inválido")
    if turno == "2" and cargo not in ("presidente", "governador"):
        raise ValueError("só presidente e governador têm 2º turno")
    return cargo, uf, ambiente, int(turno), max(1, min(int(top), TOP_MAXIMO))


def validar_municipio(consulta, uf):
    """Código TSE da cidade (5 dígitos) ou '' para a UF inteira. Se existe na UF, quem diz é o TSE."""
    codigo = consulta.get("municipio", [""])[0]
    if not codigo:
        return ""
    if uf == "br" or not (codigo.isascii() and codigo.isdigit() and len(codigo) == 5):
        raise ValueError("município inválido")
    return codigo


def validar_mapa(consulta, cargos=("presidente", "governador")):
    """(cargo, ambiente, turno) do mapa: a validação é a de `validar`, que pede uma UF; o mapa usa todas."""
    cargo = consulta.get("cargo", ["presidente"])[0]
    if cargo not in cargos:
        raise ValueError("este recurso só existe para " + " e ".join(cargos))
    _, _, ambiente, turno, _ = validar({**consulta, "uf": ["br" if cargo == "presidente" else "sp"]})
    return cargo, ambiente, turno
