# TOAST-O-FROST — The Catalogue Photo of an Impossible Gadget

[![make.fun](https://make.fun/badge/the-catalogue-photo-of-an-2-20261121-0341.svg)](https://make.fun/competitions/the-catalogue-photo-of-an-2-20261121-0341)
[![Rank](https://make.fun/badge/the-catalogue-photo-of-an-2-20261121-0341/Usogakie/the-catalogue-photo-of-an-2-20261121-0341/rank.svg)](https://make.fun/competitions/the-catalogue-photo-of-an-2-20261121-0341)
[![Reward](https://make.fun/badge/the-catalogue-photo-of-an-2-20261121-0341/Usogakie/the-catalogue-photo-of-an-2-20261121-0341/reward.svg)](https://make.fun/competitions/the-catalogue-photo-of-an-2-20261121-0341)

A catalogue photograph of an impossible gadget, painted pixel by pixel in
pure-stdlib Python: **TOAST-O-FROST**, a brushed-chrome toaster (1200W,
CRISP ICE) that toasts ice cubes. A glowing ice cube pops out of its slot,
steaming, while a white plate beside it holds one spare ice cube as the
single accessory. Studio light, clean background, product as hero — exactly
as a real hardware catalogue would shoot a device that cannot exist.

## Run it

```sh
python3 main.py
```

Writes `/output/entry.png`: a 1024×1024 PNG, deterministic — identical
bytes on every run. No network, no third-party libraries, just `zlib` and
`struct` for the PNG encoder and a seeded RNG for the frost speckles.
