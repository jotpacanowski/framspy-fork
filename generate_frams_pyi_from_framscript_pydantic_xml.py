#! /usr/bin/env -S uv run --script
# https://akrabat.com/using-uv-as-your-shebang-line/
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pydantic",
#     "pydantic-xml",
#     "rich",
# ]
# ///
import collections
import contextlib
import io
import json  # noqa: F401
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET  # noqa: F401
from pathlib import Path
from typing import List, Literal, Optional  # noqa: UP035

import pydantic_core
from pydantic import BaseModel  # noqa: F401
from pydantic_xml import BaseXmlModel, attr, element

try:
    from rich import print as rprint
except ImportError:
    rprint = print

INVALID_PY_IDENTS = [
    "import",
    "class",
    "def",  # e.g. Neuro.def
    "as",  # Part.as
]
GLOBAL_CONTEXT = "Global context"

MAP_TO_SIMPLE_PY_TYPE = {
    "string": "str",
    "float": "float",
    "integer": "int",
    "void": "None",
    "untyped": "Any",  # None,
}
"Mapping between framscript and simple Python types"

# ---


def format_code_with_ruff(code: str) -> str:
    """
    Checks if Ruff is available and formats the given Python code string using Ruff.

    Parameters:
        code (str): The Python code to format.

    Returns:
        str: The formatted code if Ruff is available, otherwise the original code.
    """
    try:
        # Check if Ruff is installed and available
        subprocess.run(
            ["ruff", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        # Ruff is not installed
        print("Ruff is not available. Returning the original code.")
        return code
    except subprocess.CalledProcessError as e:
        # Ruff command failed for some reason
        print(f"Error checking Ruff availability: {e}")
        return code

    try:
        # Use Ruff to format the code
        process = subprocess.run(
            ["ruff", "format", "-"],
            input=code,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.returncode == 0:
            # Return the formatted code
            return process.stdout
        else:
            # Ruff failed to format the code
            print(f"Ruff formatting failed: {process.stderr}", file=sys.stderr)
            return code
    except Exception as e:
        # Handle unexpected errors
        print(f"An error occurred while formatting with Ruff: {e}")
        return code


# ---

# Install: pip install pydantic-xml


class Argument(BaseXmlModel, tag="argument"):
    name: Optional[str] = attr(default=None)
    type: Optional[str] = attr(default=None)
    description: Optional[str] = element(default="")


class Arguments(BaseXmlModel, tag="arguments"):
    arguments: List[Argument] = element(tag="argument", default_factory=list)


class Element(BaseXmlModel, tag="element"):
    id: str = attr()
    name: Optional[str] = attr(default=None)  # maybe missing
    type: Optional[str] = attr(default=None)
    function: Optional[str] = attr(default="false")
    deprecated: Optional[str] = attr(default="false")
    default: Optional[str] = attr(default=None)
    min: Optional[str] = attr(default=None)
    max: Optional[str] = attr(default=None)
    flags: Optional[str] = attr(default=None)

    description: Optional[str] = element(default="")
    arguments: Optional[Arguments] = element(default=None)

    @property
    def is_function(self) -> bool:
        return self.function == "true"

    @property
    def is_deprecated(self) -> bool:
        return self.deprecated == "true"

    @property
    def get_arguments(self) -> List[Argument]:
        if self.arguments:
            return self.arguments.arguments
        return []


class Type(BaseXmlModel, tag="type"):
    name: str = attr()
    # context: str = attr()
    context: Literal[
        "Command line interface",
        "Experiment definition",
        "Fitness formula",
        "Framsticks Theater",
        "Global context",
        "Neuron definitions",
        "Signal label formula",
        "Visual style definition",
        "expdef file",
        "neuro file",
        "properties file",
        "script file",
        "show file",
        "state file",
        "style file",
    ] = attr()
    description: Optional[str] = element(default="")
    elements: List[Element] = element(tag="element", default_factory=list)


class FramscriptDoc(BaseXmlModel, tag="framscript"):
    types: List[Type] = element(tag="type", default_factory=list)


# Usage examples
def parse_framscript_xml(xml_file_path: str) -> FramscriptDoc:
    """Parse Framscript XML file using pydantic-xml"""
    with open(xml_file_path, "r", encoding="utf-8") as file:
        xml_content = file.read()

    return FramscriptDoc.from_xml(xml_content)


def parse_framscript_xml_string(xml_string: str) -> FramscriptDoc:
    """Parse Framscript XML from string"""
    return FramscriptDoc.from_xml(xml_string)


# ---


# Utility functions
def print_summary(doc: FramscriptDoc):
    """Print a summary of the parsed document"""
    print("Framscript Documentation Summary:")
    print(f"Total types: {len(doc.types)}")
    print()

    possible_contexts = set()

    for type_obj in doc.types:
        print(f"Type: {type_obj.name} (context: {type_obj.context})")
        possible_contexts.add(type_obj.context)
        # if type_obj.description:
        #     print(f"  Description: {type_obj.description}")

        functions = [e for e in type_obj.elements if e.is_function]
        fields = [e for e in type_obj.elements if not e.is_function]

        print(f"  Functions: {len(functions)}")
        print(f"  Fields: {len(fields)}")

        # Show deprecated items
        deprecated = [e for e in type_obj.elements if e.is_deprecated]
        if deprecated:
            print(f"  Deprecated items: {len(deprecated)}")

        print()

    possible_contexts = list(sorted(possible_contexts))
    print(f"\nContexts: {possible_contexts}")


def find_type_by_name(doc: FramscriptDoc, name: str) -> Optional[Type]:
    """Find a type by name"""
    for type_obj in doc.types:
        if type_obj.name == name:
            return type_obj
    return None


def get_all_functions(doc: FramscriptDoc) -> List[Element]:
    """Get all functions from all types"""
    functions = []
    for type_obj in doc.types:
        functions.extend([e for e in type_obj.elements if e.is_function])
    return functions


def get_functions_with_args(doc: FramscriptDoc) -> List[Element]:
    """Get all functions that have arguments"""
    functions_with_args = []
    for type_obj in doc.types:
        for elem in type_obj.elements:
            if elem.is_function and elem.arguments and elem.arguments.arguments:
                functions_with_args.append(elem)
    return functions_with_args


def main_example(filename=None):
    # Example XML content (replace with your actual file)
    example_xml = """<?xml version="1.0"?>
    <framscript>
        <type name="World" context="world.cpp">
            <description>Represents the simulation world</description>
            <element name="size" type="integer">
                <description>World size in units</description>
            </element>
            <element name="getName" type="string" function="true">
                <description>Returns the world name</description>
                <arguments>
                    <argument name="format" type="string">Format specification</argument>
                </arguments>
            </element>
            <element name="oldMethod" type="string" function="true" deprecated="true">
                <description>This method is deprecated</description>
                <arguments></arguments>
            </element>
        </type>
        <type name="Creature" context="creature.cpp">
            <description>A creature in the simulation</description>
            <element name="energy" type="float">
                <description>Current energy level</description>
            </element>
            <element name="move" type="void" function="true">
                <description>Move the creature</description>
                <arguments>
                    <argument name="x" type="float">X coordinate</argument>
                    <argument name="y" type="float">Y coordinate</argument>
                </arguments>
            </element>
        </type>
    </framscript>"""

    if filename is None:
        # Parse from string
        # doc = parse_framscript_xml_string(example_xml)
        doc = FramscriptDoc.from_xml(example_xml)
    else:
        doc = parse_framscript_xml(filename)

    # Print summary
    print_summary(doc)
    print()

    # Find specific type
    some_type = find_type_by_name(doc, "World")
    # some_type = find_type_by_name(doc, "GenMan")
    # some_type = find_type_by_name(doc, "String")
    if some_type:
        print(f"Found World type with {len(some_type.elements)} elements")

    # for el in some_type.elements:
    #     print(el)
    # raise SystemExit

    # Get all functions
    all_functions = get_all_functions(doc)
    print(f"Total functions: {len(all_functions)}")

    # Get functions with arguments
    functions_with_args = get_functions_with_args(doc)
    print(f"Functions with arguments: {len(functions_with_args)}")

    # Show function details
    for func in functions_with_args:
        print(f"  - {func.name}: {len(func.get_arguments)} arguments")
        for arg in func.get_arguments:
            print(f"    * {arg.name} ({arg.type}): {arg.description}")

    # # Convert to dictionary
    # doc_dict = doc.model_dump()
    # print(f"\nConverted to dict with {len(doc_dict['types'])} types")

    # # Convert to JSON
    # json_output = doc.model_dump_json(indent=2)
    # print(f"JSON output length: {len(json_output)} characters")


def format_description_as_docstring(desc: str, indent=4) -> str:
    desc_lines = [ln for ln in desc.strip().splitlines()]
    if len(desc_lines) == 0:
        return ""
    if len(desc_lines) == 1 and ("\\" not in desc):
        return " " * indent + repr(desc_lines[0])
    ret = [" " * indent + ('r"""' if "\\" in desc else '"""')]  # ruff rule D301
    for ln in desc_lines:
        ret.append(" " * indent + ln)  # TODO: repr not needed?
    ret.append(" " * indent + '"""')
    return "\n".join(ret)


def format_as_python_type_extvalue(el_type: str) -> str:
    maybe_py_type = MAP_TO_SIMPLE_PY_TYPE.get(el_type)
    if maybe_py_type in ("int", "float", "str", "None"):
        return f"ExtValue[{maybe_py_type}]", ""
    return "ExtValue", el_type
    # return f'ExtValue["{maybe_py_type}"]', el_type


def main_write_framscript_part_of_the_stub(doc: FramscriptDoc):
    print("from warnings import deprecated")
    print("from typing import Any, overload")
    print("from typing import Any as Object\n\n")
    print("class ExtValue: ...\n\n")

    for each_type in doc.types:
        if each_type.context not in (GLOBAL_CONTEXT, "Global context"):
            # skip, likely not available in frams.py anyway
            continue
        # rprint(f"{each_type.name!r} {each_type.context!r}")
        print(f"class {each_type.name}(ExtValue):")
        if each_type.description is None:
            print('    "(missing docstring?)"')
        # print("    " + repr(each_type.description))  # TODO: type docstring
        print(format_description_as_docstring(each_type.description))
        print()

        detecting_duplicate_elements = collections.Counter(
            el.id for el in each_type.elements
        )
        duplicate_elements = {
            k for k, v in detecting_duplicate_elements.items() if v > 1
        }
        # print(f"# duplicate_elements: {duplicate_elements} {len(duplicate_elements)}")
        # -> import, substr, intersect

        for el in each_type.elements:
            descr = el.description or ""
            id_py = el.id
            if el.id in INVALID_PY_IDENTS:
                id_py = el.id + "_"
            if el.name is not None:
                if el.name.lower() != el.id.lower() and (
                    el.name.lower() != el.id.lower() + " object"
                ):
                    # descr = el.name + " (el.name)\n\n" + descr
                    descr = el.name + "\n\n" + descr
                # Example:
                # world: ExtValue
                # """
                # World object (el.name)
                # """

            if el.is_function:
                func_args = el.get_arguments
                args = []
                arg_name_repeats = set()
                for arg in func_args:
                    assert not bool(arg.description), f"Each {arg} has empty descr (?)"
                    # if arg.description:
                    # descr += f"\n:arg: {arg.name}"  # {arg.description!r}"

                    arg_name = arg.name or "_"
                    if arg_name[0].isdigit():  # invalid Python ident. (?)
                        arg_name = "a_" + arg_name
                    if arg_name in arg_name_repeats:
                        arg_name += "_2"  # TODO
                    arg_type_py = MAP_TO_SIMPLE_PY_TYPE.get(arg.type)
                    args.append(
                        f"{arg_name.replace(' ', '_')}: "
                        + (arg_type_py if arg_type_py is not None else f"{arg.type!r}")
                    )
                    arg_name_repeats.add(arg_name)
                args = ", ".join(args)
                # args = "..."

                ret_type = ""
                if el.type is not None:
                    ret_type, ret_type_comment = format_as_python_type_extvalue(
                        el.type
                    )  # TODO?
                    ret_type = f" -> {ret_type}"
                    if ret_type_comment:
                        ret_type_comment = f"  # returns {ret_type_comment}"

                if el.is_deprecated:
                    print("    @deprecated")
                if el.id in duplicate_elements:
                    print("    @overload")
                print("    @staticmethod")  # does not take "self" or "cls" parameters
                print(f"    def {id_py}({args}){ret_type}:{ret_type_comment}")
                print(format_description_as_docstring(descr, indent=8))
                print("        ...")  # if no description
                print()
            else:
                el_type_py, el_type_comment = format_as_python_type_extvalue(el.type)
                if el_type_comment:
                    el_type_comment = f"  # {el_type_comment}"
                else:
                    el_type_comment = ""
                print(f"    {id_py}: {el_type_py}{el_type_comment}")
                if descr:
                    print(format_description_as_docstring(descr, indent=4))

        print("")


if __name__ == "__main__":
    try:
        # Parse from actual file (uncomment when you have the file)
        # main_example("framscript.xml")

        filename = "./framscript.xml"
        if len(sys.argv) > 1:
            filename = sys.argv[1]
        doc = parse_framscript_xml(filename)

        # Path("framscript-as-json.json").write_text(doc.model_dump_json(indent=1))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main_write_framscript_part_of_the_stub(doc)
        buf_fmt = format_code_with_ruff(buf.getvalue())
        print(buf_fmt)

    except pydantic_core.ValidationError as e:
        traceback.print_exc()
        print("----\n\n\n")
        # detailed:
        for err in e.errors():
            # {'type': 'missing', 'loc': ('types', 4, 'elements', 9, 'name'), 'msg': '[line -1]: Field required',
            # 'input': {'function': 'true', 'flags': '2', 'description': "This is the empty item in the Theater's menu"},
            # 'ctx': {'sourceline': -1, 'orig': 'Field required'}}
            print(err)
    except Exception as e:
        print(type(e))  # <class 'pydantic_core._pydantic_core.ValidationError'>
        print(f"Error: {e}")
        traceback.print_exc()
