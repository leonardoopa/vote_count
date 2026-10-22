"""Apoio dos testes: arquivos do TSE de mentira e o leitor de PNG, que mais de um teste usa."""
import struct
import zlib

from contador.tse import catalogo


def ler_png(dados):
    """(largura, altura, pixels RGB) de um PNG de 8 bits RGB sem entrelaçamento, conferindo assinatura e CRC."""
    assert dados[:8] == b"\x89PNG\r\n\x1a\n", "assinatura"
    posicao, blocos = 8, {}
    while posicao < len(dados):
        tamanho, tipo = struct.unpack(">I4s", dados[posicao:posicao + 8])
        corpo = dados[posicao + 8:posicao + 8 + tamanho]
        crc = struct.unpack(">I", dados[posicao + 8 + tamanho:posicao + 12 + tamanho])[0]
        assert crc == zlib.crc32(tipo + corpo) & 0xFFFFFFFF, f"CRC de {tipo}"
        blocos.setdefault(tipo, []).append(corpo)
        posicao += 12 + tamanho
    largura, altura, profundidade, tipo_cor, _, _, entrelacado = struct.unpack(">IIBBBBB", blocos[b"IHDR"][0])
    assert (profundidade, tipo_cor, entrelacado) == (8, 2, 0)
    bruto = zlib.decompress(b"".join(blocos[b"IDAT"]))
    assert len(bruto) == altura * (1 + 3 * largura)
    linhas = [bruto[i * (1 + 3 * largura) + 1:(i + 1) * (1 + 3 * largura)] for i in range(altura)]
    assert all(bruto[i * (1 + 3 * largura)] == 0 for i in range(altura)), "filtro 0"
    assert b"IEND" in blocos
    return largura, altura, linhas


DADOS = {
    "tf": "n",
    "dt": "04/10/2026",
    "ht": "18:01:02",
    "dg": "04/10/2026",
    "hg": "18:01:30",
    "s": {"ts": "1000", "st": "250", "pst": "25,00"},
    "e": {"te": "5000", "c": "900", "pc": "90,00", "a": "100", "pa": "2,00"},
    "v": {"tv": "900", "vb": "20", "pvb": "2,22", "tvn": "30", "ptvn": "3,33"},
    "carg": [
        {
            "agr": [
                {
                    "par": [
                        {
                            "sg": "AAA",
                            "cand": [
                                {"n": "11", "nm": "ANA", "nmu": "ANA", "vap": "100", "pvap": "20,00"},
                                {"n": "12", "nm": "BIA", "nmu": "BIA", "vap": "400", "pvap": "80,00", "st": "2º turno"},
                            ],
                        }
                    ]
                }
            ]
        }
    ],
}


CONFIG_MUNICIPIOS = {
    "abr": [
        {
            "cd": "sp",
            "mu": [
                {"cd": "71072", "nm": "SÃO PAULO", "c": "s"},
                {"cd": "62910", "nm": "CAMPINAS", "c": "n"},
                {"cd": "70670", "nm": "SÃO JOÃO DA BOA VISTA", "c": "n"},
                {"cd": "70750", "nm": "SÃO JOÃO DEL REI", "c": "n"},
            ],
        },
        {"cd": "df", "mu": [{"cd": "97012", "nm": "BRASÍLIA", "c": "s"}]},
    ]
}


ANA, BRUNO = ("13", "ANA LIMA", "PT"), ("22", "BRUNO CASTRO", "PL")


LULA, JAIR = ("13", "Ana Lima", "PT"), ("22", "Bruno Castro", "PL")


def tse(votos, apuradas=250, dt="21/10/2026", ht="20:00:00", final=False, situacoes=None, candidatos=(LULA, JAIR)):
    """Arquivo do TSE no formato real, com um candidato por partido. `votos` segue a ordem de `candidatos`."""
    total, validos = 1000, sum(votos) or 1
    situacoes = situacoes or {}
    return {
        "tf": "s" if final else "n", "dt": dt, "ht": ht, "dg": dt, "hg": ht or "16:59:00",
        "s": {"ts": str(total), "st": str(apuradas), "pst": f"{100 * apuradas / total:.2f}".replace(".", ",")},
        "e": {"te": "5000", "c": "900", "pc": "90,00", "a": "100", "pa": "2,00"},
        "v": {"tv": str(sum(votos)), "vb": "20", "pvb": "2,22", "tvn": "30", "ptvn": "3,33"},
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [{
                "n": numero, "nm": nome.upper(), "nmu": nome.upper(), "vap": str(v),
                "pvap": f"{100 * v / validos:.2f}".replace(".", ","), "st": situacoes.get(numero, ""),
            }]}]}
            for (numero, nome, partido), v in zip(candidatos, votos)
        ]}],
    }


AGORA = 1_000_000.0


def arquivo(candidatos, final=False, secoes=(1000, 500)):
    """Arquivo do TSE só com o que o mapa lê. candidatos: (número, nome, partido, votos, "pct", situação)."""
    total, apuradas = secoes
    return {
        "tf": "s" if final else "n",
        "s": {"ts": str(total), "st": str(apuradas), "pst": f"{100 * apuradas / total:.2f}".replace(".", ",")},
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [
                {"n": numero, "nm": nome.upper(), "nmu": nome.upper(), "vap": str(votos), "pvap": pct, "st": situacao}
            ]}]}
            for numero, nome, partido, votos, pct, situacao in candidatos
        ]}],
    }


DOIS = [("13", "Ana", "PT", 600, "60,00", ""), ("22", "Bia", "PL", 400, "40,00", "")]


def url(cargo, uf, turno=1, ambiente="oficial"):
    return catalogo.montar_url(ambiente, cargo, uf, turno)


def fonte_com(cargo, turno, dados_por_uf, br=None):
    respostas = {url(cargo, uf, turno): (dados, 200, AGORA) for uf, dados in dados_por_uf.items()}
    if br is not None:
        respostas[url(cargo, "br", turno)] = (br, 200, AGORA)
    return Fonte(respostas)


class Fonte:
    """Faz de conta de CACHE.obter: responde por URL e anota o que foi pedido (404 para o resto)."""

    def __init__(self, respostas=None):
        self.respostas, self.pedidos = respostas or {}, []

    def __call__(self, url, ttl=None):
        self.pedidos.append(url)
        return self.respostas.get(url, (None, 404, 0))


TRES = [("13", "Ana", "PT", 500, "50,00", ""), ("22", "Bia", "PL", 300, "30,00", ""), ("55", "Caio", "PSD", 200, "20,00", "")]
