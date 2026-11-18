#!/usr/bin/env bash
# Levanta varios routers a la vez, cada salida con prefijo [Rn]. Ctrl-C los detiene.
# Uso:  bash lanzar_red.sh <sufijo_tabla> <ids de routers...>
# Ej.:  bash lanzar_red.sh v3_mtu 1 2 3 4 5     # puertos 8881..8885, rutas/rutas_Rn_v3_mtu.txt
cd "$(dirname "$0")"
SUF="$1"; shift
if [ -z "$SUF" ] || [ "$#" -eq 0 ]; then sed -n '2,5p' "$0"; exit 1; fi
pids=()
trap 'kill "${pids[@]}" 2>/dev/null' INT TERM EXIT
for n in "$@"; do
  python3 -u router.py 127.0.0.1 $((8880 + n)) "rutas/rutas_R${n}_${SUF}.txt" \
    > >(sed -u "s/^/[R$n] /") 2>&1 &
  pids+=($!)
done
wait
