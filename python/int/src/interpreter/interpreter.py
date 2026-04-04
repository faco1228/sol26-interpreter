"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author:
"""

import logging
from pathlib import Path
from typing import TextIO, Any
from __future__ import annotations

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Program

logger = logging.getLogger(__name__)

# definitions of classes for interpreter
class SolObject:
    def __init__(self) -> None:
        self.sol_class: Any = None
        self.attributes: dict = {}

class SolClass:
    def __init__(self, name: str) -> None:
        self.name = name
        self.parent: SolClass | None = None
        self.methods: dict = {}

class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.variables: dict = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.get(name)
        
        raise InterpreterError(ErrorCode.SEM_UNDEF, f"Variable '{name}' was not defined")

    def set(self, name: str, value: Any) -> None:
        self.variables[name] = value



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
        have_seen = set()

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
                    
                    
                    
