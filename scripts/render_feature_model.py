"""Render a FeatureIDE XML feature model to a self-contained SVG.

Layout: left-to-right (root on the left, children stacked to the right).
Groups with many children use a 2-column grid to keep the tree compact.

Also normalizes duplicate group/feature naming: when a group node is
named the same as a direct leaf child (modulo case/whitespace), the two
are collapsed — e.g. "TimeManagement" group with "Time Management"
feature child becomes a single "Time Management" node with the group's
alt/or semantics.
"""
from __future__ import annotations

import html
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

XML_PATH = Path("outputs/feature_model.featureide.xml")
SVG_PATH = Path("outputs/feature_model.svg")

GROUP_TAGS = {"and", "or", "alt"}

NODE_W = 160
NODE_H = 26
H_GAP = 30        # gap between grid columns
V_GAP = 10        # vertical gap between siblings
LEVEL_GAP = 42    # horizontal gap between tree levels
COLUMNIZE_THRESHOLD = 5


@dataclass
class Node:
    name: str
    kind: str
    mandatory: bool = False
    children: list["Node"] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0  # subtree width
    h: float = 0.0  # subtree height


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
    """Collapse `group "X" / feature "X"` duplicates into one display node."""
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
    """An or/alt group with exactly one child is semantically equivalent to
    a mandatory child ("at least one of {X}" / "exactly one of {X}" both
    force X). Convert such groups to `and` with the child marked mandatory
    so the visualization shows a clean mandatory edge instead of a lone
    triangle."""
    for c in node.children:
        simplify_singletons(c)
    if node.kind in ("or", "alt") and len(node.children) == 1:
        node.kind = "and"
        node.children[0].mandatory = True


def load_constraints(root_elem) -> list[str]:
    out = []
    cons = root_elem.find("constraints")
    if cons is None:
        return out
    for rule in cons.findall("rule"):
        out.append(render_rule(rule[0]))
    return out


def render_rule(node) -> str:
    t = node.tag
    if t == "var":
        return node.text or ""
    if t == "not":
        return f"¬({render_rule(node[0])})"
    if t == "imp":
        return f"{render_rule(node[0])} → {render_rule(node[1])}"
    if t == "and":
        return " ∧ ".join(render_rule(c) for c in node)
    if t == "or":
        return " ∨ ".join(render_rule(c) for c in node)
    if t == "eq":
        return f"{render_rule(node[0])} ↔ {render_rule(node[1])}"
    return t


# ---------- Layout (left-to-right) ----------

def uses_grid(node: Node) -> bool:
    return node.kind in {"alt", "or"} and len(node.children) > COLUMNIZE_THRESHOLD


def _grid_metrics(node: Node, cols: int = 2) -> tuple[list[float], list[float]]:
    rows = math.ceil(len(node.children) / cols)
    row_h = [0.0] * rows
    col_w = [0.0] * cols
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= len(node.children):
                continue
            row_h[r] = max(row_h[r], node.children[i].h)
            col_w[c] = max(col_w[c], node.children[i].w)
    return row_h, col_w


def measure(node: Node) -> None:
    if not node.children:
        node.w = NODE_W
        node.h = NODE_H
        return
    for c in node.children:
        measure(c)

    if uses_grid(node):
        cols = 2
        row_h, col_w = _grid_metrics(node, cols)
        body_w = sum(col_w) + H_GAP * (cols - 1)
        body_h = sum(row_h) + V_GAP * (len(row_h) - 1)
    else:
        body_w = max(c.w for c in node.children)
        body_h = sum(c.h for c in node.children) + V_GAP * (len(node.children) - 1)

    node.w = NODE_W + LEVEL_GAP + body_w
    node.h = max(NODE_H, body_h)


def place(node: Node, x_left: float, y_top: float) -> None:
    if not node.children:
        node.x = x_left + NODE_W / 2
        node.y = y_top + (node.h - NODE_H) / 2
        return

    child_x_left = x_left + NODE_W + LEVEL_GAP

    if uses_grid(node):
        cols = 2
        row_h, col_w = _grid_metrics(node, cols)
        body_h = sum(row_h) + V_GAP * (len(row_h) - 1)
        row_y = y_top + (node.h - body_h) / 2
        col_x = [child_x_left]
        for c in range(1, cols):
            col_x.append(col_x[-1] + col_w[c - 1] + H_GAP)
        for r in range(len(row_h)):
            for c in range(cols):
                i = r * cols + c
                if i >= len(node.children):
                    continue
                child = node.children[i]
                cy = row_y + (row_h[r] - child.h) / 2
                cx = col_x[c] + (col_w[c] - child.w) / 2
                place(child, cx, cy)
            row_y += row_h[r] + V_GAP
    else:
        body_h = sum(c.h for c in node.children) + V_GAP * (len(node.children) - 1)
        cy = y_top + (node.h - body_h) / 2
        for c in node.children:
            place(c, child_x_left, cy)
            cy += c.h + V_GAP

    # Center node vertically among children's centers
    centers = [c.y + NODE_H / 2 for c in node.children]
    node.x = x_left + NODE_W / 2
    node.y = (min(centers) + max(centers)) / 2 - NODE_H / 2


# ---------- SVG rendering ----------

def wrap_label(name: str, max_chars: int = 22) -> list[str]:
    if len(name) <= max_chars:
        return [name]
    words = name.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:2]


def svg_for_node(node: Node) -> str:
    parts = []
    lines = wrap_label(node.name)
    fill = "#e8f1fb" if node.kind in GROUP_TAGS else "#ffffff"
    stroke = "#1f4e79"
    parts.append(
        f'<rect x="{node.x - NODE_W/2:.1f}" y="{node.y:.1f}" '
        f'width="{NODE_W}" height="{NODE_H}" rx="5" ry="5" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
    )
    if len(lines) == 1:
        ty = node.y + NODE_H / 2 + 4
        parts.append(
            f'<text x="{node.x:.1f}" y="{ty:.1f}" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="11" text-anchor="middle" fill="#111">{html.escape(lines[0])}</text>'
        )
    else:
        for i, ln in enumerate(lines):
            ty = node.y + 11 + i * 11
            parts.append(
                f'<text x="{node.x:.1f}" y="{ty:.1f}" font-family="Helvetica, Arial, sans-serif" '
                f'font-size="10" text-anchor="middle" fill="#111">{html.escape(ln)}</text>'
            )
    return "\n".join(parts)


def svg_for_edge(parent: Node, child: Node) -> str:
    x1 = parent.x + NODE_W / 2
    y1 = parent.y + NODE_H / 2
    x2 = child.x - NODE_W / 2
    y2 = child.y + NODE_H / 2
    mx = (x1 + x2) / 2
    path = f"M {x1:.1f},{y1:.1f} L {mx:.1f},{y1:.1f} L {mx:.1f},{y2:.1f} L {x2:.1f},{y2:.1f}"
    line = f'<path d="{path}" fill="none" stroke="#6b7a8f" stroke-width="1.1"/>'
    marker = ""
    if parent.kind == "and":
        r = 4.5
        cx = x2 - r - 1
        cy = y2
        fill = "#1f4e79" if child.mandatory else "#ffffff"
        marker = (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" '
            f'fill="{fill}" stroke="#1f4e79" stroke-width="1.1"/>'
        )
    return line + ("\n" + marker if marker else "")


def svg_for_group_arc(parent: Node) -> str:
    if parent.kind not in {"alt", "or"} or not parent.children:
        return ""
    apex_x = parent.x + NODE_W / 2
    apex_y = parent.y + NODE_H / 2
    # In LR, triangle points rightward; spans near column of children.
    if uses_grid(parent):
        near_col = [parent.children[i] for i in range(0, len(parent.children), 2)]
    else:
        near_col = parent.children
    ys = [c.y + NODE_H / 2 for c in near_col]
    xs = [c.x - NODE_W / 2 for c in near_col]
    x_near = min(xs)
    y_top = min(ys)
    y_bot = max(ys)
    fill = "#1f4e79" if parent.kind == "or" else "#ffffff"
    pts = f"{apex_x:.1f},{apex_y:.1f} {x_near:.1f},{y_top:.1f} {x_near:.1f},{y_bot:.1f}"
    return (
        f'<polygon points="{pts}" fill="{fill}" fill-opacity="0.35" '
        f'stroke="#1f4e79" stroke-width="1.0"/>'
    )


def walk_edges(node: Node, edges: list[str], arcs: list[str]) -> None:
    if node.kind in {"alt", "or"}:
        arcs.append(svg_for_group_arc(node))
    for c in node.children:
        edges.append(svg_for_edge(node, c))
        walk_edges(c, edges, arcs)


def walk_nodes(node: Node, out: list[str]) -> None:
    out.append(svg_for_node(node))
    for c in node.children:
        walk_nodes(c, out)


def extent(n: Node, acc: dict) -> None:
    acc["x0"] = min(acc["x0"], n.x - NODE_W / 2)
    acc["x1"] = max(acc["x1"], n.x + NODE_W / 2)
    acc["y0"] = min(acc["y0"], n.y)
    acc["y1"] = max(acc["y1"], n.y + NODE_H)
    for c in n.children:
        extent(c, acc)


def render(xml_path: Path, svg_path: Path) -> None:
    tree_doc = ET.parse(xml_path)
    root_elem = tree_doc.getroot()
    struct = root_elem.find("struct")
    assert struct is not None and len(struct) == 1
    root = parse_xml(struct[0])
    normalize(root)
    simplify_singletons(root)
    measure(root)
    place(root, x_left=20, y_top=60)

    constraints = load_constraints(root_elem)

    acc = {"x0": 1e9, "x1": -1e9, "y0": 1e9, "y1": -1e9}
    extent(root, acc)
    dx = 20 - acc["x0"]
    dy = 60 - acc["y0"]

    def shift(n: Node) -> None:
        n.x += dx
        n.y += dy
        for c in n.children:
            shift(c)

    shift(root)
    # Recompute extent after shift
    acc = {"x0": 1e9, "x1": -1e9, "y0": 1e9, "y1": -1e9}
    extent(root, acc)
    tree_w = acc["x1"] + 40
    tree_h = acc["y1"] + 80

    panel_w = 520
    panel_x = tree_w + 20
    panel_line_h = 14
    panel_h = 60 + len(constraints) * panel_line_h

    W = tree_w + panel_w + 40
    H = max(tree_h, panel_h) + 40

    nodes_svg: list[str] = []
    edges_svg: list[str] = []
    arcs_svg: list[str] = []
    walk_edges(root, edges_svg, arcs_svg)
    walk_nodes(root, nodes_svg)

    # Legend near bottom-left
    legend_x = 20
    legend_y = tree_h + 5
    legend = f'''
<g transform="translate({legend_x},{legend_y})">
  <text x="0" y="12" font-family="Helvetica, Arial, sans-serif" font-size="12" font-weight="bold" fill="#111">Legend</text>
  <circle cx="10" cy="30" r="4.5" fill="#1f4e79" stroke="#1f4e79"/>
  <text x="22" y="34" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#111">mandatory</text>
  <circle cx="110" cy="30" r="4.5" fill="#ffffff" stroke="#1f4e79"/>
  <text x="122" y="34" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#111">optional</text>
  <polygon points="200,22 214,26 200,30" fill="#1f4e79" fill-opacity="0.35" stroke="#1f4e79"/>
  <text x="222" y="34" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#111">or (≥1)</text>
  <polygon points="300,22 314,26 300,30" fill="#ffffff" stroke="#1f4e79"/>
  <text x="322" y="34" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#111">alt (XOR)</text>
</g>
'''

    c_lines = [
        f'<text x="{panel_x}" y="30" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="13" font-weight="bold" fill="#111">'
        f'Cross-tree constraints ({len(constraints)})</text>'
    ]
    for i, c in enumerate(constraints):
        cy = 50 + i * panel_line_h
        c_lines.append(
            f'<text x="{panel_x}" y="{cy}" font-family="Menlo, monospace" '
            f'font-size="10.5" fill="#111">{html.escape(c)}</text>'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">
<style>text {{ dominant-baseline: alphabetic; }}</style>
<rect width="100%" height="100%" fill="#fafbfc"/>
<text x="20" y="28" font-family="Helvetica, Arial, sans-serif" font-size="14" font-weight="bold" fill="#111">Chess Engine Product Line — Feature Model (left-to-right)</text>
{"".join(arcs_svg)}
{"".join(edges_svg)}
{"".join(nodes_svg)}
{legend}
{"".join(c_lines)}
</svg>
'''
    svg_path.write_text(svg, encoding="utf-8")
    print(f"wrote {svg_path} ({W:.0f}x{H:.0f})")


if __name__ == "__main__":
    render(XML_PATH, SVG_PATH)
