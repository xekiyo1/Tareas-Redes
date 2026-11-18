"""Pruebas locales, sin routers ni sockets. Ejecutar: python3 test_fragmentacion.py"""

import random

import router
from router import (HEADER_SIZE, check_routes, create_packet, fragment_IP_packet,
                    parse_packet, reassemble_IP_packet, store_and_reassemble)


def mk(message=b"x" * 134, ttl=10, pkt_id=347, offset=0, flag=0, ip="127.0.0.1", port=8885):
    return create_packet({"ip": ip, "port": port, "ttl": ttl, "id": pkt_id,
                          "offset": offset, "flag": flag, "message": message})


# ---------------- Paso 1: header ----------------
def test_header_16_bytes_y_roundtrip():
    assert HEADER_SIZE == 16
    # 127.0.0.1 | 8885 | TTL 10 | ID 347 | offset 0 | tamaño 5 | flag 0 | "hola!"
    v1 = (bytes([127, 0, 0, 1]) + (8885).to_bytes(2, "big") + bytes([10]) +
          (347).to_bytes(2, "big") + (0).to_bytes(2, "big") + (5).to_bytes(4, "big") +
          bytes([0]) + b"hola!")
    parsed = parse_packet(v1)
    assert parsed["id"] == 347 and parsed["size"] == 5 and parsed["message"] == b"hola!"
    v2 = create_packet(parsed)
    print("IP_packet_v1 == IP_packet_v2 ? {}".format(v1 == v2))
    assert v1 == v2


def test_header_validaciones():
    for bad in (dict(ttl=256), dict(pkt_id=70000), dict(offset=70000), dict(flag=2), dict(port=70000)):
        try:
            mk(b"a", **bad)
            assert False, f"debió fallar con {bad}"
        except ValueError:
            pass
    try:
        parse_packet(b"\x00" * 10)
        assert False
    except ValueError:
        pass
    # Tamaño inconsistente con el mensaje real
    p = bytearray(mk(b"hola"))
    p[11:15] = (99).to_bytes(4, "big")
    try:
        parse_packet(bytes(p))
        assert False
    except ValueError:
        pass


# ---------------- Paso 3: fragment_IP_packet ----------------
def test_no_fragmenta_si_cabe():
    pkt = mk(b"hola!")
    assert fragment_IP_packet(pkt, 21) == [pkt]       # justo = MTU
    assert fragment_IP_packet(pkt, 1000) == [pkt]


def test_fragmenta_150_con_mtu_80():
    pkt = mk(b"x" * 134)                              # 150 bytes totales
    assert len(pkt) == 150
    frags = fragment_IP_packet(pkt, 80)
    assert len(frags) == 3
    info = [(len(f), parse_packet(f)["offset"], parse_packet(f)["size"], parse_packet(f)["flag"])
            for f in frags]
    assert info == [(80, 0, 64, 1), (80, 64, 64, 1), (22, 128, 6, 0)], info
    assert all(len(f) <= 80 for f in frags)


def test_refragmentar_un_fragmento():
    pkt = mk(b"abcdefghij" * 13 + b"abcd")             # 134 bytes
    frag_mid = fragment_IP_packet(pkt, 80)[1]          # offset 64, flag 1, 64 bytes
    subs = fragment_IP_packet(frag_mid, 50)            # payload 34
    info = [(parse_packet(s)["offset"], parse_packet(s)["size"], parse_packet(s)["flag"]) for s in subs]
    assert info == [(64, 34, 1), (98, 30, 1)], info    # el último HEREDA flag=1
    # fragmento final (flag 0) re-fragmentado: el último sub-fragmento mantiene flag=0
    frag_last = fragment_IP_packet(pkt, 80)[2]
    assert parse_packet(frag_last)["flag"] == 0
    subs2 = fragment_IP_packet(create_packet({**parse_packet(frag_last), "message": b"z" * 70,
                                              "offset": 128}), 50)
    flags = [parse_packet(s)["flag"] for s in subs2]
    assert flags == [1, 1, 0], flags


def test_mtu_demasiado_chico():
    try:
        fragment_IP_packet(mk(b"x" * 50), HEADER_SIZE)
        assert False
    except ValueError:
        pass


def test_ttl_e_id_se_conservan():
    for f in fragment_IP_packet(mk(b"x" * 134, ttl=7, pkt_id=999), 50):
        p = parse_packet(f)
        assert p["ttl"] == 7 and p["id"] == 999 and p["ip"] == "127.0.0.1" and p["port"] == 8885


# ---------------- Paso 4: reassemble_IP_packet ----------------
def test_fragmentar_y_reensamblar():
    for total, mtu in [(150, 80), (150, 50), (150, 55), (150, 17), (21, 100), (16, 100)]:
        pkt = mk((b"0123456789" * 20)[:total - 16])
        v2 = reassemble_IP_packet(fragment_IP_packet(pkt, mtu))
        print(f"total={total} MTU={mtu}: IP_packet_v1 == IP_packet_v2 ? {pkt == v2}")
        assert pkt == v2


def test_reensamblar_desordenado_y_duplicados():
    pkt = mk(bytes(range(134)))
    frags = fragment_IP_packet(pkt, 50)
    random.Random(1).shuffle(frags)
    assert reassemble_IP_packet(frags) == pkt
    assert reassemble_IP_packet(frags + frags[:2]) == pkt


def test_reensamblar_incompleto_da_none():
    pkt = mk(bytes(range(134)))
    frags = fragment_IP_packet(pkt, 50)
    assert len(frags) == 4
    for i in range(len(frags)):                        # falta cualquiera (inicio, medio o final)
        assert reassemble_IP_packet(frags[:i] + frags[i + 1:]) is None, i
    assert reassemble_IP_packet([frags[0]]) is None    # lista de largo 1 pero incompleta
    assert reassemble_IP_packet([]) is None
    full = mk(b"hola!")
    assert reassemble_IP_packet([full]) == full        # lista de largo 1 pero completa


def test_fuzz_refragmentacion_en_cadena():
    rnd = random.Random(42)
    for _ in range(300):
        msg = bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 400)))
        pkt = mk(msg, pkt_id=rnd.randrange(65536))
        frags = [pkt]
        for _ in range(rnd.randrange(1, 4)):           # varios enlaces seguidos con MTU distintos
            mtu = rnd.randrange(HEADER_SIZE + 1, 200)
            frags = [s for f in frags for s in fragment_IP_packet(f, mtu)]
        rnd.shuffle(frags)
        assert reassemble_IP_packet(frags) == pkt


def test_utf8_cortado_en_medio_de_un_caracter():
    msg = "ñandú ✓ ".encode("utf-8") * 10
    pkt = mk(msg)
    frags = fragment_IP_packet(pkt, 30)                # payload 14: corta caracteres multibyte
    out = parse_packet(reassemble_IP_packet(frags))["message"]
    assert out.decode("utf-8") == msg.decode("utf-8")


# ---------------- Paso 6: buffer por ID ----------------
def test_buffer_por_id_orden_desorden_intercalado():
    a = fragment_IP_packet(mk(b"A" * 100, pkt_id=101), 50)
    b = fragment_IP_packet(mk(b"B" * 100, pkt_id=202), 50)
    secuencias = {
        "orden": a + b,
        "desorden": a[::-1] + b[::-1],
        "intercalado": [x for pair in zip(a, b) for x in pair],
    }
    for nombre, seq in secuencias.items():
        buffers, listos = {}, []
        for frag in seq:
            c = store_and_reassemble(buffers, frag, parse_packet(frag)["id"])
            if c is not None:
                listos.append(parse_packet(c)["message"])
        assert sorted(listos) == [b"A" * 100, b"B" * 100], nombre
        assert buffers == {}, nombre                   # se limpia lo ya reensamblado


# ---------------- Paso 2: check_routes con MTU ----------------
def test_check_routes_devuelve_mtu_y_round_robin():
    router.rr_state.clear()
    r2 = "rutas/rutas_R2_v3_mtu.txt"
    seq = [check_routes(r2, ("127.0.0.1", 8885)) for _ in range(4)]
    assert seq == [(("127.0.0.1", 8883), 50), (("127.0.0.1", 8884), 80)] * 2, seq
    assert check_routes(r2, ("127.0.0.1", 8881)) == (("127.0.0.1", 8881), 100)
    assert check_routes(r2, ("127.0.0.1", 9999)) == (None, None)
    nh, mtu = check_routes(r2, ("10.0.0.1", 8883))     # se puede desempaquetar siempre
    assert nh is None and mtu is None


def test_r5_sin_barra_es_slash32():
    router.rr_state.clear()
    r5 = "rutas/rutas_R5_v3_mtu.txt"
    assert check_routes(r5, ("127.0.0.1", 8881)) == (("127.0.0.1", 8884), 140)
    assert check_routes(r5, ("127.0.0.1", 8881)) == (("127.0.0.1", 8883), 55)
    assert check_routes(r5, ("127.0.0.2", 8881)) == (None, None)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} pruebas pasaron.")
