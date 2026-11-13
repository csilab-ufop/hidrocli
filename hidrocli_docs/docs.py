"""Generate the Hidro documentation wiki pages.

This is the implementation of the ``hidro-docs`` console command.  It runs
``pydoc-markdown``, applies the wiki markdown post-processing, and finally
regenerates the curated ``hidro models`` page from the ORM models.
"""

from __future__ import annotations

import ast
import html
import importlib.util
import inspect
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

def find_project_root() -> Path:
    """Locate the source checkout, even when installed in site-packages."""
    candidates = [Path.cwd(), Path(__file__).resolve().parent]
    for base in candidates:
        for path in (base, *base.parents):
            if (
                (path / "pyproject.toml").is_file()
                and (path / "hidrocli" / "models" / "hidro.py").is_file()
            ):
                return path
    raise SystemExit(
        "could not locate the HidroCLI source checkout; run hidro-docs "
        "from the repository root"
    )


ROOT = find_project_root()
WIKI_DIR = ROOT / "wiki"
MODEL_FILE = ROOT / "hidrocli" / "models" / "hidro.py"
OUTPUT_FILE = WIKI_DIR / "hidro models.md"

COLUMN_TYPES = {
    "BigInteger": "int",
    "DateTime": "datetime",
    "Float": "float",
    "Integer": "int",
    "SmallInteger": "int",
    "String": "str",
    "Text": "str",
}

DOC_TYPE = re.compile(
    r"^(int|float|string|str|datetime|date|bool)\s*:\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Field:
    name: str
    type_name: str
    description: str
    markdown_name: bool = False


@dataclass
class Group:
    title: str
    fields: list[Field] = field(default_factory=list)
    collapsible: bool = False


@dataclass
class Model:
    class_name: str
    title: str
    table: str | None
    description: str
    anchor: str
    groups: list[Group] = field(default_factory=list)
    extra_fields: list[Field] = field(default_factory=list)


def column_type(node: ast.AST) -> str:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return "unknown"
    if not node.args:
        return "unknown"
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        return COLUMN_TYPES.get(arg.id, arg.id.lower())
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
        return COLUMN_TYPES.get(arg.func.id, arg.func.id.lower())
    return "unknown"


def split_doc(doc: str | None, fallback_type: str) -> tuple[str, str]:
    text = inspect.cleandoc(doc or "").strip()
    match = DOC_TYPE.match(text)
    if match:
        type_name = match.group(1).lower()
        text = match.group(2).strip()
    else:
        type_name = fallback_type

    if type_name == "string":
        type_name = "str"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    description = "\n".join(lines)
    if not description:
        description = "—"
    else:
        description = description[0].upper() + description[1:]
        if description[-1] not in ".!?":
            description += "."
    return type_name, description


def read_models() -> list[Model]:
    tree = ast.parse(MODEL_FILE.read_text())
    models: list[Model] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        table = None
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "__tablename__"
            ):
                table = ast.literal_eval(stmt.value)
                break

        fields: list[Field] = []
        body = node.body
        for index, stmt in enumerate(body[:-1]):
            if not (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and not stmt.targets[0].id.startswith("__")
            ):
                continue
            value = stmt.value
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "Column"
            ):
                continue

            doc_node = body[index + 1]
            doc = None
            if (
                isinstance(doc_node, ast.Expr)
                and isinstance(doc_node.value, ast.Constant)
                and isinstance(doc_node.value.value, str)
            ):
                doc = doc_node.value.value

            type_name, description = split_doc(doc, column_type(value))
            fields.append(
                Field(
                    name=stmt.targets[0].id,
                    type_name=type_name,
                    description=description,
                )
            )

        if not fields:
            continue

        models.append(
            Model(
                class_name=node.name,
                title=node.name,
                table=table,
                description="",
                anchor="",
                groups=[Group("", fields)],
            )
        )

    return models


def by_names(*names: str) -> Callable[[str], bool]:
    accepted = set(names)
    return lambda name: name in accepted


def by_prefix(prefix: str) -> Callable[[str], bool]:
    return lambda name: name.startswith(prefix)


def apply_groups(
    fields: list[Field],
    rules: list[tuple[str, Callable[[str], bool], bool]],
) -> list[Group]:
    groups = [Group(title, collapsible=collapsible) for title, _, collapsible in rules]
    remaining: list[Field] = []
    for item in fields:
        for group, (_, predicate, _) in zip(groups, rules):
            if predicate(item.name):
                group.fields.append(item)
                break
        else:
            remaining.append(item)
    if remaining:
        groups.append(Group("Other", fields=remaining))
    return [group for group in groups if group.fields]


# Curated metadata: (model class, display title, table, description).
SHARED = [
    (
        "HidroBaseModel",
        "Shared fields",
        None,
        "Audit and identity columns inherited by every persisted model.",
        "shared-fields",
    ),
]

REFERENCE = [
    ("Basin", "Bacia", "Bacia", "Hydrographic basins.", "bacia-basin"),
    ("SubBasin", "SubBacia", "SubBacia", "Hydrographic sub-basins.", "subbacia-subbasin"),
    ("Entity", "Entidade", "Entidade", "Agencies and entities associated with stations.", "entidade-entity"),
    ("Township", "Municipio", "Municipio", "Municipalities.", "municipio-township"),
    ("River", "Rio", "Rio", "Rivers.", "rio-river"),
    ("State", "Estado", "Estado", "States and other South American countries.", "estado-state"),
    (
        "Station",
        "Estacao",
        "Estacao",
        "Hydrometeorological stations, including location, operator, observation periods, and network types.",
        "estacao-station",
    ),
]

SERIES = [
    (
        "Rain",
        "Chuvas",
        "Chuvas",
        "Monthly rainfall records with daily totals and status flags.",
        "chuvas-rain",
    ),
    (
        "Stage",
        "Cotas",
        "Cotas",
        "Monthly stage (water-level) records with daily values and status flags.",
        "cotas-stage",
    ),
    (
        "FlowRate",
        "Vazoes",
        "Vazoes",
        "Monthly flow-rate records with daily values and status flags.",
        "vazoes-flowrate",
    ),
    (
        "DischargeMeasurement",
        "ResumoDescarga",
        "ResumoDescarga",
        "Liquid-discharge measurement summaries.",
        "resumodescarga-dischargemeasurement",
    ),
    (
        "Sediments",
        "Sedimentos",
        "Sedimentos",
        "Sediment measurements and their corresponding liquid-discharge data.",
        "sedimentos-sediments",
    ),
    (
        "RatingCurve",
        "CurvaDescarga",
        "CurvaDescarga",
        "Stage-discharge rating curves, equations, and validity periods.",
        "curvadescarga-ratingcurve",
    ),
    (
        "WaterQuality",
        "QualAgua",
        "QualAgua",
        "Water-quality measurements. Parameter columns follow the ANA codes; status flags are stored in QualAguaStatus.",
        "qualagua-waterquality",
    ),
    (
        "WaterQualityStatus",
        "QualAguaStatus",
        "QualAguaStatus",
        "Status flags for each water-quality parameter.",
        "qualaguastatus-waterqualitystatus",
    ),
    (
        "Granulometry",
        "Granulometria",
        "Granulometria",
        "Granulometric analyses of bed material, bed load, and suspended sediment.",
        "granulometria-granulometry",
    ),
    (
        "CrossSection",
        "PerfilTransversal",
        "PerfilTransversal",
        "Cross-section surveys.",
        "perfiltransversal-crosssection",
    ),
    (
        "VerticalCrossSection",
        "PerfilTransversalVert",
        "PerfilTransversalVert",
        "Vertical measurements within cross-section surveys.",
        "perfiltransversalvert-verticalcrosssection",
    ),
]

MODEL_INFO = {
    class_name: (title, table, description, anchor)
    for class_name, title, table, description, anchor in SHARED + REFERENCE + SERIES
}

EXTRA_FIELDS = {
    "Rain": [
        Field("`Chuva01`..`Chuva31`", "float", "Daily rainfall for days 1–31 of the month (mm).", True),
        Field("`Chuva01Status`..`Chuva31Status`", "int", "Status flag for each daily rainfall value.", True),
    ],
    "Stage": [
        Field("`Cota01`..`Cota31`", "float", "Daily stage for days 1–31 of the month (cm).", True),
        Field("`Cota01Status`..`Cota31Status`", "int", "Status flag for each daily stage value.", True),
    ],
    "FlowRate": [
        Field("`Vazao01`..`Vazao31`", "float", "Daily flow rate for days 1–31 of the month (m3/s).", True),
        Field("`Vazao01Status`..`Vazao31Status`", "int", "Status flag for each daily flow-rate value.", True),
    ],
    "WaterQualityStatus": [
        Field("`QualAgua001Status`..`QualAgua147Status`", "int", "Status flag for each water-quality parameter.", True),
    ],
}

FIELD_ORDER: dict[tuple[str, str], list[str]] = {
    ("Station", "Identification"): [
        "Codigo",
        "Nome",
        "CodigoAdicional",
        "BaciaCodigo",
        "SubBaciaCodigo",
        "RioCodigo",
        "MunicipioCodigo",
        "EstadoSigla",
    ],
    ("Station", "Location"): ["Latitude", "Longitude", "Altitude", "AreaDrenagem"],
    ("Station", "Operation"): [
        "OperadoraCodigo",
        "OperadoraUnidade",
        "OperadoraSubUnidade",
        "ResponsavelCodigo",
        "ResponsavelUnidade",
        "Operando",
        "UltimaAtualizacao",
    ],
    ("WaterQuality", "Measurement metadata"): [
        "Data",
        "NivelConsistencia",
        "NumMedicao",
        "EstacaoCodigo",
        "Choveu",
        "PosHorizColeta",
        "PosVertColeta",
        "Profundidade",
    ],
}

GROUP_RULES: dict[str, list[tuple[str, Callable[[str], bool], bool]]] = {
    "Station": [
        (
            "Identification",
            by_names(
                "Codigo",
                "Nome",
                "CodigoAdicional",
                "BaciaCodigo",
                "SubBaciaCodigo",
                "RioCodigo",
                "MunicipioCodigo",
                "EstadoSigla",
            ),
            False,
        ),
        ("Location", by_names("Latitude", "Longitude", "Altitude", "AreaDrenagem"), False),
        (
            "Operation",
            by_names(
                "OperadoraCodigo",
                "OperadoraUnidade",
                "OperadoraSubUnidade",
                "ResponsavelCodigo",
                "ResponsavelUnidade",
                "Operando",
                "UltimaAtualizacao",
            ),
            False,
        ),
        ("Observation periods", by_prefix("Periodo"), False),
        ("Station types", by_prefix("TipoEstacao"), False),
        ("Network types", by_prefix("TipoRede"), False),
    ],
    "WaterQuality": [
        (
            "Measurement metadata",
            by_names(
                "Data",
                "NivelConsistencia",
                "NumMedicao",
                "PosHorizColeta",
                "PosVertColeta",
                "Profundidade",
                "Choveu",
                "EstacaoCodigo",
            ),
            False,
        ),
        ("Water-quality parameters", lambda name: True, True),
    ],
    "Granulometry": [
        (
            "Sampling metadata",
            by_names(
                "EstacaoCodigo",
                "NivelConsistencia",
                "Data",
                "HoraInicial",
                "HoraFinal",
                "Cota",
                "Largura",
                "TipoAmostra",
                "TipoColeta",
                "TipoEquip",
                "ProfTotal",
                "OrdemColeta",
                "DistPTOInicial",
                "ChuvaUlt48",
            ),
            False,
        ),
        ("Bed material (`MatFundo*`)", by_prefix("MatFundo"), False),
        ("Bed load (`MatArraste*`)", by_prefix("MatArraste"), False),
        ("Suspended sediment (`MatSusp*`)", by_prefix("MatSusp"), False),
    ],
}


def escape_cell(text: str) -> str:
    parts = [html.escape(line, quote=False).replace("|", "\\|") for line in text.split("\n")]
    return "<br>".join(parts)


def field_table(fields: list[Field]) -> list[str]:
    lines = ["| Field | Type | Description |", "| :--- | :--- | :--- |"]
    for item in fields:
        name = item.name if item.markdown_name else f"`{item.name}`"
        description = escape_cell(item.description)
        lines.append(f"| {name} | `{item.type_name}` | {description} |")
    return lines


def render_table(model: Model, group: Group) -> list[str]:
    lines: list[str] = []
    if group.title:
        lines.append(f"#### {group.title}")
        lines.append("")
    fields = group.fields
    if group.collapsible:
        lines.append("<details>")
        lines.append(f"<summary><strong>Show {len(fields)} fields</strong></summary>")
        lines.append("")
        lines.extend(field_table(fields))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    else:
        lines.extend(field_table(fields))
        lines.append("")
    return lines


def render_model(model: Model) -> list[str]:
    heading = f"{model.title} ({model.class_name})" if model.table else model.title
    lines = [f"### {heading}", ""]
    metadata = f"*Model: `{model.class_name}`"
    if model.table:
        metadata += f" · Table: `{model.table}`"
    metadata += "*"
    lines.extend([metadata, "", model.description, ""])

    for group in model.groups:
        lines.extend(render_table(model, group))

    if model.extra_fields:
        lines.extend(render_table(model, Group("Generated columns", model.extra_fields)))

    return lines


def build_page(models: list[Model]) -> str:
    by_class = {model.class_name: model for model in models}

    for class_name, model in by_class.items():
        title, table, description, anchor = MODEL_INFO[class_name]
        model.title = title
        model.table = table
        model.description = description
        model.anchor = anchor
        rules = GROUP_RULES.get(class_name)
        if rules:
            model.groups = apply_groups([f for group in model.groups for f in group.fields], rules)
            for group in model.groups:
                order = FIELD_ORDER.get((class_name, group.title))
                if order:
                    position = {name: index for index, name in enumerate(order)}
                    group.fields.sort(key=lambda item: position.get(item.name, len(order)))
        model.extra_fields = EXTRA_FIELDS.get(class_name, [])

    lines = [
        "# Hidro Models",
        "",
        "ORM models for the Hidro database. Field descriptions follow the ANA HIDRO 1.0 "
        "data dictionary (Manual do Usuário, Apêndice A) and the ANA Hidro WebServices payloads.",
        "",
        "## Contents",
        "",
        "**Shared**",
        "",
        "- [Shared fields](#shared-fields)",
        "",
        "**Reference tables**",
        "",
    ]
    for class_name, title, _, _, anchor in REFERENCE:
        lines.append(f"- [{title}](#{anchor})")

    lines.extend(["", "**Time-series tables**", ""])
    for class_name, title, _, _, anchor in SERIES:
        lines.append(f"- [{title}](#{anchor})")

    lines.extend(["", "## Shared fields", ""])
    for class_name, _, _, _, _ in SHARED:
        model = by_class[class_name]
        lines.append(model.description)
        lines.append("")
        for group in model.groups:
            lines.extend(field_table(group.fields))
            lines.append("")

    lines.extend(["## Reference tables", ""])
    for class_name, _, _, _, _ in REFERENCE:
        lines.extend(render_model(by_class[class_name]))

    lines.extend(["## Time-series tables", ""])
    for class_name, _, _, _, _ in SERIES:
        lines.extend(render_model(by_class[class_name]))

    lines.extend(
        [
            "---",
            "",
            "*Generated from `hidrocli/models/hidro.py` by `hidro-docs`.*",
            "",
        ]
    )
    return "\n".join(lines)


def generate_models_page() -> None:
    """Regenerate the curated Hidro models wiki page."""
    if not OUTPUT_FILE.parent.is_dir():
        raise SystemExit(
            "wiki directory not found; run `git submodule update --init wiki` first"
        )
    models = read_models()
    OUTPUT_FILE.write_text(build_page(models))
    print(f"wrote {OUTPUT_FILE}")


def run_pydoc_markdown() -> None:
    """Run pydoc-markdown from the project root."""
    if importlib.util.find_spec("pydoc_markdown") is None:
        raise SystemExit(
            "pydoc-markdown is not installed; run "
            "`.venv/bin/python -m pip install -e '.[dev]'`"
        )
    subprocess.run(
        [sys.executable, "-c", "from pydoc_markdown.main import cli; cli()"],
        cwd=ROOT,
        check=True,
    )


def post_process_wiki() -> None:
    """Add the separator layout used by the generated wiki pages."""
    for path in sorted(WIKI_DIR.glob("*.md")):
        text = path.read_text()
        text = re.sub(
            r'(<a id=".*?"></a>\n\n## )',
            r'\n---\n\n\1',
            text,
        )
        text = re.sub(
            r'(?<!\n---\n\n)(?=^#### )',
            r'\n---\n\n',
            text,
            flags=re.MULTILINE,
        )
        path.write_text(text)

    # pydoc-markdown's mkdocs renderer writes these files, but the published
    # documentation is a GitHub wiki, not an MkDocs site.
    for artifact in ("mkdocs.yml", ".generated-files.txt"):
        (WIKI_DIR / artifact).unlink(missing_ok=True)


def main() -> None:
    """Build every wiki page, then regenerate the curated models page."""
    run_pydoc_markdown()
    post_process_wiki()
    generate_models_page()


if __name__ == "__main__":
    main()
