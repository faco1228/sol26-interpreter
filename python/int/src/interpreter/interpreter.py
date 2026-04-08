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

# definitions of classes for interpreter
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
        self.variables[name] = value

# wrapper for super - same object as self but method lookup starts in parent class
class SuperWrapper:
    def __init__(self, obj: SolObject, start_cls: SolClass) -> None:
        self.obj = obj
        self.start_cls = start_cls

# build-in classes
class Runtime:
    def __init__(self, input_io: TextIO) -> None:
        self.classes: dict[str, SolClass] = {}
        self.input_io = input_io

        self._init_builtin_classes()

    # method to initialize built-in classes and their inheritance
    def _init_builtin_classes(self) -> None:

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

        # empty frames for literals
        self.nil_frame = SolObject()
        self.nil_frame.sol_class = self.nil_class

        self.true_frame = SolObject()
        self.true_frame.sol_class = self.true_class

        self.false_frame = SolObject()
        self.false_frame.sol_class = self.false_class

        def builtin_string_print(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            value = reciever.attributes.get("__value__", "")
            print(value, end="", flush = True)
            return reciever

        self.str_class.methods["print"] = builtin_string_print

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
            obj = SolObject()
            obj.sol_class = reciever.sol_class
            obj.attributes = dict(arg.attributes)
            return obj
        
        def builtin_str_read(reciever: SolObject, args: list[SolObject], runtime: Runtime) -> SolObject:
            line = runtime.input_io.readline()
            line = line.rstrip("\n")
            obj = SolObject()
            obj.sol_class = runtime.str_class
            obj.attributes["__value__"] = line
            return obj
        
        self.object_class.class_methods["new"] = builtin_new
        self.object_class.class_methods["from:"] = builtin_from
        self.str_class.class_methods["read"] = builtin_str_read

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
    def execute_method(self, block: Block, args: list[SolObject], env: Environment, self_obj: SolObject) -> SolObject | None:
        # new env
        new_env = Environment(parent=env)

        for param, arg in zip(block.parameters, args):
            new_env.set(param.name, arg)
        
        result = None
        for assign in block.assigns:
            value = self.eval_expression(assign.expr, new_env, self_obj)
            if assign.target.name != "_":
                new_env.set(assign.target.name, value)
            result = value
        
        return result
    
    # method to evaluate an expression in given environment and self object
    def eval_expression(self, expr: Expr, env: Environment, self_obj: SolObject) -> SolObject | SuperWrapper:
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
                return SuperWrapper(self_obj, self_obj.sol_class)
            return env.get(expr.var.name)
        if expr.block is not None:
            return self.eval_block_lit(expr.block, env, self_obj)
        if expr.send is not None:
            return self.eval_send(expr.send, env, self_obj) 
        
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
        
        else:
            if literal.class_id in self.classes:
                class_obj = SolObject()
                class_obj.sol_class = self.classes[literal.class_id]
                class_obj.attributes["__is_class__"] = True
                return class_obj
            raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown class '{literal.class_id}'")
        
        return obj
    
    def eval_block_lit(self, block: Block, env: Environment, self_obj: SolObject) -> SolObject:
        obj = SolObject()

        obj.sol_class = self.block_class
        obj.attributes["__block__"] = block
        obj.attributes["__env__"] = env
        obj.attributes["__self__"] = self_obj

        return obj
    
    def eval_send(self, send: Send, env: Environment, self_obj: SolObject) -> SolObject:
        # evaluate recriver
        receiver = self.eval_expression(send.receiver, env, self_obj)

        # evaluate args
        args = []
        for arg in send.args:
            args.append(self.eval_expression(arg.expr, env, self_obj))

        # find and call coressponding method
        return self.send_message(receiver, send.selector, args, env)
    
    def send_message(self, receiver: SolObject | SuperWrapper, selector: str, args: list[SolObject], env: Environment) -> SolObject:
        # devide super from normal object
        if isinstance(receiver, SuperWrapper):
            actual_obj = receiver.obj
            start_cls: SolClass | None = receiver.start_cls.parent
        else:
            actual_obj = receiver
            start_cls = receiver.sol_class

        # class message handling
        if actual_obj.attributes.get("__is_class__"):
            sol_cls = actual_obj.sol_class
            if selector in sol_cls.class_methods:
                return sol_cls.class_methods[selector](actual_obj, args, self)
            raise InterpreterError(ErrorCode.SEM_UNDEF, f"Unknown class method '{selector}' on class '{sol_cls.name}'")

        # search for method in class and parent classes
        sol_class = start_cls
        while sol_class is not None:
            if selector in sol_class.methods:
                method = sol_class.methods[selector]
                if callable(method):
                    return method(actual_obj, args, self)
                else:
                    return self.execute_method(method, args, env, actual_obj)
            sol_class = sol_class.parent

        # if args are empty (dont have params), read atributes
        if len(args) == 0 and selector in actual_obj.attributes:
            return actual_obj.attributes[selector]
        
        # if args has only 1 element, set atribute
        if len(args) == 1:
            atribute_name = selector[:-1]
            check_class: SolClass | None = actual_obj.sol_class
            while check_class is not None:
                # check for collision with method
                if atribute_name in check_class.methods:
                    raise InterpreterError(ErrorCode.INT_INST_ATTR, f"Atribute '{atribute_name}' have collision with method")
                check_class = check_class.parent
            actual_obj.attributes[atribute_name] = args[0]
            return actual_obj

        raise InterpreterError(ErrorCode.INT_DNU, f"Receiver of class '{actual_obj.sol_class.name}' does not understand the message '{selector}' with {len(args)} arguments")

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

        # call methon 'run'
        run_block = runtime.classes["Main"].methods["run"]
        runtime.execute_method(run_block, [], env, main_object)
