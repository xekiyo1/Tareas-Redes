"""Pruebas locales (sin levantar routers). Ejecutar: python3 test_router.py"""

import router
from router import check_routes, create_packet, parse_packet


def test_roundtrip():
    # 127.0.0.1 : 8885 : TTL 10 : "hola"
    v1 = bytes([127, 0, 0, 1]) + (8885).to_bytes(2, "big") + bytes([10]) + b"hola"
    parsed = parse_packet(v1)
    assert parsed == {"ip": "127.0.0.1", "port": 8885, "ttl": 10, "message": "hola"}
    v2 = create_packet(parsed)
    print("IP_packet_v1 == IP_packet_v2 ? {}".format(v1 == v2))
    assert v1 == v2


def test_utf8_y_largo_minimo():
    p = {"ip": "10.20.30.40", "port": 65535, "ttl": 255, "message": "ñandú ✓"}
    assert parse_packet(create_packet(p)) == p
    try:
        parse_packet(b"\x00\x01\x02")
        assert False, "debió fallar"
    except ValueError:
        pass


def test_rangos():
    for bad in ({"ip": "1.1.1.1", "port": 70000, "ttl": 1, "message": ""},
                {"ip": "1.1.1.1", "port": 80, "ttl": 256, "message": ""}):
        try:
            create_packet(bad)
            assert False, "debió fallar"
        except ValueError:
            pass


def test_check_routes_v2():
    r = "rutas/rutas_R2_v2.txt"
    assert check_routes(r, ("127.0.0.1", 8883)) == ("127.0.0.1", 8883)
    assert check_routes(r, ("127.0.0.1", 8881)) == ("127.0.0.1", 8881)
    assert check_routes(r, ("127.0.0.1", 8884)) is None       # fuera de la red
    assert check_routes(r, ("10.0.0.1", 8883)) is None


def test_round_robin_v3():
    router.rr_state.clear()
    r = "rutas/rutas_R2_v3.txt"
    seq = [check_routes(r, ("127.0.0.1", 8885))[1] for _ in range(6)]
    assert seq == [8883, 8884, 8883, 8884, 8883, 8884], seq
    # R1 (8881) tiene una sola ruta: no se ve afectado por el contador anterior
    assert check_routes(r, ("127.0.0.1", 8881)) == ("127.0.0.1", 8881)


def test_round_robin_independiente_por_area():
    """R2 extendido: dos áreas (8880-8881 y 8883-8886) con contadores separados."""
    router.rr_state.clear()
    r = "rutas/rutas_R2_ext.txt"
    a = [check_routes(r, ("127.0.0.1", 8880))[1] for _ in range(4)]   # área 1
    b = [check_routes(r, ("127.0.0.1", 8885))[1] for _ in range(6)]   # área 2
    assert a == [8880, 8881, 8880, 8881], a
    assert b == [8883, 8884, 8886, 8883, 8884, 8886], b
    # intercalado: avanzar un área no mueve la otra
    router.rr_state.clear()
    seq = []
    for _ in range(3):
        seq.append(("A", check_routes(r, ("127.0.0.1", 8881))[1]))
        seq.append(("B", check_routes(r, ("127.0.0.1", 8884))[1]))
    assert [x[1] for x in seq if x[0] == "A"] == [8880, 8881, 8880]
    assert [x[1] for x in seq if x[0] == "B"] == [8883, 8884, 8886]


def test_r5_ext_llega_a_r6():
    router.rr_state.clear()
    assert check_routes("rutas/rutas_R5_ext.txt", ("127.0.0.1", 8886)) is not None


def test_default_al_final():
    router.rr_state.clear()
    r = "rutas/rutas_R2_v3_default.txt"
    assert check_routes(r, ("8.8.8.8", 53)) == ("127.0.0.1", 7000)       # fuera de la red
    assert check_routes(r, ("127.0.0.1", 9999)) == ("127.0.0.1", 7000)   # puerto fuera de rango
    assert check_routes(r, ("127.0.0.1", 8881)) == ("127.0.0.1", 8881)   # interno no se captura


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} pruebas pasaron.")
