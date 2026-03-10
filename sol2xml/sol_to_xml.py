#!/usr/bin/env python3
import os
import sys
import re
from lark import Lark, Transformer, LarkError
from lxml import etree
from lxml.etree import tostring, indent

grammar = r'''
COMMENT: /"([^"\\]|\\.)*"/

STR: /'([^'\\]|\\.)*'/
%import common.SIGNED_INT
//%import common.CNAME -> ID
ID: /[a-z_][A-Za-z0-9_]*/
CID: /[A-Z][A-Za-z0-9_]*/

?program: class_def*

class_def: "class" CID ":" CID "{" method* "}"

method: selector block

selector: ID ":" (ID ":")*    -> selector
        | ID                  -> selector_nopar

block: "[" block_body "]"

?block_body: block_par "|" block_stat    -> param_block
           | block_stat                  -> stat_block

block_par: (":" ID)*

block_stat: assignment*

assignment: ID ":=" expr "."

?expr: expr_base expr_tail?
?expr_tail: ID         -> simple_tail
           | expr_sel

expr_sel: (ID ":" expr_base)+

?expr_base: SIGNED_INT  -> int
          | STR         -> str
          | ID          -> id
          | CID         -> cid
          | block       -> block_expr
          | "(" expr ")"
          
%ignore COMMENT
%ignore /\s+/
'''


# Utility to escape the handful of problematic XML characters
def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class SolTransformer(Transformer):
    """
    Builds a simple AST that includes:
      - 'comment' nodes: capturing the entire comment string (double quotes included).
      - 'class_def' nodes with name, parent, and a list of methods
      - 'method' nodes with a 'selector' and a 'block'
      - 'block' with parameters (list) and statements (list)
      - 'assign' statements with var=, expr=
      - expressions with type= ("int","str","id","msg_send","block_expr","class_lit") etc.
    """

    def __init__(self):
        super().__init__()

    def program(self, children):
        # 'children' can be comment or class_def nodes
        # We'll separate them into comments and classes
        classes = []
        for ch in children:
            if isinstance(ch, dict) and ch.get("kind") == "class_def":
                classes.append(ch)
        return {
            "type": "program",
            "classes": classes
        }

    def class_def(self, kids):
        # kids: [CID, CID, method*, possibly 0 or more methods]
        cname = kids[0]  # str name of the class
        parent = kids[1]  # str name of parent
        methods = kids[2:]  # list of method dicts
        return {
            "kind": "class_def",
            "cname": cname,
            "parent": parent,
            "methods": methods
        }

    def method(self, kids):
        # kids[0] is a selector dict, kids[1] is a block
        return {
            "kind": "method",
            "selector": kids[0],
            "block": kids[1]
        }

    def selector_nopar(self, kids):
        # single ID
        return {
            "type": "selector",
            "base": kids[0],  # the selector name
            "params": [],
            "full": kids[0]  # e.g. "run"
        }

    def selector(self, kids):
        # first is base ID, rest are ID from "ID:" pattern
        base = kids[0]
        params = kids[1:]
        # e.g. base='compute', params=['and','and']
        # full = 'compute:and:and:'
        colon_tail = ':'.join(params)
        if colon_tail:
            full_selector = f"{base}:{colon_tail}:"
        else:
            full_selector = f"{base}:"
        return {
            "type": "selector",
            "base": base,
            "params": params,
            "full": full_selector
        }

    def block(self, kids):
        # single child: block_body
        return kids[0]

    def param_block(self, kids):
        # kids[0] is a list of param IDs, kids[1] is the statement list
        return {
            "type": "block",
            "params": kids[0],
            "stats": kids[1]
        }

    def stat_block(self, kids):
        # only statements
        return {
            "type": "block",
            "params": [],
            "stats": kids
        }

    def block_par(self, kids):
        # each child is an ID
        return kids

    def assignment(self, kids):
        # kids: [var ID, expr dict]
        return {
            "type": "assign",
            "var": kids[0],
            "expr": kids[1]
        }

    def expr(self, kids):
        if len(kids) == 1:
            return kids[0]  # single subexpression
        else:
            # msg_send with a 'tail'
            return {
                "type": "msg_send",
                "receiver": kids[0],
                "tail": kids[1]
            }

    def simple_tail(self, kids):
        # e.g. "asString" with no arguments
        return {
            "type": "simple_tail",
            "name": kids[0]
        }

    def expr_sel(self, kids):
        # pairs of ID and expr_base
        # result: "sel": [(id, expr), (id, expr), ...]
        it = iter(kids)
        pairs = []
        for token in it:
            msg = token
            arg = next(it)
            pairs.append((msg, arg))
        return {"type": "sel", "pairs": pairs}

    def int(self, kids):
        val_str = str(kids[0])
        return {
            "type": "literal",
            "class": "Integer",
            "value": val_str
        }

    def str(self, kids):
        # kids[0] is the token, e.g. 'some string'
        raw = kids[0]
        # remove leading/trailing single quotes
        s_val = raw[1:-1]
        # unescape the usual combos if needed - should not be done (see specification of XML)
        # s_val = s_val.replace("\\n", "\n").replace("\\\\", "\\").replace("\\'", "'")
        return {
            "type": "literal",
            "class": "String",
            "value": s_val
        }

    def id(self, kids):
        # could be "nil" or "true"/"false", or a normal var
        name = kids[0]
        if name == "nil":
            return {
                "type": "literal",
                "class": "Nil",
                "value": "nil"
            }
        elif name == "true":
            return {
                "type": "literal",
                "class": "True",
                "value": "true"
            }
        elif name == "false":
            return {
                "type": "literal",
                "class": "False",
                "value": "false"
            }
        else:
            # normal variable reference
            return {
                "type": "var",
                "name": name
            }

    def cid(self, kids):
        # Uppercase IDs are class references => we treat them as a literal with class="class"
        c_name = kids[0]
        return {
            "type": "literal",
            "class": "class",
            "value": c_name
        }

    def block_expr(self, kids):
        # we have a nested block inside an expression
        # kids[0] is a block dict: {type:"block", params:..., stats:...}
        return kids[0]


#
# Build the XML according to the rules:
#

def build_xml_program(ast, first_comment):
    """
    ast: { "type":"program", "classes":[...] }
    first_comment: optional string (the first double-quoted comment encountered),
                   or None if none found.
    Returns an Element <program> with nested structure.
    """
    # Root element
    root = etree.Element("program", {"language": "SOL26"})
    if first_comment:
        root.set("description", first_comment.replace("\n", "\x0A"))

    # For each class in ast["classes"], build <class> subelements

    if "classes" not in ast:
        ast["classes"] = [ast]

    for cdef in ast["classes"]:
        cls_elem = etree.SubElement(root, "class")
        cls_elem.set("name", cdef["cname"])
        cls_elem.set("parent", cdef["parent"])
        # Each method => <method selector="..."><block ...></method>
        for m in cdef["methods"]:
            m_elem = etree.SubElement(cls_elem, "method")
            m_elem.set("selector", m["selector"]["full"])
            # The method body is a block:
            block_ast = m["block"]
            block_elem = build_xml_block(block_ast)
            m_elem.append(block_elem)

    return root


def build_xml_block(block_ast):
    """
    block_ast: { "type":"block", "params": [...], "stats": [...]}
    Return an Element <block arity="N"> with <parameter> and <assign> children.
    """
    # The block has a certain number of params => "arity"
    params = block_ast["params"]
    stats = block_ast["stats"]
    block_elem = etree.Element("block")
    block_elem.set("arity", str(len(params)))

    # Build <parameter> elements
    for i, p in enumerate(params, start=1):
        param_elem = etree.SubElement(block_elem, "parameter")
        param_elem.set("order", str(i))
        param_elem.set("name", p)

    # Build <assign> elements for each statement
    # The specification requires order=..., from 1 up to ...
    for j, stmt in enumerate(stats.children, start=1):
        # stmt: { "type":"assign", "var":..., "expr":... }
        assign_elem = etree.SubElement(block_elem, "assign")
        assign_elem.set("order", str(j))

        var_elem = etree.SubElement(assign_elem, "var")
        var_elem.set("name", stmt["var"])

        expr_elem = etree.SubElement(assign_elem, "expr")
        expr_child = build_xml_expr(stmt["expr"])
        expr_elem.append(expr_child)

    return block_elem


def build_xml_expr(expr_ast):
    """
    expr_ast is one of:
      { "type":"literal", "class":"Integer", "value":"10" }
      { "type":"var", "name":"x" }
      { "type":"block", "params":[...], "stats":[...] }  (nested block)
      { "type":"msg_send", "receiver":..., "tail":... }  (a send)
      etc.
    Return an Element that is the single child of <expr>.
    """
    etype = expr_ast["type"]
    if etype == "literal":
        # <literal class="..." value="..."/>
        lit_elem = etree.Element("literal")
        lit_elem.set("class", expr_ast["class"])
        # Escape the value for XML - should not be done (otherwise escaping escaped character)
        # val = xml_escape(expr_ast["value"])
        lit_elem.set("value", expr_ast["value"])
        return lit_elem
    elif etype == "var":
        # <var name="..."/>
        v_elem = etree.Element("var")
        v_elem.set("name", expr_ast["name"])
        return v_elem
    elif etype == "block":
        # nested <block ...>
        return build_xml_block(expr_ast)
    elif etype == "msg_send":
        # <send selector="..."><expr>...</expr><arg><expr>...</expr></arg>...</send>
        # The tail could be a "simple_tail" or a "sel" with pairs
        send_elem = etree.Element("send")
        if expr_ast["tail"]["type"] == "simple_tail":
            # simple message: e.g. "obj asString"
            sel_name = expr_ast["tail"]["name"]
            send_elem.set("selector", sel_name)
            # The receiver
            recv_expr_elem = etree.SubElement(send_elem, "expr")
            recv_sub = build_xml_expr(expr_ast["receiver"])
            recv_expr_elem.append(recv_sub)
            # no args => done
        else:
            # multi-arg message => "sel":{"type":"sel","pairs":[(msg, expr),(msg, expr),...]}
            pairs = expr_ast["tail"]["pairs"]
            # Build the full selector string => e.g. "compute:and:and:"
            msgs = [m for (m, _) in pairs]
            # Join them with ":" and add trailing ":"
            combined_selector = ""
            # If there's 1 pair, it might be "compute" + trailing colon
            # If multiple pairs, etc.
            combined_selector = "".join(m + ":" for m in msgs)

            send_elem.set("selector", combined_selector)

            # The receiver:
            recv_expr_elem = etree.SubElement(send_elem, "expr")
            recv_sub = build_xml_expr(expr_ast["receiver"])
            recv_expr_elem.append(recv_sub)

            # The arguments:
            for idx, (m, arg_expr) in enumerate(pairs, start=1):
                arg_elem = etree.SubElement(send_elem, "arg")
                arg_elem.set("order", str(idx))
                arg_expr_elem = etree.SubElement(arg_elem, "expr")
                arg_expr_child = build_xml_expr(arg_expr)
                arg_expr_elem.append(arg_expr_child)

        return send_elem
    else:
        # Something else, fallback
        lit_elem = etree.Element("literal")
        lit_elem.set("class", "Unknown")
        lit_elem.set("value", "???")
        return lit_elem


def find_first_comment(text):
    match = re.search(r"\"((.|\n)*?)\"", text)
    if match is None: return None
    return match.group(1)


script_dir = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(script_dir, 'parser_output_schema.xsd')) as xsd_f:
        sol_schema = etree.XMLSchema(file=xsd_f)
except IOError:
    print('Schema not found, will not validate', file=sys.stderr)
    sol_schema = None


def validate(xml_string: str) -> str | None:
    if sol_schema is None:
        return None
    try:
        xml_doc = etree.fromstring(xml_string.encode('utf-8'))
        sol_schema.assertValid(xml_doc)
        return None
    except (etree.DocumentInvalid, etree.XMLSyntaxError) as e:
        return str(e)


def convert_to_xml(sol_program: str) -> str:
    parser = Lark(grammar, start="program", parser="lalr")

    transformer = SolTransformer()
    tree = parser.parse(sol_program)
    ast = transformer.transform(tree)

    # Build the XML
    root = build_xml_program(ast, find_first_comment(sol_program))
    # Output the XML with the required prolog
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    indent(root, level=0)
    return xml_declaration + tostring(root, encoding="unicode")


def main():
    source_file = None
    if len(sys.argv) > 1:
        source_file = sys.argv[-1]

    if source_file and source_file != "-":
        with open(source_file, "r", encoding="utf-8") as f:
            contents = f.read()
    else:
        contents = sys.stdin.read()

    try:
        xml_str = convert_to_xml(contents)
        print(xml_str)

        validation_result = validate(xml_str)
        if validation_result is not None:
            print('Generated XML does not conform to the schema:', file=sys.stderr)
            print(validation_result, file=sys.stderr)
            exit(2)
    except LarkError as e:
        print("Invalid input:", file=sys.stderr)
        print(str(e), file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
