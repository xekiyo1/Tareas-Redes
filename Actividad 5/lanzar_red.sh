#!/usr/bin/env bash
# Levanta varios routers a la vez, cada salida con prefijo [Rn].
# Uso: ./lanzar_red.sh <sufijo_tabla> <ids de routers...>
# Ejemplos:
#   ./lanzar_red.sh v3 1 2 3 4 5                 # 5 routers (puertos 8881..8885)
#   ./lanzar_red.sh ext 0 1 2 3 4 5 6            # topología extendida
#   ./lanzar_red.sh v3_default 1 2 3 4 5         # con ruta default (levanta aparte el 7000)
#   ./lanzar_red.sh v2 1 2 3                     # ejemplo 2 (3 routers)
# Ctrl-C detiene todos los routers.
cd "$(dirname "$0")"
SUF="$1"; shift
if [ -z "$SUF" ] || [ "$#" -eq 0 ]; then
  sed -n '2,10p' "$0"; exit 1
fi
pids=()
trap 'kill "${pids[@]}" 2>/dev/null' INT TERM EXIT
for n in "$@"; do
  python3 -u router.py 127.0.0.1 $((8880 + n)) "rutas/rutas_R${n}_${SUF}.txt" \
    > >(sed -u "s/^/[R$n] /") 2>&1 &
  pids+=($!)
done
wait
