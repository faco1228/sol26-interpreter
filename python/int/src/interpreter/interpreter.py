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
        self.sol_class: Any = None
        self.attributes: dict[str, Any] = {}

class SolClass:
    def __init__(self, name: str) -> None:
        self.name = name
        self.parent: SolClass | None = None
        self.methods: dict[str, Any] = {}

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
    def eval_expression(self, expr: Expr, env: Environment, self_obj: SolObject) -> SolObject:
        if expr.literal is not None:
            return self.eval_literal(expr.literal)
        if expr.var is not None:
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
            raise InterpreterError(ErrorCode.GENERAL_OTHER, f"Unknown literal type '{literal.class_id}'")
        
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
    
    def send_message(self, receiver: SolObject, selector: str, args: list[SolObject], env: Environment) -> SolObject:
        # search for method in class and parent classes
        sol_class: SolClass | None = receiver.sol_class
        while sol_class is not None:
            if selector in sol_class.methods:
                method = sol_class.methods[selector]
                if callable(method):
                    return method(receiver, args, self)
                else:
                    raise self.execute_method(method, args, env, receiver)
            sol_class = sol_class.parent

        # if args are empty (dont have params), read atributes
        if len(args) == 0 and selector in receiver.attributes:
            return receiver.attributes[selector]
        
        # if args has only 1 element, set atribute
        if len(args) == 1:
            atribute_name = selector[:-1]
            check_class: SolClass | None = receiver.sol_class
            while check_class is not None:
                # check for collision with method
                if atribute_name in check_class.methods:
                    raise InterpreterError(ErrorCode.INT_INST_ATTR, f"Atribute '{atribute_name}' have collision with method")
                check_class = check_class.parent
            receiver.attributes[atribute_name] = args[0]
            return receiver

        raise InterpreterError(ErrorCode.INT_DNU, f"Receiver of class '{receiver.sol_class.name}' does not understand the message '{selector}' with {len(args)} arguments")

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

        # implementation of python interpreter
        
        # --- Guard: program must be loaded before execution (error code 99) ---
        if self.current_program is None:
            raise InterpreterError(ErrorCode.GENERAL_OTHER, "Program was not loaded")
 

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
                
        
        # --- Static check: assignment to block parameter is forbidden (error 34) ---
        for cls in self.current_program.classes:
            for meth in cls.methods:
                params_names = []
                for param in meth.block.parameters:
                    params_names.append(param.name)
                
                for assign in meth.block.assigns:
                    if assign.target.name in params_names:
                        raise InterpreterError(ErrorCode.SEM_COLLISION, f"Assignment to parameter '{assign.target.name}' is not allowed, read-only")
                    
                    
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
