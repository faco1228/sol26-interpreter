"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Samuel Fačka <xfackas00>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TextIO

from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, ClassDef, Expr, Literal, Program, Send

logger = logging.getLogger(__name__)

# =============================================================================
# RUNTIME OBJECT MODEL
# =============================================================================

# type alias for builtin method callables
type BuiltinFn = Any


class SolObject:
    """runtime object in the SOL26 interpreter"""

    def __init__(self) -> None:
        """init with no class and empty attributes"""
        self.sol_class: SolClass | None = None
        self.attributes: dict[str, Any] = {}


class SolClass:
    """runtime class descriptor holding method tables and parent class"""

    def __init__(self, name: str) -> None:
        """init a class with the given name and empty method tables"""
        self.name = name
        self.parent: SolClass | None = None
        self.methods: dict[str, BuiltinFn] = {}
        self.class_methods: dict[str, BuiltinFn] = {}


class Environment:
    """lexical variable scope with optional parent for closure chains"""

    def __init__(self, parent: Environment | None = None) -> None:
        """init an empty scope with an optional parent"""
        self.variables: dict[str, SolObject] = {}
        self.parent = parent

    def get(self, name: str) -> SolObject:
        """return the value of a variable, searching parent scopes"""
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise InterpreterError(ErrorCode.SEM_UNDEF, f"Variable '{name}' was not defined")

    def set(self, name: str, value: SolObject) -> None:
        """set a variable, updating an existing binding in the nearest scope"""
        env: Environment | None = self
        while env is not None:
            if name in env.variables:
                env.variables[name] = value
                return
            env = env.parent
        self.variables[name] = value


class SuperWrapper:
    """wraps a receiver so that method lookup starts in the parent of start_cls"""

    def __init__(self, obj: SolObject, start_cls: SolClass) -> None:
        """init with the actual object and the class to start lookup from"""
        self.obj = obj
        self.start_cls = start_cls


# =============================================================================
# MODULE-LEVEL BUILTIN IMPLEMENTATIONS
# =============================================================================
# each function receives (receiver, args, runtime) and returns a SolObject
# keeping them at module level avoids nested-def complexity

# ---- class methods ----------------------------------------------------------


def builtin_new(reciever: SolObject, _args: list[SolObject], _runtime: Runtime) -> SolObject:
    assert reciever.sol_class is not None
    obj = SolObject()
    obj.sol_class = reciever.sol_class
    if reciever.sol_class.name == "Integer":
        obj.attributes["__value__"] = 0
    if reciever.sol_class.name == "String":
        obj.attributes["__value__"] = ""
    return obj


def builtin_from(reciever: SolObject, args: list[SolObject], _runtime: Runtime) -> SolObject:
    assert reciever.sol_class is not None
    arg = args[0]
    cls_name = reciever.sol_class.name
    if cls_name == "Integer" and not isinstance(arg.attributes.get("__value__"), int):
        raise InterpreterError(ErrorCode.INT_INVALID_ARG, "from: argument must be an Integer")
    if cls_name == "String" and not isinstance(arg.attributes.get("__value__"), str):
        raise InterpreterError(ErrorCode.INT_INVALID_ARG, "from: argument must be a String")
    obj = SolObject()
    obj.sol_class = reciever.sol_class
    obj.attributes = dict(arg.attributes)
    return obj


def builtin_str_read(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    line = runtime.input_io.readline()
    if line == "":
        return runtime.nil_frame
    return runtime.make_str(line.rstrip("\n"))


def builtin_nil_new(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.nil_frame


def builtin_true_new(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame


def builtin_false_new(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.false_frame


def builtin_block_new(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    obj = SolObject()
    obj.sol_class = runtime.block_class
    obj.attributes["__block__"] = Block(arity=0)
    obj.attributes["__env__"] = Environment()
    obj.attributes["__self__"] = runtime.nil_frame
    obj.attributes["__current_cls__"] = None
    return obj


# ---- object instance methods ------------------------------------------------


def is_instance(obj: SolObject, cls_name: str) -> bool:
    """return True if obj is an instance of cls_name or any of its subclasses"""
    current = obj.sol_class
    while current is not None:
        if current.name == cls_name:
            return True
        current = current.parent
    return False


def builtin_identical(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame if reciever is args[0] else runtime.false_frame


def builtin_equal(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    if "__value__" not in reciever.attributes:
        return builtin_identical(reciever, args, runtime)
    same = reciever.attributes["__value__"] == args[0].attributes.get("__value__")
    return runtime.true_frame if same else runtime.false_frame


def builtin_as_str(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_str("")


def builtin_is_nil(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame if is_instance(reciever, "Nil") else runtime.false_frame


def builtin_is_number(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame if is_instance(reciever, "Integer") else runtime.false_frame


def builtin_is_string(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame if is_instance(reciever, "String") else runtime.false_frame


def builtin_is_block(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame if is_instance(reciever, "Block") else runtime.false_frame


def builtin_is_bool(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    val = is_instance(reciever, "True") or is_instance(reciever, "False")
    return runtime.true_frame if val else runtime.false_frame


# ---- nil instance methods ---------------------------------------------------


def builtin_nil_as_str(
    _reciever: SolObject, _args: list[SolObject], runtime: Runtime
) -> SolObject:
    return runtime.make_str("nil")


# ---- integer instance methods -----------------------------------------------


def builtin_int_add(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_int(reciever.attributes["__value__"] + args[0].attributes["__value__"])


def builtin_int_sub(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_int(reciever.attributes["__value__"] - args[0].attributes["__value__"])


def builtin_int_mul(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_int(reciever.attributes["__value__"] * args[0].attributes["__value__"])


def builtin_int_div(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    val2: int = args[0].attributes["__value__"]
    if val2 == 0:
        raise InterpreterError(ErrorCode.INT_INVALID_ARG, "Division by zero")
    return runtime.make_int(reciever.attributes["__value__"] // val2)


def builtin_int_greater(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    val = reciever.attributes["__value__"] > args[0].attributes["__value__"]
    return runtime.true_frame if val else runtime.false_frame


def builtin_int_as_str(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_str(str(reciever.attributes["__value__"]))


def builtin_int_as_int(
    reciever: SolObject, _args: list[SolObject], _runtime: Runtime
) -> SolObject:
    return reciever


def builtin_int_times_repeat(
    reciever: SolObject, args: list[SolObject], runtime: Runtime
) -> SolObject:
    n: int = reciever.attributes["__value__"]
    result: SolObject = runtime.nil_frame
    for i in range(1, n + 1):
        result = runtime.exec_block(args[0], [runtime.make_int(i)])
    return result


# ---- string instance methods ------------------------------------------------


def builtin_string_print(
    reciever: SolObject, _args: list[SolObject], _runtime: Runtime
) -> SolObject:
    print(reciever.attributes.get("__value__", ""), end="", flush=True)
    return reciever


def equal_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    same = reciever.attributes["__value__"] == args[0].attributes["__value__"]
    return runtime.true_frame if same else runtime.false_frame


def as_str(reciever: SolObject, _args: list[SolObject], _runtime: Runtime) -> SolObject:
    return reciever


def as_int(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    try:
        return runtime.make_int(int(reciever.attributes["__value__"]))
    except ValueError:
        return runtime.nil_frame


def concat_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    if not isinstance(args[0].attributes.get("__value__"), str):
        return runtime.nil_frame
    return runtime.make_str(reciever.attributes["__value__"] + args[0].attributes["__value__"])


def substr_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    val: str = reciever.attributes["__value__"]
    if not isinstance(args[0].attributes.get("__value__"), int):
        return runtime.nil_frame
    if not isinstance(args[1].attributes.get("__value__"), int):
        return runtime.nil_frame
    start: int = args[0].attributes["__value__"]
    end: int = args[1].attributes["__value__"]
    if start <= 0 or end <= 0:
        return runtime.nil_frame
    if end - start <= 0:
        return runtime.make_str("")
    return runtime.make_str(val[start - 1 : end - 1])


def length_str(reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_int(len(reciever.attributes["__value__"]))


# ---- true instance methods --------------------------------------------------


def true_not(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.false_frame


def true_and(_reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.exec_block(args[0], [])


def true_or(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame


def true_if(_reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.exec_block(args[0], [])


def true_as_str(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_str("true")


# ---- False instance methods -------------------------------------------------


def false_not(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.true_frame


def false_and(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.false_frame


def false_or(_reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.exec_block(args[0], [])


def false_if(_reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.exec_block(args[1], [])


def false_as_str(_reciever: SolObject, _args: list[SolObject], runtime: Runtime) -> SolObject:
    return runtime.make_str("false")


# ---- block instance methods -------------------------------------------------


def value_block(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    block: Block = reciever.attributes["__block__"]
    if block.arity != len(args):
        raise InterpreterError(
            ErrorCode.INT_DNU, f"Block arity mismatch: expected {block.arity}, got {len(args)}"
        )
    return runtime.exec_block(reciever, args)


def while_true(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
    result: SolObject = runtime.nil_frame
    while runtime.exec_block(reciever, []) is runtime.true_frame:
        result = runtime.exec_block(args[0], [])
    return result


# =============================================================================
# MODULE-LEVEL STATIC VALIDATION HELPERS
# =============================================================================
# used by Interpreter.execute(), needed to keep at module level to avoid
# nested-def complexity in the execute() method


def check_block(block: Block, params: set[str]) -> None:
    """validate a block - no duplicate params/no assignment to a param"""
    params_set: set[str] = set()
    for param in block.parameters:
        if param.name in params_set:
            raise InterpreterError(
                ErrorCode.SEM_ERROR, f"Duplicate parameter '{param.name}' in block"
            )
        params_set.add(param.name)

    all_params = params | params_set
    for assign in block.assigns:
        if assign.target.name in all_params:
            raise InterpreterError(
                ErrorCode.SEM_COLLISION,
                f"Assignment to parameter '{assign.target.name}' is not allowed",
            )
        check_expr(assign.expr, all_params)


def check_expr(expr: Expr, params: set[str]) -> None:
    """recursively validate an expression for parameter violations"""
    if expr.block is not None:
        check_block(expr.block, params)
    if expr.send is not None:
        check_expr(expr.send.receiver, params)
        for arg in expr.send.args:
            check_expr(arg.expr, params)


# =============================================================================
# RUNTIME ENGINE
# =============================================================================


class Runtime:
    """executes a loaded SOL26 program"""

    def __init__(self, input_io: TextIO) -> None:
        """init the runtime and register all builtin classes"""
        self.classes: dict[str, SolClass] = {}
        self.input_io = input_io
        self._init_builtin_classes()

    # ---- helper functions used by builtin methods ---------------------------

    def make_int(self, value: int) -> SolObject:
        """create and return a new Integer instance"""
        obj = SolObject()
        obj.sol_class = self.int_class
        obj.attributes["__value__"] = value
        return obj

    def make_str(self, value: str) -> SolObject:
        """create and return a new String instance"""
        obj = SolObject()
        obj.sol_class = self.str_class
        obj.attributes["__value__"] = value
        return obj

    def exec_block(self, block_obj: SolObject, args: list[SolObject]) -> SolObject:
        """execute a captured Block object with the given arguments"""
        block: Block = block_obj.attributes["__block__"]
        env: Environment = block_obj.attributes["__env__"]
        self_obj: SolObject = block_obj.attributes["__self__"]
        cls: SolClass | None = block_obj.attributes.get("__current_cls__")
        return self.execute_method(block, args, env, self_obj, cls)

    # ---- builtin class initialisation ---------------------------------------

    def _init_builtin_classes(self) -> None:
        """init all builtin classes, their hierarchy and methods"""
        self._init_class_hierarchy()
        self._init_class_methods()
        self._init_object_methods()
        self._init_nil_methods()
        self._init_integer_methods()
        self._init_string_methods()
        self._init_boolean_methods()
        self._init_block_methods()

    def _init_class_hierarchy(self) -> None:
        """create SolClass objects, set up inheritance and create singletons"""
        self.object_class = SolClass("Object")
        self.object_class.parent = None
        self.classes["Object"] = self.object_class

        self.nil_class = SolClass("Nil")
        self.nil_class.parent = self.object_class
        self.classes["Nil"] = self.nil_class

        self.true_class = SolClass("True")
        self.true_class.parent = self.object_class
        self.classes["True"] = self.true_class

        self.false_class = SolClass("False")
        self.false_class.parent = self.object_class
        self.classes["False"] = self.false_class

        self.int_class = SolClass("Integer")
        self.int_class.parent = self.object_class
        self.classes["Integer"] = self.int_class

        self.str_class = SolClass("String")
        self.str_class.parent = self.object_class
        self.classes["String"] = self.str_class

        self.block_class = SolClass("Block")
        self.block_class.parent = self.object_class
        self.classes["Block"] = self.block_class

        self.nil_frame = SolObject()
        self.nil_frame.sol_class = self.nil_class

        self.true_frame = SolObject()
        self.true_frame.sol_class = self.true_class

        self.false_frame = SolObject()
        self.false_frame.sol_class = self.false_class

    def _init_class_methods(self) -> None:
        """register new/from: class methods"""
        self.object_class.class_methods["new"] = builtin_new
        self.object_class.class_methods["from:"] = builtin_from
        self.str_class.class_methods["read"] = builtin_str_read
        self.nil_class.class_methods["new"] = builtin_nil_new
        self.nil_class.class_methods["from:"] = builtin_nil_new
        self.true_class.class_methods["new"] = builtin_true_new
        self.true_class.class_methods["from:"] = builtin_true_new
        self.false_class.class_methods["new"] = builtin_false_new
        self.false_class.class_methods["from:"] = builtin_false_new
        self.block_class.class_methods["new"] = builtin_block_new

    def _init_object_methods(self) -> None:
        """register Object instance methods"""
        self.object_class.methods["identicalTo:"] = builtin_identical
        self.object_class.methods["equalTo:"] = builtin_equal
        self.object_class.methods["asString"] = builtin_as_str
        self.object_class.methods["isNil"] = builtin_is_nil
        self.object_class.methods["isNumber"] = builtin_is_number
        self.object_class.methods["isString"] = builtin_is_string
        self.object_class.methods["isBlock"] = builtin_is_block
        self.object_class.methods["isBoolean"] = builtin_is_bool

    def _init_nil_methods(self) -> None:
        """register Nil instance methods"""
        self.nil_class.methods["asString"] = builtin_nil_as_str

    def _init_integer_methods(self) -> None:
        """register Integer instance methods"""
        self.int_class.methods["plus:"] = builtin_int_add
        self.int_class.methods["minus:"] = builtin_int_sub
        self.int_class.methods["multiplyBy:"] = builtin_int_mul
        self.int_class.methods["divBy:"] = builtin_int_div
        self.int_class.methods["greaterThan:"] = builtin_int_greater
        self.int_class.methods["asString"] = builtin_int_as_str
        self.int_class.methods["asInteger"] = builtin_int_as_int
        self.int_class.methods["timesRepeat:"] = builtin_int_times_repeat

    def _init_string_methods(self) -> None:
        """register String instance methods"""
        self.str_class.methods["print"] = builtin_string_print
        self.str_class.methods["equalTo:"] = equal_str
        self.str_class.methods["asString"] = as_str
        self.str_class.methods["asInteger"] = as_int
        self.str_class.methods["concatenateWith:"] = concat_str
        self.str_class.methods["startsWith:endsBefore:"] = substr_str
        self.str_class.methods["length"] = length_str

    def _init_boolean_methods(self) -> None:
        """register True and False instance methods"""
        self.true_class.methods["not"] = true_not
        self.true_class.methods["and:"] = true_and
        self.true_class.methods["or:"] = true_or
        self.true_class.methods["ifTrue:ifFalse:"] = true_if
        self.true_class.methods["asString"] = true_as_str

        self.false_class.methods["not"] = false_not
        self.false_class.methods["and:"] = false_and
        self.false_class.methods["or:"] = false_or
        self.false_class.methods["ifTrue:ifFalse:"] = false_if
        self.false_class.methods["asString"] = false_as_str

    def _init_block_methods(self) -> None:
        """register Block instance methods"""
        self.block_class.methods["value"] = value_block
        self.block_class.methods["value:"] = value_block
        self.block_class.methods["value:value:"] = value_block
        self.block_class.methods["whileTrue:"] = while_true

    # ---- user class loading -------------------------------------------------

    def load_user_classes(self, classes: list[ClassDef]) -> None:
        """register user-defined classes, set up inheritance and methods"""
        for cls in classes:
            sol_class = SolClass(cls.name)
            self.classes[cls.name] = sol_class

        for cls in classes:
            if cls.parent in self.classes:
                self.classes[cls.name].parent = self.classes[cls.parent]
            else:
                raise InterpreterError(
                    ErrorCode.SEM_UNDEF,
                    f"The parent class '{cls.parent}' of '{cls.name}' was not defined",
                )

        for cls in classes:
            for meth in cls.methods:
                self.classes[cls.name].methods[meth.selector] = meth.block

    # ---- execution ----------------------------------------------------------

    def execute_method(
        self,
        block: Block,
        args: list[SolObject],
        env: Environment,
        self_obj: SolObject,
        current_cls: SolClass | None = None,
    ) -> SolObject:
        """execute block with the given arguments in a child scope"""
        new_env = Environment(parent=env)

        for param, arg in zip(block.parameters, args, strict=False):
            # params bind directly into the new scope, bypassing closure lookup
            new_env.variables[param.name] = arg

        result: SolObject = self.nil_frame
        for assign in block.assigns:
            value = self.eval_expression(assign.expr, new_env, self_obj, current_cls)
            # super stored in a variable loses its super semantics and acts as self
            if isinstance(value, SuperWrapper):
                value = value.obj
            if assign.target.name != "_":
                new_env.set(assign.target.name, value)
            result = value

        return result

    def eval_expression(
        self,
        expr: Expr,
        env: Environment,
        self_obj: SolObject,
        current_cls: SolClass | None = None,
    ) -> SolObject | SuperWrapper:
        """evaluate a single expression and return the result"""
        if expr.literal is not None:
            return self.eval_literal(expr.literal)
        if expr.var is not None:
            name = expr.var.name
            if name == "self":
                return self_obj
            if name == "nil":
                return self.nil_frame
            if name == "true":
                return self.true_frame
            if name == "false":
                return self.false_frame
            if name == "super":
                cls: SolClass = (
                    current_cls
                    if current_cls is not None
                    else (self_obj.sol_class or self.object_class)
                )
                return SuperWrapper(self_obj, cls)
            return env.get(expr.var.name)
        if expr.block is not None:
            return self.eval_block_lit(expr.block, env, self_obj, current_cls)
        if expr.send is not None:
            return self.eval_send(expr.send, env, self_obj, current_cls)

        raise InterpreterError(ErrorCode.GENERAL_OTHER, "Invalid expression")

    def eval_literal(self, literal: Literal) -> SolObject:
        """evaluate a literal node and return the corresponding runtime object"""
        obj = SolObject()

        if literal.class_id == "Integer":
            obj.sol_class = self.classes["Integer"]
            obj.attributes["__value__"] = int(literal.value)
        elif literal.class_id == "String":
            obj.sol_class = self.classes["String"]
            obj.attributes["__value__"] = literal.value
        elif literal.class_id == "Nil":
            return self.nil_frame
        elif literal.class_id == "True":
            return self.true_frame
        elif literal.class_id == "False":
            return self.false_frame
        elif literal.class_id == "class":
            class_name = literal.value
            if class_name not in self.classes:
                raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown class '{class_name}'")
            class_obj = SolObject()
            class_obj.sol_class = self.classes[class_name]
            class_obj.attributes["__is_class__"] = True
            return class_obj
        else:
            raise InterpreterError(
                ErrorCode.SEM_UNDEF, f"Unknown literal class '{literal.class_id}'"
            )

        return obj

    def eval_block_lit(
        self,
        block: Block,
        env: Environment,
        self_obj: SolObject,
        current_cls: SolClass | None = None,
    ) -> SolObject:
        """capture a block literal into a Block runtime object"""
        obj = SolObject()
        obj.sol_class = self.block_class
        obj.attributes["__block__"] = block
        obj.attributes["__env__"] = env
        obj.attributes["__self__"] = self_obj
        obj.attributes["__current_cls__"] = current_cls
        return obj

    def eval_send(
        self,
        send: Send,
        env: Environment,
        self_obj: SolObject,
        current_cls: SolClass | None = None,
    ) -> SolObject:
        """evaluate a message-send expression and return the result"""
        receiver = self.eval_expression(send.receiver, env, self_obj, current_cls)

        args: list[SolObject] = []
        for arg in send.args:
            val = self.eval_expression(arg.expr, env, self_obj, current_cls)
            if isinstance(val, SuperWrapper):
                val = val.obj
            args.append(val)

        return self.send_message(receiver, send.selector, args, env, current_cls)

    def dispatch_class_message(
        self, actual_obj: SolObject, selector: str, args: list[SolObject]
    ) -> SolObject:
        """go through the class hierarchy, looking for a class method and invoke it"""
        sol_cls: SolClass | None = actual_obj.sol_class
        while sol_cls is not None:
            if selector in sol_cls.class_methods:
                result: SolObject = sol_cls.class_methods[selector](actual_obj, args, self)
                return result
            sol_cls = sol_cls.parent

        assert actual_obj.sol_class is not None
        raise InterpreterError(
            ErrorCode.SEM_UNDEF,
            f"Unknown class method '{selector}' on class '{actual_obj.sol_class.name}'",
        )

    def send_message(
        self,
        receiver: SolObject | SuperWrapper,
        selector: str,
        args: list[SolObject],
        env: Environment,
        current_cls: SolClass | None = None,
    ) -> SolObject:
        """send a message to the receiver, handling class messages, methods, attributes"""
        if isinstance(receiver, SuperWrapper):
            actual_obj = receiver.obj
            start_cls: SolClass | None = receiver.start_cls.parent
        else:
            actual_obj = receiver
            start_cls = receiver.sol_class

        # class message
        if actual_obj.attributes.get("__is_class__"):
            return self.dispatch_class_message(actual_obj, selector, args)

        # instance method lookup
        sol_class = start_cls
        while sol_class is not None:
            if selector in sol_class.methods:
                method = sol_class.methods[selector]
                if callable(method):
                    instance: SolObject = method(actual_obj, args, self)
                    return instance
                return self.execute_method(method, args, env, actual_obj, sol_class)
            sol_class = sol_class.parent

        # zero-arg unknown selector - read instance attribute
        if len(args) == 0 and selector in actual_obj.attributes:
            val: SolObject = actual_obj.attributes[selector]
            return val

        # one-arg unknown selector - set instance attribute
        if len(args) == 1:
            name = selector[:-1]
            # collision check against LEXICAL class - not runtime class
            lexical_cls = current_cls if current_cls is not None else actual_obj.sol_class
            if lexical_cls is not None and name in lexical_cls.methods:
                raise InterpreterError(
                    ErrorCode.INT_INST_ATTR, f"Attribute '{name}' collides with an existing method"
                )
            actual_obj.attributes[name] = args[0]
            return actual_obj

        assert actual_obj.sol_class is not None
        raise InterpreterError(
            ErrorCode.INT_DNU,
            f"Receiver of class '{actual_obj.sol_class.name}' does not understand "
            f"the message '{selector}' with {len(args)} arguments",
        )


# =============================================================================
# INTERPRETER ENTRY POINT
# =============================================================================


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        """init with no program loaded"""
        self.current_program: Program | None = None

    def load_program(self, source_file_path: Path) -> None:
        """
        Reads the source SOL-XML file and stores it as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.

        IPP: If you wish to run static checks on the program before execution, this is a good place
             to call them from.
        """
        logger.info("Opening source file: %s", source_file_path)
        try:
            xml_bytes = source_file_path.read_bytes()
            self.current_program = Program.from_xml(xml_bytes)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

    BUILTIN_CLASS_NAMES: frozenset[str] = frozenset(
        ["Object", "Nil", "True", "False", "Integer", "String", "Block"]
    )

    def validate_no_builtin_redefinition(self, classes: list[ClassDef]) -> None:
        """raise SEM_ERROR if any user class redefines a builtin class"""
        for cls in classes:
            if cls.name in self.BUILTIN_CLASS_NAMES:
                raise InterpreterError(
                    ErrorCode.SEM_ERROR,
                    f"Redefinition of built-in class '{cls.name}' is not allowed",
                )

    def validate_no_duplicate_classes(self, classes: list[ClassDef]) -> None:
        """raise SEM_ERROR if the same class is defined more than once"""
        seen: set[str] = set()
        for cls in classes:
            if cls.name in seen:
                raise InterpreterError(
                    ErrorCode.SEM_ERROR, f"The class '{cls.name}' was defined more than once"
                )
            seen.add(cls.name)

    def validate_main_exists(self, classes: list[ClassDef]) -> None:
        """raise SEM_MAIN if Main class or its run method is missing"""
        main_class = next((c for c in classes if c.name == "Main"), None)
        if main_class is None:
            raise InterpreterError(ErrorCode.SEM_MAIN, "The 'Main' class is missing")

        method_run = next((m for m in main_class.methods if m.selector == "run"), None)
        if method_run is None:
            raise InterpreterError(ErrorCode.SEM_MAIN, "The 'Main' class is missing 'run' method")

    def validate_arity(self, classes: list[ClassDef]) -> None:
        """raise SEM_ARITY if method selector arity does not match its block arity"""
        for cls in classes:
            for meth in cls.methods:
                if meth.block.arity != meth.selector.count(":"):
                    raise InterpreterError(
                        ErrorCode.SEM_ARITY, f"Arity mismatch in method '{meth.selector}'"
                    )

    def validate_block_params(self, classes: list[ClassDef]) -> None:
        """raise SEM_ERROR/SEM_COLLISION on duplicate params or param assignment"""
        for cls in classes:
            for meth in cls.methods:
                check_block(meth.block, set())

    def validate_no_duplicate_methods(self, classes: list[ClassDef]) -> None:
        """raise SEM_ERROR if a class defines the same method selector more than once"""
        for cls in classes:
            seen: set[str] = set()
            for meth in cls.methods:
                if meth.selector in seen:
                    raise InterpreterError(
                        ErrorCode.SEM_ERROR,
                        f"Duplicate method selector '{meth.selector}' in class '{cls.name}'",
                    )
                seen.add(meth.selector)

    def validate_no_cyclic_inheritance(self, classes: list[ClassDef]) -> None:
        """raise SEM_ERROR if a cyclic inheritance is detected"""
        user_classes: set[str] = {cls.name for cls in classes}
        parent_map: dict[str, str] = {cls.name: cls.parent for cls in classes}
        for cls in classes:
            visited: set[str] = set()
            current = cls.name
            while current in user_classes:
                if current in visited:
                    raise InterpreterError(
                        ErrorCode.SEM_ERROR,
                        f"Cyclic inheritance detected involving class '{current}'",
                    )
                visited.add(current)
                current = parent_map[current]

    def execute(self, input_io: TextIO) -> None:
        """run the loaded program, reading input from the given stream"""
        logger.info("Executing program")

        if self.current_program is None:
            raise InterpreterError(ErrorCode.GENERAL_OTHER, "Program was not loaded")

        classes = self.current_program.classes
        self.validate_no_builtin_redefinition(classes)
        self.validate_no_duplicate_classes(classes)
        self.validate_main_exists(classes)
        self.validate_arity(classes)
        self.validate_block_params(classes)
        self.validate_no_duplicate_methods(classes)
        self.validate_no_cyclic_inheritance(classes)

        # run
        runtime = Runtime(input_io)
        runtime.load_user_classes(classes)

        main_object = SolObject()
        main_object.sol_class = runtime.classes["Main"]

        env = Environment()

        # pass Main as lexical class so collision checks work from the start
        run_block = runtime.classes["Main"].methods["run"]
        runtime.execute_method(run_block, [], env, main_object, runtime.classes["Main"])
