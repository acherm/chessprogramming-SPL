"""Export the FeatureIDE XML feature model to two textual formats:

  - outputs/feature_model.uvl   — Universal Variability Language (UVL)
  - outputs/feature_model.fml   — FAMILIAR textual syntax (FML)

Both exports first normalize the tree: when a group "X" has a direct
leaf feature child named "X" (modulo case/whitespace), they are
collapsed so the group's display name becomes the feature's name. This
removes confusing duplicates like `TimeManagement → Time Management`.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

XML_PATH = Path("outputs/feature_model.featureide.xml")
UVL_PATH = Path("outputs/feature_model.uvl")
FML_PATH = Path("outputs/feature_model.fml")

GROUP_TAGS = {"and", "or", "alt"}


@dataclass
class Node:
    name: str
    kind: str
    mandatory: bool = False
    children: list["Node"] = field(default_factory=list)


def parse_xml(elem) -> Node:
    tag = elem.tag
    name = elem.attrib.get("name", "?")
    mandatory = elem.attrib.get("mandatory", "false") == "true"
    kind = tag if tag in GROUP_TAGS else "feature"
    node = Node(name=name, kind=kind, mandatory=mandatory)
    for child in elem:
        if child.tag in GROUP_TAGS or child.tag == "feature":
            node.children.append(parse_xml(child))
    return node


def canonical(s: str) -> str:
    return re.sub(r"[\s\-_]+", "", s).lower()


def normalize(node: Node) -> None:
    if node.kind in GROUP_TAGS and node.children:
        key = canonical(node.name)
        for i, c in enumerate(node.children):
            if c.kind == "feature" and not c.children and canonical(c.name) == key:
                node.name = c.name
                del node.children[i]
                break
    for c in node.children:
        normalize(c)


def simplify_singletons(node: Node) -> None:
    """An or/alt group with exactly one child is equivalent to a
    mandatory child. Convert to `and` with the child marked mandatory."""
    for c in node.children:
        simplify_singletons(c)
    if node.kind in ("or", "alt") and len(node.children) == 1:
        node.kind = "and"
        node.children[0].mandatory = True


def load_constraints(root_elem) -> list:
    cons = root_elem.find("constraints")
    if cons is None:
        return []
    return [r[0] for r in cons.findall("rule")]


# ---------- UVL export ----------

UVL_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def uvl_id(name: str) -> str:
    return name if UVL_ID_RE.fullmatch(name) else f'"{name}"'


def write_uvl(root: Node, constraints: list, path: Path) -> None:
    lines: list[str] = []
    lines.append("// Chess engine product line — generated from FeatureIDE XML")
    lines.append("features")
    _emit_uvl_feature(root, 1, lines)

    if constraints:
        lines.append("")
        lines.append("constraints")
        for rule_ast in constraints:
            lines.append("\t" + uvl_rule(rule_ast))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _emit_uvl_feature(node: Node, depth: int, lines: list[str]) -> None:
    indent = "\t" * depth
    lines.append(f"{indent}{uvl_id(node.name)}")
    if node.children:
        _emit_uvl_group_block(node, depth + 1, lines)


def _emit_uvl_group_block(node: Node, depth: int, lines: list[str]) -> None:
    indent = "\t" * depth
    if node.kind in ("and", "feature"):
        mand = [c for c in node.children if c.mandatory]
        opt = [c for c in node.children if not c.mandatory]
        if mand:
            lines.append(f"{indent}mandatory")
            for c in mand:
                _emit_uvl_feature(c, depth + 1, lines)
        if opt:
            lines.append(f"{indent}optional")
            for c in opt:
                _emit_uvl_feature(c, depth + 1, lines)
    elif node.kind == "alt":
        lines.append(f"{indent}alternative")
        for c in node.children:
            _emit_uvl_feature(c, depth + 1, lines)
    elif node.kind == "or":
        lines.append(f"{indent}or")
        for c in node.children:
            _emit_uvl_feature(c, depth + 1, lines)


def uvl_rule(node) -> str:
    t = node.tag
    if t == "var":
        return uvl_id(node.text or "")
    if t == "not":
        return f"!({uvl_rule(node[0])})"
    if t == "imp":
        return f"{uvl_rule(node[0])} => {uvl_rule(node[1])}"
    if t == "and":
        return "(" + " & ".join(uvl_rule(c) for c in node) + ")"
    if t == "or":
        return "(" + " | ".join(uvl_rule(c) for c in node) + ")"
    if t == "eq":
        return f"{uvl_rule(node[0])} <=> {uvl_rule(node[1])}"
    return t


# ---------- FAMILIAR (FML) export ----------

def fml_id(name: str) -> str:
    """FAMILIAR identifiers: alnum + underscore. Replace other chars."""
    s = re.sub(r"[\s\-]+", "_", name)
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    if s and s[0].isdigit():
        s = "_" + s
    return s


def write_fml(root: Node, constraints: list, path: Path) -> None:
    header_children = _fml_children_tokens(root)
    lines: list[str] = []
    lines.append(f"FM ( {fml_id(root.name)}: {header_children} ;")
    _emit_fml(root, lines, indent=" ")
    lines.append(")")

    if constraints:
        lines.append("")
        lines.append("%% Cross-tree constraints")
        for rule_ast in constraints:
            lines.append(fml_rule(rule_ast) + ";")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _fml_children_tokens(node: Node) -> str:
    if not node.children:
        return ""
    if node.kind == "alt":
        return "(" + "|".join(fml_id(c.name) for c in node.children) + ")"
    if node.kind == "or":
        return "(" + "|".join(fml_id(c.name) for c in node.children) + ")+"
    # and/feature: sequence of tokens, bare for mandatory, [brackets] for optional
    toks = []
    for c in node.children:
        ident = fml_id(c.name)
        toks.append(ident if c.mandatory else f"[{ident}]")
    return " ".join(toks)


def _emit_fml(node: Node, lines: list[str], indent: str = "") -> None:
    for c in node.children:
        if c.children:
            lines.append(f"{indent}{fml_id(c.name)}: {_fml_children_tokens(c)} ;")
            _emit_fml(c, lines, indent)


def fml_rule(node) -> str:
    t = node.tag
    if t == "var":
        return fml_id(node.text or "")
    if t == "not":
        return f"!{fml_rule(node[0])}"
    if t == "imp":
        return f"{fml_rule(node[0])} -> {fml_rule(node[1])}"
    if t == "and":
        return "(" + " & ".join(fml_rule(c) for c in node) + ")"
    if t == "or":
        return "(" + " | ".join(fml_rule(c) for c in node) + ")"
    if t == "eq":
        return f"{fml_rule(node[0])} <-> {fml_rule(node[1])}"
    return t


def main() -> None:
    tree_doc = ET.parse(XML_PATH)
    root_elem = tree_doc.getroot()
    struct = root_elem.find("struct")
    assert struct is not None and len(struct) == 1
    root = parse_xml(struct[0])
    normalize(root)
    simplify_singletons(root)
    constraints = load_constraints(root_elem)
    write_uvl(root, constraints, UVL_PATH)
    write_fml(root, constraints, FML_PATH)


if __name__ == "__main__":
    main()
