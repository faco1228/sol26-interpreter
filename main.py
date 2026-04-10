"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Samuel Fačka <xfackas00>
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import TextIO, Any

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Program, ClassDef, Method, Block, Expr, Literal, Send

logger = logging.getLogger(__name__)

# =============================================================================
# RUNTIME OBJECT MODEL
# =============================================================================

class SolObject:
    def __init__(self) -> None:
        self.sol_class: SolClass | None = None
        self.attributes: dict[str, Any] = {}

class SolClass:
    def __init__(self, name: str) -> None:
        self.name = name
        self.parent: SolClass | None = None
        self.methods: dict[str, Any] = {}
        self.class_methods: dict[str, Any] = {}

class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.variables: dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.get(name)
        
        raise InterpreterError(ErrorCode.SEM_UNDEF, f"Variable '{name}' was not defined")

    def set(self, name: str, value: Any) -> None:
        # update existing variable in nearest enclosing scope (closure semantics)
        env: Environment | None = self
        while env is not None:
            if name in env.variables:
                env.variables[name] = value
                return
            env = env.parent
        # new variable — create in current scope
        self.variables[name] = value

# wrapper for super — same object as self, but method lookup starts in parent class
class SuperWrapper:
    def __init__(self, obj: SolObject, start_cls: SolClass) -> None:
        self.obj = obj
        self.start_cls = start_cls

# =============================================================================
# RUNTIME ENGINE
# =============================================================================

class Runtime:
    def __init__(self, input_io: TextIO) -> None:
        self.classes: dict[str, SolClass] = {}
        self.input_io = input_io

        self._init_builtin_classes()

    # method to initialize built-in classes and their inheritance
    def _init_builtin_classes(self) -> None:

        # --- Class hierarchy ---
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

        # --- Singleton instances (nil, true, false) ---
        self.nil_frame = SolObject()
        self.nil_frame.sol_class = self.nil_class

        self.true_frame = SolObject()
        self.true_frame.sol_class = self.true_class

        self.false_frame = SolObject()
        self.false_frame.sol_class = self.false_class

        # --- String instance methods ---
        def builtin_string_print(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            value = reciever.attributes.get("__value__", "")
            print(value, end="", flush = True)
            return reciever

        self.str_class.methods["print"] = builtin_string_print

        # --- Class methods (new, from:, read) ---
        def builtin_new(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            obj = SolObject()
            obj.sol_class = reciever.sol_class
            if reciever.sol_class.name == "Integer":
                obj.attributes["__value__"] = 0
            if reciever.sol_class.name == "String":
                obj.attributes["__value__"] = ""
            return obj
        
        def builtin_from(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            arg = args[0]
            cls_name = reciever.sol_class.name
            # Integer/String require __value__ of correct type
            if cls_name == "Integer" and not isinstance(arg.attributes.get("__value__"), int):
                raise InterpreterError(ErrorCode.INT_INVALID_ARG, "from: argument must be an Integer")
            if cls_name == "String" and not isinstance(arg.attributes.get("__value__"), str):
                raise InterpreterError(ErrorCode.INT_INVALID_ARG, "from: argument must be a String")
            obj = SolObject()
            obj.sol_class = reciever.sol_class
            obj.attributes = dict(arg.attributes)
            return obj
        
        def builtin_str_read(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            line = runtime.input_io.readline()
            if line == "":
                # EOF — return nil
                return runtime.nil_frame
            line = line.rstrip("\n")
            obj = SolObject()
            obj.sol_class = runtime.str_class
            obj.attributes["__value__"] = line
            return obj
        
        def builtin_nil_new(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return runtime.nil_frame

        def builtin_nil_from(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return runtime.nil_frame

        self.object_class.class_methods["new"] = builtin_new
        self.object_class.class_methods["from:"] = builtin_from
        self.str_class.class_methods["read"] = builtin_str_read
        self.nil_class.class_methods["new"] = builtin_nil_new
        self.nil_class.class_methods["from:"] = builtin_nil_from

        def builtin_true_new(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return runtime.true_frame

        def builtin_false_new(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return runtime.false_frame

        self.true_class.class_methods["new"] = builtin_true_new
        self.true_class.class_methods["from:"] = builtin_true_new
        self.false_class.class_methods["new"] = builtin_false_new
        self.false_class.class_methods["from:"] = builtin_false_new

        def builtin_block_new(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            empty_block = Block(arity=0)
            obj = SolObject()
            obj.sol_class = runtime.block_class
            obj.attributes["__block__"] = empty_block
            obj.attributes["__env__"] = Environment()
            obj.attributes["__self__"] = runtime.nil_frame
            return obj

        self.block_class.class_methods["new"] = builtin_block_new

        # --- Object instance methods ---
        def builtin_identical(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if reciever is args[0]:
                return self.true_frame
            else:
                return self.false_frame
        
        def builtin_equal(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if "__value__" not in reciever.attributes:
                return builtin_identical(reciever, args, runtime)
            if reciever.attributes["__value__"] == args[0].attributes.get("__value__"):
                return self.true_frame
            return self.false_frame
        
        self.object_class.methods["identicalTo:"] = builtin_identical
        self.object_class.methods["equalTo:"] = builtin_equal

        # helper function to check if object is instance of the class or its subclass
        def is_instance(obj: SolObject, cls: str, runtime: Runtime) -> bool:
            current_cls = obj.sol_class
            while current_cls is not None:
                if current_cls.name == cls:
                    return True
                current_cls = current_cls.parent
            return False

        def builtin_as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            obj = SolObject()
            obj.sol_class = runtime.str_class
            obj.attributes["__value__"] = ""
            return obj
        
        def builtin_is_nil(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if is_instance(reciever, "Nil", runtime): #
                return self.true_frame
            else:
                return self.false_frame
        
        def builtin_is_number(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if is_instance(reciever, "Integer", runtime): #
                return self.true_frame 
            else:
                return self.false_frame
            
        def builtin_is_string(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if is_instance(reciever, "String", runtime): # 
                return self.true_frame
            else:
                return self.false_frame
            
        def builtin_is_block(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if is_instance(reciever, "Block", runtime): #
                return self.true_frame
            else:
                return self.false_frame
        
        def builtin_is_bool(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if is_instance(reciever, "True", runtime) or is_instance(reciever, "False", runtime): #
                return self.true_frame
            else:
                return self.false_frame
            
        self.object_class.methods["asString"] = builtin_as_str
        self.object_class.methods["isNil"] = builtin_is_nil
        self.object_class.methods["isNumber"] = builtin_is_number
        self.object_class.methods["isString"] = builtin_is_string
        self.object_class.methods["isBlock"] = builtin_is_block
        self.object_class.methods["isBoolean"] = builtin_is_bool

        def make_int(value: int) -> SolObject:
            obj = SolObject()
            obj.sol_class = self.int_class
            obj.attributes["__value__"] = value
            return obj

        def builtin_int_add(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            return make_int(val1 + val2)
        
        def builtin_int_sub(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            return make_int(val1 - val2)
        
        def builtin_int_mul(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            return make_int(val1 * val2)
        
        def builtin_int_div(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            if val2 == 0:
                raise InterpreterError(ErrorCode.INT_INVALID_ARG, "Division by zero")
            return make_int(val1 // val2)
        
        def builtin_int_greater(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            if val1 > val2:
                return self.true_frame
            else:
                return self.false_frame
            
        def builtin_int_as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            value = reciever.attributes["__value__"]
            obj = SolObject()
            obj.sol_class = runtime.str_class
            obj.attributes["__value__"] = str(value)
            return obj

        def builtin_int_as_int(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return reciever
        
        def builtin_nil_as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            obj = SolObject()
            obj.sol_class = runtime.str_class
            obj.attributes["__value__"] = "nil"
            return obj
        
        def builtin_int_times_repeat(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            value = reciever.attributes["__value__"]
            block = args[0]
            result: SolObject = runtime.nil_frame
            for i in range(1, value + 1):
                result = exec_block(block, [make_int(i)], runtime)
            return result

        self.int_class.methods["plus:"] = builtin_int_add
        self.int_class.methods["minus:"] = builtin_int_sub
        self.int_class.methods["multiplyBy:"] = builtin_int_mul
        self.int_class.methods["divBy:"] = builtin_int_div
        self.int_class.methods["greaterThan:"] = builtin_int_greater
        self.int_class.methods["asString"] = builtin_int_as_str
        self.int_class.methods["asInteger"] = builtin_int_as_int
        self.nil_class.methods["asString"] = builtin_nil_as_str
        self.int_class.methods["timesRepeat:"] = builtin_int_times_repeat

        def make_str(value: str) -> SolObject:
            obj = SolObject()
            obj.sol_class = self.str_class
            obj.attributes["__value__"] = value
            return obj
        
        def equal_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            if val1 == val2:
                return self.true_frame
            else:
                return self.false_frame
            
        def as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return reciever
        
        def as_int(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            value = reciever.attributes["__value__"]
            try:
                int_value = int(value)
            except ValueError:
                return runtime.nil_frame
            return make_int(int_value)
        
        def concat_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            if "__value__" not in args[0].attributes or not isinstance(args[0].attributes["__value__"], str):
                return runtime.nil_frame
            val1 = reciever.attributes["__value__"]
            val2 = args[0].attributes["__value__"]
            return make_str(val1 + val2)
        
        def substr_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val = reciever.attributes["__value__"]
            # args must be positive integers
            if not isinstance(args[0].attributes.get("__value__"), int) or not isinstance(args[1].attributes.get("__value__"), int):
                return runtime.nil_frame
            start = args[0].attributes["__value__"]
            end = args[1].attributes["__value__"]
            if start <= 0 or end <= 0:
                return runtime.nil_frame
            if end - start <= 0:
                return make_str("")
            # convert to 0-based, clamp end to length
            return make_str(val[start - 1 : end - 1])
            
        def length_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            val = reciever.attributes["__value__"]
            return make_int(len(val))
        
        self.str_class.methods["equalTo:"] = equal_str
        self.str_class.methods["asString"] = as_str
        self.str_class.methods["asInteger"] = as_int
        self.str_class.methods["concatenateWith:"] = concat_str
        self.str_class.methods["startsWith:endsBefore:"] = substr_str
        self.str_class.methods["length"] = length_str

        def exec_block(block_obj: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            block = block_obj.attributes["__block__"]
            env = block_obj.attributes["__env__"]
            self_obj = block_obj.attributes["__self__"]
            cls = block_obj.attributes.get("__current_cls__")
            return runtime.execute_method(block, args, env, self_obj, cls)
        
        # true methods
        def true_not(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return self.false_frame
        
        def true_and(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return exec_block(args[0], [], runtime)
        
        def true_or(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return self.true_frame
        
        def true_if(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return exec_block(args[0], [], runtime)
        
        def true_as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return make_str("true")
        
        # false methods
        def false_not(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return self.true_frame
        
        def false_and(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return self.false_frame
        
        def false_or(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return exec_block(args[0], [], runtime)
        
        def false_if(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return exec_block(args[1], [], runtime)
        
        def false_as_str(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            return make_str("false")

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


        def value_block(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            block = reciever.attributes["__block__"]
            env = reciever.attributes["__env__"]
            self_obj = reciever.attributes["__self__"]
            if block.arity != len(args):
                raise InterpreterError(ErrorCode.INT_DNU, f"Block arity mismatch: expected {block.arity}, got {len(args)}")
            return runtime.execute_method(block, args, env, self_obj)
        
        def while_true(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            result: SolObject = runtime.nil_frame
            while exec_block(reciever, [], runtime) is runtime.true_frame:
                result = exec_block(args[0], [], runtime)
            return result
        
        self.block_class.methods["value"] = value_block
        self.block_class.methods["value:"] = value_block
        self.block_class.methods["value:value:"] = value_block
        self.block_class.methods["whileTrue:"] = while_true


    # method to load user defined classes into runtime
    def load_user_classes(self, classes: list[ClassDef]) -> None:
        for cls in classes:
            sol_class = SolClass(cls.name)
            self.classes[cls.name] = sol_class

        for cls in classes:
            if cls.parent in self.classes:
                self.classes[cls.name].parent = self.classes[cls.parent]
            else:
                raise InterpreterError(ErrorCode.SEM_UNDEF, f"The parent class '{cls.parent}' of '{cls.name}' was not defined")
            
        for cls in classes:
            for meth in cls.methods:
                self.classes[cls.name].methods[meth.selector] = meth.block

    # method to execute a method with given block, arguments, environment and self object
    def execute_method(self, block: Block, args: list[SolObject], env: Environment, self_obj: SolObject, current_cls: SolClass | None = None) -> SolObject:
        # new env
        new_env = Environment(parent=env)

        for param, arg in zip(block.parameters, args):
            # parameters always shadow outer scope — set directly, no closure traversal
            new_env.variables[param.name] = arg
        
        result = self.nil_frame
        for assign in block.assigns:
            value = self.eval_expression(assign.expr, new_env, self_obj, current_cls)
            # super assigned to variable behaves as self (spec 1.2.8)
            if isinstance(value, SuperWrapper):
                value = value.obj
            if assign.target.name != "_":
                new_env.set(assign.target.name, value)
            result = value
        
        return result
    
    # method to evaluate an expression in given environment and self object
    def eval_expression(self, expr: Expr, env: Environment, self_obj: SolObject, current_cls: SolClass | None = None) -> SolObject | SuperWrapper:
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
                if current_cls is not None:
                    cls = current_cls
                else:
                    cls = self_obj.sol_class
                return SuperWrapper(self_obj, cls)
            return env.get(expr.var.name)
        if expr.block is not None:
            return self.eval_block_lit(expr.block, env, self_obj, current_cls)
        if expr.send is not None:
            return self.eval_send(expr.send, env, self_obj, current_cls) 
        
        raise InterpreterError(ErrorCode.GENERAL_OTHER, "Invalid expression")
    
    def eval_literal(self, literal: Literal) -> SolObject:
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
            # class reference: <literal class="class" value="ClassName"/>
            class_name = literal.value
            if class_name not in self.classes:
                raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown class '{class_name}'")
            class_obj = SolObject()
            class_obj.sol_class = self.classes[class_name]
            class_obj.attributes["__is_class__"] = True
            return class_obj
        else:
            raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown literal class '{literal.class_id}'")
        
        return obj
    
    def eval_block_lit(self, block: Block, env: Environment, self_obj: SolObject, current_cls: SolClass | None = None) -> SolObject:
        obj = SolObject()

        obj.sol_class = self.block_class
        obj.attributes["__block__"] = block
        obj.attributes["__env__"] = env
        obj.attributes["__self__"] = self_obj
        # capture lexical class so exec_block can use it for collision checks
        obj.attributes["__current_cls__"] = current_cls

        return obj
    
    def eval_send(self, send: Send, env: Environment, self_obj: SolObject, current_cls: SolClass | None = None) -> SolObject:
        # evaluate recriver
        receiver = self.eval_expression(send.receiver, env, self_obj, current_cls)

        # evaluate args
        args = []
        for arg in send.args:
            val = self.eval_expression(arg.expr, env, self_obj, current_cls)
            if isinstance(val, SuperWrapper):
                val = val.obj
            args.append(val)

        # find and call coressponding method
        return self.send_message(receiver, send.selector, args, env, current_cls)
    
    def send_message(self, receiver: SolObject | SuperWrapper, selector: str, args: list[SolObject], env: Environment, current_cls: SolClass | None = None) -> SolObject:
        # devide super from normal object
        if isinstance(receiver, SuperWrapper):
            actual_obj = receiver.obj
            start_cls: SolClass | None = receiver.start_cls.parent
        else:
            actual_obj = receiver
            start_cls = receiver.sol_class

        # class message handling
        if actual_obj.attributes.get("__is_class__"):
            sol_cls: SolClass | None = actual_obj.sol_class
            while sol_cls is not None:
                if selector in sol_cls.class_methods:
                    return sol_cls.class_methods[selector](actual_obj, args, self)
                sol_cls = sol_cls.parent
            raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown class method '{selector}' on class '{actual_obj.sol_class.name}'")

        # search for method in class and parent classes
        sol_class = start_cls
        while sol_class is not None:
            if selector in sol_class.methods:
                method = sol_class.methods[selector]
                if callable(method):
                    return method(actual_obj, args, self)
                else:
                    return self.execute_method(method, args, env, actual_obj, sol_class)
            sol_class = sol_class.parent

        # if args are empty (dont have params), read atributes
        if len(args) == 0 and selector in actual_obj.attributes:
            return actual_obj.attributes[selector]
        
        # if args has only 1 element, set atribute
        if len(args) == 1:
            atribute_name = selector[:-1]
            # collision check against LEXICAL class (where self is written), not runtime class
            lexical_cls = current_cls if current_cls is not None else actual_obj.sol_class
            if lexical_cls is not None and atribute_name in lexical_cls.methods:
                raise InterpreterError(ErrorCode.INT_INST_ATTR, f"Atribute '{atribute_name}' have collision with method")
            actual_obj.attributes[atribute_name] = args[0]
            return actual_obj

        raise InterpreterError(ErrorCode.INT_DNU, f"Receiver of class '{actual_obj.sol_class.name}' does not understand the message '{selector}' with {len(args)} arguments")

# =============================================================================
# INTERPRETER ENTRY POINT
# =============================================================================

class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
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
            xml_tree = etree.parse(source_file_path)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            self.current_program = Program.from_xml_tree(xml_tree.getroot())  # type: ignore
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

    def execute(self, input_io: TextIO) -> None:
        """
        Executes the currently loaded program, using the provided input stream as standard input.
        """
        logger.info("Executing program")

        BUILTIN_CLASSES_NAMES = frozenset(["Object", "Nil", "True", "False", "Integer", "String", "Block"])

        # local helper functions/methods for Interpreter

        def check_block(block: Block, params: set[str]) -> None:
            # duplicate parameters in this block (error code 35)
            params_set = set()
            for param in block.parameters:
                if param.name in params_set:
                    raise InterpreterError(ErrorCode.SEM_ERROR, f"Duplicate parameter '{param.name}' in block")
                params_set.add(param.name)
            
            all_params = params | params_set

            # assignment to block parameter (error code 34)
            for assign in block.assigns:
                if assign.target.name in all_params:
                    raise InterpreterError(ErrorCode.SEM_COLLISION, f"Assignment to parameter '{assign.target.name}' is not allowed, read-only")
                check_expr(assign.expr, all_params)
        
        def check_expr(expr: Expr, params: set[str]) -> None:
            if expr.block is not None:
                check_block(expr.block, params)
            if expr.send is not None:
                check_expr(expr.send.receiver, params)
                for arg in expr.send.args:
                    check_expr(arg.expr, params)


        # implementation of python interpreter
        
        # --- Guard: program must be loaded before execution (error code 99) ---
        if self.current_program is None:
            raise InterpreterError(ErrorCode.GENERAL_OTHER, "Program was not loaded")
 

        # check for redifinition of built-in classes (error code 35)
        for cls in self.current_program.classes:
            if cls.name in BUILTIN_CLASSES_NAMES:
                raise InterpreterError(ErrorCode.SEM_ERROR, f"Redefinition of built-in class '{cls.name}' is not allowed")


        # --- Static check: no duplicate class definitions (error code 35) ---
        have_seen: set[str] = set()

        for cls in self.current_program.classes:
            if cls.name in have_seen:
                raise InterpreterError(ErrorCode.SEM_ERROR, f"The class '{cls.name}' was defined more than once")
            have_seen.add(cls.name)


        # --- Static check: class Main with method run must exist (error code 31) ---
        main_class = None
        for cls in self.current_program.classes:
            if cls.name == "Main":
                main_class = cls
                break

        if main_class is None:
            raise InterpreterError(ErrorCode.SEM_MAIN, "The 'Main' class is missing")

        method_run = None
        for meth in main_class.methods:
            if meth.selector == "run":
                method_run = meth
                break        
                    
        if method_run is None:
            raise InterpreterError(ErrorCode.SEM_MAIN, "The 'Main' class is missing 'run' method")


        # --- Static check: method selector arity must match block arity (error 33) ---
        for cls in self.current_program.classes:
            for meth in cls.methods:
                params_count = meth.selector.count(":")
                if meth.block.arity != params_count:
                    raise InterpreterError(ErrorCode.SEM_ARITY, f"Arity mismatch occured in method '{meth.selector}'")
                

        # --- Static checks: duplicate parameters (35) and assignment to parameter (34) ---
        for cls in self.current_program.classes:
            for meth in cls.methods:
                check_block(meth.block, set())

        
        # --- Static check: duplicate class methods (error code 35) ---
        for cls in self.current_program.classes:
            have_seen: set[str] = set()
            for meth in cls.methods:
                if meth.selector in have_seen:
                    raise InterpreterError(ErrorCode.SEM_ERROR, f"Duplicate method selector '{meth.selector}' in class '{cls.name}'")
                have_seen.add(meth.selector)

        
                
        # -- Static check: cyclic inheritance (error code 35) ---
        user_classes: set[str] = set() 
        parent_map: dict[str, str] = {}
        for cls in self.current_program.classes:
            user_classes.add(cls.name)
            parent_map[cls.name] = cls.parent

        for cls in self.current_program.classes:
            visited: set[str] = set()
            current_cls = cls.name
            while current_cls in user_classes:
                if current_cls in visited:
                    raise InterpreterError(ErrorCode.SEM_ERROR, f"Cyclic inheritance detected involving class '{current_cls}'")
                visited.add(current_cls)
                current_cls = parent_map[current_cls]

                    
        # load data
        runtime = Runtime(input_io)
        runtime.load_user_classes(self.current_program.classes)

        # instance Main
        main_object = SolObject()
        main_object.sol_class = runtime.classes["Main"]

        # empty environment
        env = Environment()

        # call method 'run' — pass Main as lexical class for collision checks
        run_block = runtime.classes["Main"].methods["run"]
        runtime.execute_method(run_block, [], env, main_object, runtime.classes["Main"])
