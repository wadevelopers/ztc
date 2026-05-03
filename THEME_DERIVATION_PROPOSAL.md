# Propuesta: derivacion de paleta legacy con vendor de alacritty-theme

## El problema

Cuando clonamos un tema built-in de Zellij a un user theme editable, o
cuando sincronizamos los colores a `alacritty.toml`, necesitamos
**reducir** los componentes UI del formato nuevo de Zellij (10+ componentes
con 6 slots cada uno) a una **paleta legacy plana** de 11 slots
(`fg, bg, black, red, green, yellow, blue, magenta, cyan, white, orange`).

Esa reduccion es **fundamentalmente lossy** porque:

1. El formato nuevo tiene ~54 slots de color (10 componentes × 6 slots).
2. La paleta legacy tiene 11 slots.
3. Los autores de los `.kdl` built-in de Zellij **no siguen una
   convencion uniforme** sobre que slot del formato nuevo corresponde
   a que color "ANSI". Cada autor decide.

### Ejemplos concretos del problema

**`gruber-darker`**: nuestra derivacion da
```
yellow  -> #ffffff   (deberia ser #ffdd33 — el amarillo iconico del tema)
magenta -> #ffffff
orange  -> #95a99f   (un verde-grisaceo, no naranja)
```

El amarillo `#ffdd33` esta en el `.kdl`, pero en `text_unselected.emphasis_3`
y `ribbon_selected.background`, no en `table_title.emphasis_0` (que es de
donde derivamos `yellow`).

**`catppuccin-latte`**: nuestra derivacion da
```
magenta -> #d20f39   (es el red, no es magenta)
yellow  -> #fe640b   (es el orange canonico, no el yellow)
```

El autor de catppuccin-latte puso colores en posiciones distintas a las
que asume nuestra derivacion.

### Por que la regla actual no se puede arreglar con otra regla

Cualquier regla de derivacion `slot_legacy <- componente.subslot` que
elijamos va a fallar para algunos temas. No hay una eleccion de
componente/subslot que produzca el resultado correcto para los **40
temas built-in** simultaneamente, porque los autores los disenaron
con criterios distintos.

La paleta legacy es **mas pobre** que el formato nuevo. Hay decisiones
artisticas (el amarillo de `gruber-darker`, el rosa de `catppuccin`, etc.)
que **no caben** en los 11 slots ANSI. Se pueden aproximar, no
reproducir 1:1.

---

## Inventario completo de divergencias

Comparando nuestra derivacion legacy (regla unica desde el `.kdl`) vs la
paleta canonica de `alacritty-theme` (cuando existe), de los 40 temas
built-in:

- **30 temas tienen al menos una divergencia** (algunos sutiles, otros
  severos).
- **9 temas matchean al 100%**: `blade-runner`, `cyber-noir`, `iceberg-light`
  (no estan en alacritty-theme — no se pudieron comparar), `lucario`,
  `menace`, `molokai-dark`, `one-half-dark`, `retro-wave`,
  `atelier-sulphurpool` (ninguna divergencia detectable porque no hay
  alacritty-theme equivalente).
- **1 tema con slots sospechosos sin equivalente**: `ao` (red derivado
  como `#000000`).

### Severidad: SEVERO (slot completamente erroneo)

Estos casos tienen slots con valor visualmente equivocado (color
totalmente distinto del concepto que el slot representa).

| Tema | Slot | Derivamos | Canonico | Comentario |
|---|---|---|---|---|
| `gruber-darker` | yellow | `#ffffff` | `#ffdd33` | blanco en vez de amarillo |
| `gruber-darker` | magenta | `#ffffff` | `#9e95c7` | blanco en vez de violeta |
| `ayu-light` | bg | `#e7eaed` | `#fcfcfc` | gris claro en vez de casi-blanco |
| `ayu-light` | black | `#e7eaed` | `#010101` | gris claro en vez de negro real |
| `ayu-light` | white | `#fcfcfc` | `#c1c1c1` | casi-blanco en vez de gris |
| `ayu-light` | cyan | `#478acc` | `#51b891` | azul en vez de turquesa/verde |
| `ayu-mirage` | cyan | `#444b55` | `#98e6ca` | gris-azul en vez de turquesa |
| `ayu-mirage` | green | `#d5ff80` | `#53bf97` | amarillo-verde en vez de verde-azulado |
| `ayu-mirage` | magenta | `#dfbfff` | `#ec7171` | violeta vs salmon |
| `catppuccin-latte` | bg | `#dce0e8` | `#eff1f5` | usa surface en vez de base |
| `catppuccin-latte` | black | `#dce0e8` | `#5c5f77` | gris claro en vez de gris oscuro |
| `catppuccin-latte` | yellow | `#fe640b` | `#df8e1d` | naranja en vez de amarillo |
| `catppuccin-latte` | magenta | `#d20f39` | `#ea76cb` | rojo en vez de rosa |
| `catppuccin-latte` | cyan | `#04a5e5` | `#179299` | azul en vez de teal |
| `catppuccin-latte` | white | `#4c4f69` | `#acb0be` | gris muy oscuro en vez de claro |
| `dayfox` | white | `#643f61` | `#f2e9e1` | medio-oscuro en vez de claro |
| `dayfox` | bg | `#d3c7bb` | `#f6f2ee` | beige saturado vs casi-blanco |
| `dayfox` | black | `#d3c7bb` | `#352c24` | claro en vez de oscuro |
| `dayfox` | yellow | `#955f61` | `#ac5402` | rojizo en vez de marron |
| `dracula` | bg | `#000000` | `#282a36` | negro en vez del violeta canonico |
| `dracula` | yellow | `#ffb86c` | `#f1fa8c` | naranja en vez de amarillo |
| `dracula` | blue | `#6272a4` | `#bd93f9` | gris-azul en vez del purpura iconico |
| `dracula` | white | `#ffffff` | `#bbbbbb` | blanco puro en vez de gris claro |
| `gruvbox-light` | yellow | `#980005` | `#d79921` | rojo en vez de amarillo (!) |
| `gruvbox-light` | white | `#3c3836` | `#7c6f64` | gris muy oscuro en vez de medio |
| `gruvbox-light` | black | `#ebdbb2` | `#fbf1c7` | beige saturado vs claro |
| `gruvbox-dark` | yellow | `#d65d0e` | `#d79921` | naranja en vez de amarillo |
| `gruvbox-dark` | white | `#fbf1c7` | `#a89984` | claro vs gris medio |
| `iceberg-dark` | green | `#84a0c6` | `#b4be82` | azul en vez de verde (!) |
| `iceberg-dark` | blue | `#b4be82` | `#84a0c6` | verde en vez de azul (!) |
| `tokyo-night-light` | bg | `#0f0f14` | `#d6d8df` | DARK en vez de LIGHT (!) |
| `tokyo-night-light` | black | `#0f0f14` | `#343b58` | dark vs medio |
| `tokyo-night-light` | green | `#485e30` | `#41a6b5` | verde en vez de teal |
| `pencil-light` | black | `#f1f1f1` | `#212121` | invertido completamente |
| `pencil-light` | red | `#b6d6fd` | `#c30771` | azul claro en vez de rojo |
| `pencil-light` | white | `#424242` | `#e0e0e0` | invertido |
| `nord` | bg | `#3b4252` | `#2e3440` | usa nord1 en vez de nord0 |
| `nord` | yellow | `#d08770` | `#ebcb8b` | naranja en vez de amarillo |

### Severidad: SUTIL (mismo concepto, hex levemente distinto)

| Tema | Slots con diferencias menores |
|---|---|
| `ayu-dark` | bg, black, red, green, yellow, blue, magenta (sutiles), white |
| `catppuccin-frappe` | bg, black, yellow, cyan, white |
| `catppuccin-macchiato` | bg, black, yellow, cyan, white |
| `catppuccin-mocha` | bg, black, yellow, cyan, white |
| `everforest-dark` | bg, black, yellow |
| `everforest-light` | bg, black, yellow, white |
| `flexoki-dark` | black, red, green, yellow, magenta, cyan, white |
| `kanagawa` | bg, black, yellow, cyan, white |
| `night-owl` | bg, black, red, green, yellow, blue, magenta, cyan, white |
| `nightfox` | bg, black, yellow, white |
| `onedark` | bg, black, red, white |
| `solarized-dark` | bg, yellow |
| `solarized-light` | bg, yellow |
| `terafox` | bg, black, yellow, white |
| `tokyo-night` | bg, black, red, yellow, magenta, cyan, white |
| `tokyo-night-storm` | bg, black, red, yellow, magenta, cyan, white |
| `vesper` | yellow |
| `tokyo-night-dark` | black, red, yellow, magenta, cyan, white |

### Resumen

- **15 temas** tienen al menos un problema severo (slot conceptualmente
  equivocado).
- **15 temas** tienen solo diferencias sutiles (mismo concepto, hex
  levemente distinto).
- Los problemas mas comunes son:
  - `bg` y `black` derivados desde slots equivocados (afecta a
    catppuccin-*, gruvbox-*, dayfox, nord, etc.).
  - `yellow` que sale como naranja, blanco, o rojo (ningun tema clava
    yellow en `table_title.emphasis_0`).
  - Inversion bg/black en temas light (gruvbox-light, dayfox,
    pencil-light).
  - Casos extremos como `iceberg-dark` con green y blue intercambiados,
    o `tokyo-night-light` con bg DARK.

Esto confirma que la regla unica de derivacion **NO es viable** para
estos temas — la unica forma de obtener la paleta canonica es leerla
desde una fuente curada manualmente.

---

## La solucion propuesta

Aprovechar el repo oficial **`alacritty/alacritty-theme`** que tiene
paletas ANSI canonicas para 174 temas, **manualmente curadas por la
comunidad** durante mas de 5 anos.

Para los temas Zellij cuyo nombre matchea con un tema en `alacritty-theme`,
usar la paleta de `alacritty-theme` como **autoridad** para los slots
legacy. Asi evitamos inventar mappings nosotros.

### Coverage analysis

De los 40 temas built-in que vendorizamos, cruzando contra los 174 de
`alacritty-theme`:

**Match exacto (26 temas)** — mismo nombre:
> ayu-dark, ayu-light, ayu-mirage, catppuccin-frappe, catppuccin-latte,
> catppuccin-macchiato, catppuccin-mocha, dayfox, dracula, everforest-dark,
> everforest-light, gruber-darker, gruvbox-dark, gruvbox-light, night-owl,
> nightfox, nord, onedark, pencil-light, solarized-dark, solarized-light,
> terafox, tokyo-night, tokyo-night-light, tokyo-night-storm, vesper

**Match con alias (4 temas)** — variaciones de nombre:
| Zellij | Alacritty-theme |
|---|---|
| `flexoki-dark` | `flexoki` |
| `iceberg-dark` | `iceberg` |
| `kanagawa` | `kanagawa_wave` |
| `tokyo-night-dark` | `tokyo_night` |

**Sin match (10 temas)**:
> ao, atelier-sulphurpool, blade-runner, cyber-noir, iceberg-light,
> lucario, menace, molokai-dark, one-half-dark, retro-wave

**Cobertura total: 30/40 (75%)** con vendor.

### Como funcionaria

```
                    ┌─────────────────────────────────────┐
        Zellij      │  src/...assets/zellij_themes/       │
        builtin     │    catppuccin-latte.kdl             │
        kdl    ─────┤    gruber-darker.kdl                │
                    │    ...                              │
                    └────────────────┬────────────────────┘
                                     │
                                     │ (formato nuevo
                                     │  componentes UI)
                                     ▼
                          ┌─────────────────────┐
                          │  load_bundled_theme  │  ← componentes ricos
                          └──────────┬───────────┘     (text_unselected,
                                     │                  ribbon_selected, etc.)
                                     │
                                     │   Sigue siendo la fuente
                                     │   unica para `build_textual_theme`
                                     │   (primary, accent, secondary, ...)
                                     │
                                     ▼
                          ┌─────────────────────────┐
                          │ derive_legacy_slots(name) │
                          └──────────┬──────────────┘
                                     │
                                     ▼
                  ┌──────────────────┴──────────────────┐
                  │                                     │
        ¿hay un .toml en              caer a la regla unica
        alacritty_themes/<name>?       desde los componentes
                  │                                     │
                  │ si                                  │ no (los 10)
                  ▼                                     ▼
        leer paleta canonica                  derivar de text_unselected,
        del .toml (10 slots ANSI)             ribbon_unselected, etc.
                  │                                     │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │  paleta legacy 11   │
                          │  slots para clone   │
                          │  + alacritty sync   │
                          └─────────────────────┘
```

### Implementacion concreta

1. **Vendorizar `alacritty-theme`** en
   `src/term_config_tui/assets/alacritty_themes/*.toml` (174 archivos,
   ~50KB total).
2. **Aliases zellij → alacritty** como dict pequeno en codigo:
   ```python
   ALACRITTY_THEME_ALIASES = {
       "flexoki-dark": "flexoki",
       "iceberg-dark": "iceberg",
       "kanagawa": "kanagawa_wave",
       "tokyo-night-dark": "tokyo_night",
   }
   ```
3. **Funcion `load_alacritty_theme(zellij_name)`** que aplica el alias y
   devuelve el `.toml` parseado o `None`.
4. **`derive_legacy_slots_from_bundled(name)`** se modifica:
   - Primero intenta `load_alacritty_theme(name)`. Si esta, devuelve
     sus 10 slots ANSI directamente (mas el `orange` derivado del .kdl
     porque alacritty no tiene slot orange).
   - Si no, deriva del `.kdl` con la regla unica actual.
5. **`build_textual_theme`** sigue usando los componentes ricos del .kdl
   (no cambia). Solo `foreground` y `background` se toman de la paleta
   resuelta.
6. **`THEME_OVERRIDES`** vuelve como dict opcional para correcciones
   puntuales en los 10 sin match (`{"gruber-darker": {"yellow": "#xxxx"}}`),
   solo si algo se ve mal. **No se anaden de antemano**, solo cuando
   reportes un problema.

### Estructura de los .toml de alacritty-theme

```toml
[colors.primary]
background = '#ffffff'
foreground = '#5c6166'

[colors.normal]
black   = '#000000'
red     = '#ff0000'
green   = '#00ff00'
yellow  = '#ffff00'
blue    = '#0000ff'
magenta = '#ff00ff'
cyan    = '#00ffff'
white   = '#ffffff'

[colors.bright]
...
```

Mapping de la paleta canonica a slots legacy:

| Slot legacy | Origen `.toml` |
|---|---|
| `bg` | `primary.background` |
| `fg` | `ribbon_unselected.background` (= bg de ribbons; sigue derivandose del `.kdl` Zellij — ver nota abajo) |
| `black` | `normal.black` |
| `red` | `normal.red` |
| `green` | `normal.green` |
| `yellow` | `normal.yellow` |
| `blue` | `normal.blue` |
| `magenta` | `normal.magenta` |
| `cyan` | `normal.cyan` |
| `white` | `normal.white` (o `primary.foreground`) |
| `orange` | sin equivalente — derivado del `.kdl` |

**Nota sobre `fg`**: este slot, en el modelo de Zellij, NO es el fg
canonico. Es el bg de los ribbons del propio Zellij. Por eso lo
seguimos derivando del `.kdl` (`ribbon_unselected.background`), no del
`.toml`. La paleta canonica de alacritty-theme no tiene un slot
equivalente al "fg de ribbon".

---

## Trade-offs honestos

### A favor

- **75% de los temas** quedan con paletas canonicas ANSI sin trabajo
  manual nuestro.
- **El "amarillo perdido" de gruber-darker se resuelve** automaticamente
  (alacritty-theme tiene gruber_darker con `yellow = #ffdd33`).
- **catppuccin-latte queda con red, magenta, yellow correctos**.
- Comunidad de Alacritty ya hizo las decisiones subjetivas dificiles.
- Cuando alacritty-theme actualice un tema, basta con re-vendorizar.

### En contra

- **Dos fuentes de datos** para 30 temas: `.kdl` para componentes ricos,
  `.toml` para paleta legacy. Riesgo de inconsistencia visual entre
  los dos formatos.
- **Vendor extra**: ~50KB de assets adicionales. Trivial en disco pero
  conceptualmente otro repo del que dependemos.
- **Si alacritty-theme cambia un tema** (raro pero posible) y nosotros
  no actualizamos, divergimos.
- **Los 10 sin match** siguen igual que ahora — alguno necesitara
  override manual cuando aparezca el problema.
- **Otros usos del `.toml`**: el formato Alacritty tambien define
  `colors.bright` y `colors.cursor`/`colors.selection`. Hoy no los
  usamos, pero podriamos en el futuro.

### Riesgo concreto: inconsistencia entre fuentes

El `.kdl` de Zellij dice "el rojo es X", el `.toml` de alacritty-theme
dice "el rojo es Y". ¿Cual usamos?

Mi propuesta: **`.toml` gana para slots legacy/ANSI**, `.kdl` gana para
los componentes UI (los slots que solo afectan al rendering del propio
Zellij).

En la practica los autores tienden a usar la misma paleta para ambos
formatos, asi que las inconsistencias deberian ser raras. Cuando
ocurran, la version de alacritty-theme es la que se usa para terminal
apps reales — eso es mas importante visualmente.

---

## Alternativas que descarte

### A) Diccionario per-tema en codigo

```python
THEME_MAPPINGS = {
    "gruber-darker": {
        "fg": "ribbon_unselected.base",
        "yellow": "text_unselected.emphasis_3",
        ...
    },
    ...
}
```

**Por que no**: ~440 decisiones manuales (40 temas × 11 slots).
Subjetivo (que slot del nuevo formato es "el yellow"?). Maintenance:
cuando Zellij saque un tema nuevo, hay que mapear a mano.

Es la solucion del usuario, factible pero menos eficiente que B.

### B) Alacritty-theme vendor (la propuesta principal)

Lo descrito arriba.

### C) Aceptar la inexactitud actual

No hacer nada. Documentar que el clone es aproximado. El usuario
ajusta a mano los slots que se ven mal.

**Por que no**: el clone deberia ser fiel para que tenga sentido. Si
no, mejor dejar el built-in y no clonarlo.

### D) Solo overrides puntuales sin vendor

Mantener la regla unica actual + dict THEME_OVERRIDES con correcciones
caso por caso. Va creciendo organicamente segun aparecen problemas.

**Por que no como solucion principal**: cubre menos en menos esfuerzo,
pero sin la base canonica de la comunidad de Alacritty. Para los temas
populares (catppuccin, dracula, gruvbox, tokyo-night) seguiriamos
deviniendo "bien suficiente" en vez de "exactamente bien".

**Pero**: D + B juntas tienen sentido. Para los 10 sin match en B,
usamos D segun reporten problemas.

---

## Resumen ejecutivo

- Problema: la paleta legacy es lossy y nuestra regla unica falla
  visualmente para varios temas built-in.
- Solucion: vendorizar `alacritty-theme` (174 .toml) y usarlos como
  fuente autoritativa para los slots ANSI/legacy de los 30/40 temas
  con match. Los 10 sin match siguen con la regla unica actual + override
  puntual cuando haga falta.
- Costo: ~50KB de assets adicionales, una funcion `load_alacritty_theme`
  con su mapping inverso, una tabla de aliases, modificar
  `derive_legacy_slots_from_bundled` para preferir el .toml cuando
  exista.
- Beneficio: 30 temas quedan con paletas canonicas exactas sin trabajo
  manual nuestro. catppuccin-latte, gruber-darker, monokai (via clone),
  dracula, etc. todos correctos automaticamente.
