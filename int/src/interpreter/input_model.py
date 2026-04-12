"""
This module defines the data models for representing SOL-XML programs in memory,
using Pydantic and pydantic-xml.

IPP: You should not need to modify this file. If you find it necessary to modify it,
     consult your intentions on the project forum first.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
"""

from typing import Any

from pydantic import model_validator
from pydantic_xml import BaseXmlModel, attr, element

# --- Leaf nodes ---


class OrderedElementXmlModel(BaseXmlModel):
    """Represents any XML element with an 'order' attribute."""

    order: int = attr(name="order")


class Var(BaseXmlModel, tag="var"):
    """<var name="..."/>"""

    name: str = attr(name="name")


class Literal(BaseXmlModel, tag="literal"):
    """<literal class="Integer|String|Nil|True|False|class" value="..."/>"""

    class_id: str = attr(name="class")
    value: str = attr(name="value")


class Parameter(OrderedElementXmlModel, tag="parameter"):
    """<parameter name="..." order="..."/>"""

    name: str = attr(name="name")


class Arg(OrderedElementXmlModel, tag="arg"):
    """<arg order="..."><expr>...</expr></arg>"""

    expr: Expr = element(tag="expr")


# --- Helpers ---


def sort_by_order[T: OrderedElementXmlModel](items: list[T]) -> list[T]:
    """Sorts list of elements that carry an `order` attribute."""
    return sorted(items, key=lambda x: x.order)


# --- Expression and statements ---


class Expr(BaseXmlModel, tag="expr"):
    """
    <expr> contains exactly one child, one of:
      - <literal .../>
      - <var .../>
      - <block ...>...</block>
      - <send ...>...</send>

    Implemented as four optional fields with a validator enforcing "exactly one".
    This avoids relying on union-tag discrimination.
    """

    literal: Literal | None = element(tag="literal", default=None)
    var: Var | None = element(tag="var", default=None)
    block: Block | None = element(tag="block", default=None)
    send: Send | None = element(tag="send", default=None)

    @model_validator(mode="after")
    def _exactly_one_child(self) -> Expr:
        present = sum(x is not None for x in (self.literal, self.var, self.block, self.send))
        if present != 1:
            raise ValueError("<expr> must contain exactly one of: literal|var|block|send")
        return self


class Send(BaseXmlModel, tag="send", search_mode="unordered"):
    """
    <send selector="...">
      <expr>...</expr>              # receiver expression (required)
      <arg order="1"><expr>...</expr></arg>  # optional, ordered
      ...
    </send>
    """

    selector: str = attr(name="selector")
    receiver: Expr = element(tag="expr")
    args: list[Arg] = element(tag="arg", default_factory=list)

    def model_post_init(self, context: Any) -> None:
        """
        After the model is initialized, ensure the args are sorted
        according to their declared order.
        """
        self.args = sort_by_order(self.args)


class Assign(OrderedElementXmlModel, tag="assign", search_mode="unordered"):
    """
    <assign order="...">
      <var name="..."/>
      <expr>...</expr>
    </assign>
    """

    target: Var = element(tag="var")
    expr: Expr = element(tag="expr")


class Block(BaseXmlModel, tag="block", search_mode="unordered"):
    """
    <block arity="...">
      <parameter name="..." order="..."/>
      ...
      <assign order="...">...</assign>
      ...
    </block>
    """

    arity: int = attr(name="arity")
    parameters: list[Parameter] = element(tag="parameter", default_factory=list)
    assigns: list[Assign] = element(tag="assign", default_factory=list)

    def model_post_init(self, context: Any) -> None:
        """
        After the model is initialized, ensure the parameters and assignments
        are sorted according to their declared order.
        """
        self.parameters = sort_by_order(self.parameters)
        self.assigns = sort_by_order(self.assigns)


# --- Program structure ---


class Method(BaseXmlModel, tag="method"):
    """
    <method selector="...">
      <block arity="...">...</block>
    </method>
    """

    selector: str = attr(name="selector")
    block: Block = element(tag="block")


class ClassDef(BaseXmlModel, tag="class"):
    """
    <class name="..." parent="...">
      <method selector="...">...</method>
      ...
    </class>
    """

    name: str = attr(name="name")
    parent: str = attr(name="parent")
    methods: list[Method] = element(tag="method", default_factory=list)


class Program(BaseXmlModel, tag="program"):
    """
    <program language="..." description="...">
      <class ...>...</class>
      ...
    </program>
    """

    language: str = attr(name="language")
    description: str | None = attr(name="description", default=None)
    classes: list[ClassDef] = element(tag="class", default_factory=list)


# Resolve forward references
Expr.model_rebuild()
Arg.model_rebuild()
Send.model_rebuild()
Assign.model_rebuild()
Block.model_rebuild()
Method.model_rebuild()
ClassDef.model_rebuild()
Program.model_rebuild()
