# SPL Codebase Metrics

## File and LOC Breakdown

- Files under `c_engine_pl/`: **43**
- Maintained SPL files excluding `build/`: **36**
- Maintained SPL files excluding `build/` and generated bindings: **34**
- C source files: **6**
- Maintained headers: **5**
- Variant configurations: **18**
- C source LOC (physical / non-empty): **7596 / 6813**
- Maintained header LOC (physical / non-empty): **206 / 175**
- Variant configuration LOC (physical / non-empty): **499 / 499**

## Guarded LOC Per Compile-Time Feature

- Compile-time features with a `CFG_*` binding: **56**
- Minimum / median / maximum guarded non-empty LOC: **1 / 9.0 / 279**
- First quartile / third quartile: **2.75 / 21.25**
- Features with guarded LOC <= 5: **21**
- Features with guarded LOC <= 10: **30**
- Features with guarded LOC <= 20: **41**

Top guarded-LOC features:

- `Magic Bitboards`: **279** guarded non-empty LOC
- `Pondering`: **242** guarded non-empty LOC
- `Opening Book`: **233** guarded non-empty LOC
- `Castling`: **120** guarded non-empty LOC
- `Null Move Pruning`: **108** guarded non-empty LOC
- `Transposition Table`: **98** guarded non-empty LOC
- `Piece Lists`: **86** guarded non-empty LOC
- `Bitboards`: **45** guarded non-empty LOC
- `En Passant`: **36** guarded non-empty LOC
- `Piece-Square Tables`: **34** guarded non-empty LOC

This metric is intentionally conservative: it counts non-empty lines lexically enclosed by `CFG_*` preprocessor conditions in maintained C sources and headers.
A full sorted table with feature names, families, and `CFG_*` flags is exported in `feature_guard_loc_table.md` and `feature_guard_loc.csv`.
