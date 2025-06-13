from IPython.core.interactiveshell import InteractiveShell
from logai_mcp.session import app, logger
from typing import Optional, Dict, List, Any, Tuple
import io
import contextlib
import ast


_SHELL: InteractiveShell = InteractiveShell.instance()
_SHELL.reset()

async def run_code_in_shell(code: str):
    execution_result = await _SHELL.run_cell_async(code)
    
    # Check for execution errors and raise them instead of silently ignoring
    if execution_result.error_before_exec:
        raise execution_result.error_before_exec
    
    if execution_result.error_in_exec:
        raise execution_result.error_in_exec
    
    return execution_result.result

@app.tool()
async def execute_python_code(code: str):
    """
    Executes a given string of Python code in the underlying IPython interactive shell.

    This tool allows for direct execution of arbitrary Python code, including
    defining variables, calling functions, or running any valid Python statements.
    The code is run in the same IPython shell instance used by other tools,
    allowing for state sharing (variables defined in one call can be used in subsequent calls).

    Parameters
    ----------
    code : str
        A string containing the Python code to be executed.
        For example, "x = 10+5" or "print(\\'Hello, world!\\')" or
        "my_variable = some_function_defined_elsewhere()".

    Returns
    -------
    Any
        The result of the last expression in the executed code. If the code
        does not produce a result (e.g., an assignment statement), it might
        return None or as per IPython's `run_cell_async` behavior for such cases.
        Specifically, it returns `execution_result.result` from IPython's
        `ExecutionResult` object.

    Examples
    --------
    # Define a variable
    >>> execute_python_code(code="my_var = 42")
    # Use the defined variable
    >>> execute_python_code(code="print(my_var * 2)")
    # Output: 84

    # Execute a multi-line script
    >>> script = \'\'\'
    ... import math
    ... def calculate_circle_area(radius):
    ...     return math.pi * radius ** 2
    ... area = calculate_circle_area(5)
    ... area
    ... \'\'\'
    >>> execute_python_code(code=script)
    # Output: 78.53981633974483

    See Also
    --------
    IPython.core.interactiveshell.InteractiveShell.run_cell_async
    run_code_in_shell (internal utility called by this tool)
    """
    # Capture stdout and stderr so that users can see print output and error messages
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        result = await run_code_in_shell(code)

    stdout_value = stdout_buffer.getvalue()
    stderr_value = stderr_buffer.getvalue()

    execution_details_dict = {}

    if result is not None:
        execution_details_dict["result"] = result.result

        if result.error_before_exec:
            execution_details_dict["error_before_exec"] = str(result.error_before_exec)

        if result.error_in_exec:
            error_type = type(result.error_in_exec).__name__
            error_msg = str(result.error_in_exec)
            execution_details_dict["error_in_exec"] = f"{error_type}: {error_msg}"


    if stdout_value:
        execution_details_dict["stdout"] = stdout_value.rstrip()

    if stderr_value:
        execution_details_dict["stderr"] = stderr_value.rstrip()

    return execution_details_dict

@app.tool()
async def list_shell_variables() -> list[str]:
    """Lists variable names in the current IPython user namespace.

    Tries to exclude common IPython internal variables (e.g., 'In', 'Out', 'exit', 'quit', 'get_ipython')
    and variables starting with an underscore unless they are common history accessors.
    Special underscore variables like '_', '__', '___' (output history) and
    '_i', '_ii', '_iii' (input history) are included if present.

    Returns
    -------
    list[str]
        A sorted list of identified user variable names. To get the value of a variable, use the `inspect_shell_object` tool.
    """
    user_vars = []
    system_variables = {'In', 'Out', 'exit', 'quit', 'get_ipython', '_ih', '_oh', '_dh', '_sh', '_ip'}

    if _SHELL.user_ns is None:
        return []

    for name in _SHELL.user_ns.keys():
        if name in system_variables:
            continue
        if name.startswith('_') and name not in {'_', '__', '___', '_i', '_ii', '_iii'} and not name.startswith('_i'):
            continue
        user_vars.append(name)
    return sorted(list(set(user_vars)))

@app.tool()
async def inspect_shell_object(object_name: str, detail_level: int = 0) -> str:
    """Provides detailed information about an object in the IPython shell by its name.
    Uses IPython's object inspector.

    Parameters
    ----------
    object_name : str
        The name of the variable/object in the shell to inspect.
    detail_level : int, optional
        Detail level for inspection (0, 1, or 2).
        0: basic info (type, string representation).
        1: adds docstring.
        2: adds source code if available.
        Defaults to 0.

    Returns
    -------
    str
        A string containing the inspection details.
        Returns an error message if the object is not found or if an error occurs during inspection.
    """
    if _SHELL.user_ns is None or object_name not in _SHELL.user_ns:
        return f"Error: Object '{object_name}' not found in the shell namespace."
    try:
        actual_detail_level = min(max(detail_level, 0), 2)
        return _SHELL.object_inspect_text(object_name, detail_level=actual_detail_level)
    except Exception as e:
        return f"Error during inspection of '{object_name}': {str(e)}"

@app.tool()
async def get_shell_history(range_str: str = "", raw: bool = False) -> str:
    """Retrieves lines from the IPython shell's input history.

    Uses IPython's `extract_input_lines` method. The `range_str` defines which lines to retrieve.
    Examples for `range_str`:
    - "1-5": Lines 1 through 5 of the current session.
    - "~2/1-5": Lines 1 through 5 of the second-to-last session.
    - "6": Line 6 of the current session.
    - "": (Default) All lines of the current session except the last executed one.
    - "~10:": All lines starting from the 10th line of the last session.
    - ":5": Lines up to 5 of current session.

    Parameters
    ----------
    range_str : str, optional
        A string specifying the history slices to retrieve, by default "" (all current session history, except last).
        The syntax is based on IPython's history access (%history magic).
    raw : bool, optional
        If True, retrieves the raw, untransformed input history. Defaults to False.

    Returns
    -------
    str
        A string containing the requested input history lines, separated by newlines.
        Returns an error message if history retrieval fails.
    """
    try:
        history_lines = _SHELL.extract_input_lines(range_str=range_str, raw=raw)
        return history_lines
    except Exception as e:
        return f"Error retrieving shell history for range '{range_str}' (raw={raw}): {str(e)}"

@app.tool()
async def run_shell_magic(magic_name: str, line: str, cell: Optional[str] = None):
    """Executes an IPython magic command in the shell.

    Allows execution of both line magics (e.g., %ls -l) and cell magics (e.g., %%timeit code...).

    Parameters
    ----------
    magic_name : str
        The name of the magic command (e.g., "ls", "timeit", "writefile") WITHOUT the leading '%' or '%%'.
    line : str
        The argument string for the magic command. For line magics, this is the entire line after the magic name.
        For cell magics, this is the line immediately following the `%%magic_name` directive.
        Can be an empty string if the magic command takes no arguments on its first line.
    cell : str, optional
        The body of a cell magic (the code block below `%%magic_name line`).
        If None or an empty string, the command is treated as a line magic.
        If provided, it's treated as a cell magic.

    Returns
    -------
    Any
        The result of the magic command execution, if any. Behavior varies depending on the magic command.
        May return None, text output, or other objects. In case of errors, an error message string is returned.

    Examples
    --------
    # Line magic example: list files
    >>> run_shell_magic(magic_name="ls", line="-la")

    # Cell magic example: time a piece of code
    >>> run_shell_magic(magic_name="timeit", line="-n 10", cell="sum(range(100))")

    # Magic that doesn't produce a return value directly to python but has side effects (e.g. writing a file)
    >>> run_shell_magic(magic_name="writefile", line="my_test_file.txt", cell="This is a test.")
    """
    try:
        if cell is not None and cell.strip() != "":
            return _SHELL.run_cell_magic(magic_name, line, cell)
        else:
            return _SHELL.run_line_magic(magic_name, line)
    except Exception as e:
        error_type = type(e).__name__
        return f"Error executing magic command '{magic_name}' (line='{line}', cell present: {cell is not None}): {error_type}: {str(e)}"

@app.tool()
async def install_package(package_spec: str, upgrade: bool = False):
    """Installs a Python package using uv within the IPython shell session.

    This tool allows the LLM to install packages dynamically using IPython's magic commands.
    The package will be installed in the same environment where the IPython shell is running
    and will be immediately available for import in subsequent code executions.

    Parameters
    ----------
    package_spec : str
        The package specification to install. Can be:
        - A simple package name: "requests"
        - A package with version: "requests==2.31.0"
        - A package with version constraints: "requests>=2.30.0"
        - A git repository: "git+https://github.com/user/repo.git"
        - A local path: "/path/to/package"
        - Multiple packages: "requests numpy pandas"
    upgrade : bool, optional
        Whether to upgrade the package if it's already installed. Defaults to False.

    Returns
    -------
    dict
        A dictionary containing:
        - "success": bool indicating if installation succeeded
        - "output": str with installation output or error message
        - "packages_requested": list of package names that were requested for installation

    Examples
    --------
    # Install a single package
    >>> install_package("requests")
    
    # Install with version constraint
    >>> install_package("numpy>=1.20.0")
    
    # Install and upgrade if already present
    >>> install_package("matplotlib", upgrade=True)
    
    # Install from git repository
    >>> install_package("git+https://github.com/user/repo.git@main")
    """
    try:
        # Build the pip install command arguments
        pip_args = []
        
        if upgrade:
            pip_args.append("--upgrade")
            
        # Add the package specification
        pip_args.append(package_spec)
        
        # Join arguments for the magic command
        pip_command_line = " ".join(pip_args)
        
        # Use IPython's %pip magic command to install packages
        # This ensures the package is installed in the same environment as the IPython shell
        magic_result = _SHELL.run_line_magic("pip", f"install {pip_command_line}")
        
        # Extract requested package names for tracking
        packages_requested = []
        for pkg in package_spec.split():
            # Extract base package name (strip version constraints)
            base_name = pkg.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('@')[0]
            if not base_name.startswith('git+'):
                packages_requested.append(base_name)
            else:
                # For git repos, try to extract package name from URL
                if '.git' in base_name:
                    repo_name = base_name.split('/')[-1].replace('.git', '')
                    packages_requested.append(repo_name)
        
        return {
            "success": True,
            "output": str(magic_result) if magic_result else "Package installation completed successfully",
            "packages_requested": packages_requested
        }
        
    except Exception as e:
        error_msg = str(e)
        
        # Check if it's a common error type we can provide better feedback for
        if "No module named" in error_msg:
            error_msg += "\nNote: Package may need to be installed with a different name or from a different source."
        elif "Permission denied" in error_msg:
            error_msg += "\nNote: Installation may require different permissions in this environment."
        
        return {
            "success": False,
            "output": f"Installation failed: {error_msg}",
            "packages_requested": package_spec.split()
        }


# =============================================================================
# CODE COMPLETION & CONTEXT TOOLS
# =============================================================================

@app.tool()
async def get_completions(text: str, cursor_pos: Optional[int] = None) -> Dict[str, Any]:
    """Get code completions at cursor position to help LLM understand available methods/attributes.
    
    This tool provides intelligent code completion suggestions that can help the LLM
    understand what methods, attributes, or variables are available in the current context.
    
    Parameters
    ----------
    text : str
        The code text for which to get completions
    cursor_pos : int, optional
        Position of cursor in the text. If None, defaults to end of text.
        
    Returns
    -------
    dict
        Dictionary containing:
        - "text": the actual text that was completed
        - "matches": list of possible completions
        - "cursor_start": position where completion starts
        - "cursor_end": position where completion ends
        
    Examples
    --------
    >>> get_completions("import o")
    {'text': 'o', 'matches': ['os', 'operator', 'optparse', ...], ...}
    
    >>> get_completions("np.arr")  # after importing numpy as np
    {'text': 'arr', 'matches': ['array', 'array_equal', 'array_split', ...], ...}
    """
    try:
        if cursor_pos is None:
            cursor_pos = len(text)
            
        # Use IPython's completion system
        completed_text, matches = _SHELL.complete(text, cursor_pos)
        
        # Find where the completion starts
        cursor_start = cursor_pos - len(completed_text)
        cursor_end = cursor_pos
        
        return {
            "text": completed_text,
            "matches": matches,
            "cursor_start": cursor_start,
            "cursor_end": cursor_end,
            "total_matches": len(matches)
        }
    except Exception as e:
        logger.error(f"Error getting completions: {e}")
        return {
            "text": "",
            "matches": [],
            "cursor_start": cursor_pos or 0,
            "cursor_end": cursor_pos or 0,
            "total_matches": 0,
            "error": str(e)
        }


@app.tool()
async def get_function_signature(func_name: str) -> Dict[str, Any]:
    """Get function signature and docstring to help LLM generate correct function calls.
    
    This tool provides detailed information about function signatures, parameters,
    and documentation, which helps the LLM understand how to correctly call functions.
    
    Parameters
    ----------
    func_name : str
        Name of the function/method/class to inspect
        
    Returns
    -------
    dict
        Dictionary containing function information:
        - "signature": function signature string
        - "docstring": function documentation
        - "type": type of the object (function, method, class, etc.)
        - "module": module where object is defined
        - "file": file where object is defined (if available)
        
    Examples
    --------
    >>> get_function_signature("print")
    {'signature': 'print(*args, sep=...', 'docstring': 'print(value, ..., sep=...', ...}
    
    >>> get_function_signature("pandas.DataFrame")
    {'signature': 'DataFrame(data=None, index=None, ...', 'docstring': 'Two-dimensional...', ...}
    """
    try:
        # Use IPython's object inspection with detail level 1 for docstring
        info = _SHELL.object_inspect(func_name, detail_level=1)
        
        if not info:
            return {"error": f"Object '{func_name}' not found"}
            
        return {
            "signature": info.get('definition', ''),
            "docstring": info.get('docstring', ''),
            "type": info.get('type_name', ''),
            "module": info.get('namespace', ''),
            "file": info.get('file', ''),
            "class_docstring": info.get('class_docstring', ''),
            "init_docstring": info.get('init_docstring', ''),
            "call_def": info.get('call_def', ''),
            "call_docstring": info.get('call_docstring', '')
        }
    except Exception as e:
        logger.error(f"Error getting function signature for {func_name}: {e}")
        return {"error": str(e)}


@app.tool()
async def get_namespace_info() -> Dict[str, Any]:
    """Get information about current namespaces to help LLM understand scope.
    
    This tool provides insight into what variables, functions, and objects are
    currently available in different namespaces, helping the LLM understand
    the current execution context.
    
    Returns
    -------
    dict
        Dictionary with namespace information:
        - "user_variables": list of user-defined variable names
        - "builtin_names": list of available builtin names  
        - "imported_modules": list of imported module names
        - "total_user_objects": count of objects in user namespace
        
    Examples
    --------
    >>> get_namespace_info()
    {'user_variables': ['x', 'df', 'my_func'], 'builtin_names': ['print', 'len', ...], ...}
    """
    try:
        # Get user namespace variables (excluding IPython internals)
        user_vars = []
        system_variables = {'In', 'Out', 'exit', 'quit', 'get_ipython', '_ih', '_oh', '_dh', '_sh', '_ip'}
        
        if _SHELL.user_ns:
            for name in _SHELL.user_ns.keys():
                if name in system_variables:
                    continue
                if name.startswith('_') and name not in {'_', '__', '___', '_i', '_ii', '_iii'} and not name.startswith('_i'):
                    continue
                user_vars.append(name)
        
        # Get builtin names - use dir() on builtins module as fallback
        builtin_names = []
        try:
            import builtins
            builtin_names = [name for name in dir(builtins) if not name.startswith('_')][:50]
        except:
            builtin_names = ['print', 'len', 'str', 'int', 'float', 'list', 'dict', 'tuple', 'set']
        
        # Find imported modules
        imported_modules = []
        if _SHELL.user_ns:
            for name, obj in _SHELL.user_ns.items():
                if hasattr(obj, '__file__') and hasattr(obj, '__name__'):
                    if not name.startswith('_'):
                        imported_modules.append(name)
        
        return {
            "user_variables": sorted(user_vars),
            "builtin_names": sorted(builtin_names),
            "imported_modules": sorted(imported_modules),
            "total_user_objects": len(user_vars)
        }
    except Exception as e:
        logger.error(f"Error getting namespace info: {e}")
        return {"error": str(e)}


# =============================================================================
# ENHANCED OBJECT INTROSPECTION TOOLS
# =============================================================================

@app.tool()
async def get_object_source(object_name: str) -> Dict[str, Any]:
    """Get source code of functions/classes to help LLM understand implementation patterns.
    
    This tool retrieves the actual source code of functions, methods, and classes,
    which helps the LLM understand implementation patterns and coding styles.
    
    Parameters
    ----------
    object_name : str
        Name of the object to get source code for
        
    Returns
    -------
    dict
        Dictionary containing:
        - "source": source code string
        - "file": file where object is defined
        - "line_number": line number where object starts
        - "type": type of the object
        
    Examples
    --------
    >>> get_object_source("my_function")
    {'source': 'def my_function(x):\n    return x * 2', 'file': '<ipython-input-1>', ...}
    """
    try:
        # Use IPython's object inspection with detail level 2 for source code
        info = _SHELL.object_inspect(object_name, detail_level=2)
        
        if not info:
            return {"error": f"Object '{object_name}' not found"}
            
        return {
            "source": info.get('source', ''),
            "file": info.get('file', ''),
            "line_number": info.get('line_number', ''),
            "type": info.get('type_name', ''),
            "definition": info.get('definition', ''),
            "docstring": info.get('docstring', '')
        }
    except Exception as e:
        logger.error(f"Error getting source for {object_name}: {e}")
        return {"error": str(e)}


@app.tool()
async def list_object_attributes(object_name: str, pattern: str = "*", include_private: bool = False) -> Dict[str, Any]:
    """List all attributes matching pattern to help LLM discover available methods.
    
    This tool lists attributes, methods, and properties of an object, helping
    the LLM discover what functionality is available.
    
    Parameters
    ----------
    object_name : str
        Name of the object to inspect
    pattern : str, optional
        Pattern to match attributes against (supports wildcards)
    include_private : bool, optional
        Whether to include private attributes (starting with _)
        
    Returns
    -------
    dict
        Dictionary containing:
        - "attributes": list of matching attribute names
        - "methods": list of callable attributes
        - "properties": list of property attributes
        - "total_count": total number of attributes found
        
    Examples
    --------
    >>> list_object_attributes("str", pattern="*find*")
    {'attributes': ['find', 'rfind'], 'methods': ['find', 'rfind'], ...}
    """
    try:
        if object_name not in _SHELL.user_ns:
            return {"error": f"Object '{object_name}' not found in namespace"}
            
        obj = _SHELL.user_ns[object_name]
        
        # Get all attributes
        all_attrs = dir(obj)
        
        # Filter based on pattern and private setting
        import fnmatch
        filtered_attrs = []
        for attr in all_attrs:
            if not include_private and attr.startswith('_'):
                continue
            if fnmatch.fnmatch(attr.lower(), pattern.lower()):
                filtered_attrs.append(attr)
        
        # Categorize attributes
        methods = []
        properties = []
        other_attrs = []
        
        for attr in filtered_attrs:
            try:
                attr_obj = getattr(obj, attr)
                if callable(attr_obj):
                    methods.append(attr)
                elif isinstance(attr_obj, property):
                    properties.append(attr)
                else:
                    other_attrs.append(attr)
            except:
                other_attrs.append(attr)
        
        return {
            "attributes": sorted(filtered_attrs),
            "methods": sorted(methods),
            "properties": sorted(properties),
            "other_attributes": sorted(other_attrs),
            "total_count": len(filtered_attrs),
            "pattern_used": pattern,
            "include_private": include_private
        }
    except Exception as e:
        logger.error(f"Error listing attributes for {object_name}: {e}")
        return {"error": str(e)}


@app.tool()
async def get_docstring(object_name: str) -> Dict[str, Any]:
    """Get just the docstring - lighter than full inspection for understanding APIs.
    
    This tool provides a lightweight way to get documentation for objects
    without the overhead of full inspection.
    
    Parameters
    ----------
    object_name : str
        Name of the object to get docstring for
        
    Returns
    -------
    dict
        Dictionary containing:
        - "docstring": the object's docstring
        - "summary": first line of docstring (brief description)
        
    Examples
    --------
    >>> get_docstring("print")
    {'docstring': 'print(value, ..., sep=...', 'summary': 'print(value, ..., sep=...)'}
    """
    try:
        info = _SHELL.object_inspect(object_name, detail_level=1)
        
        if not info:
            return {"error": f"Object '{object_name}' not found"}
            
        docstring = info.get('docstring', '') or ''
        summary = docstring.split('\n')[0] if docstring else ''
        
        return {
            "docstring": docstring,
            "summary": summary,
            "has_docstring": bool(docstring.strip())
        }
    except Exception as e:
        logger.error(f"Error getting docstring for {object_name}: {e}")
        return {"error": str(e)}


# =============================================================================
# ERROR ANALYSIS & DEBUGGING TOOLS
# =============================================================================

@app.tool()
async def get_last_exception_info() -> Dict[str, Any]:
    """Get detailed info about last exception to help LLM debug and fix code.
    
    This tool provides comprehensive information about the most recent exception,
    including the exception type, message, and traceback information.
    
    Returns
    -------
    dict
        Dictionary containing:
        - "exception_type": type of the exception
        - "exception_message": exception message
        - "traceback": formatted traceback
        - "has_exception": whether there was a recent exception
        
    Examples
    --------
    >>> get_last_exception_info()
    {'exception_type': 'NameError', 'exception_message': "name 'x' is not defined", ...}
    """
    try:
        # Get the last exception info
        exception_only = _SHELL.get_exception_only()
        
        if not exception_only or exception_only.strip() == '':
            return {
                "has_exception": False,
                "message": "No recent exception found"
            }
        
        # Parse exception info
        lines = exception_only.strip().split('\n')
        if lines:
            last_line = lines[-1]
            if ':' in last_line:
                exception_type, exception_message = last_line.split(':', 1)
                exception_type = exception_type.strip()
                exception_message = exception_message.strip()
            else:
                exception_type = last_line.strip()
                exception_message = ""
        else:
            exception_type = "Unknown"
            exception_message = ""
        
        return {
            "has_exception": True,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "full_exception": exception_only,
            "traceback_lines": lines
        }
    except Exception as e:
        logger.error(f"Error getting exception info: {e}")
        return {"error": str(e), "has_exception": False}


@app.tool()
async def analyze_syntax_error(code: str) -> Dict[str, Any]:
    """Check if code has syntax errors before execution to help LLM validate code.
    
    This tool performs static analysis of Python code to detect syntax errors
    before execution, helping prevent runtime failures.
    
    Parameters
    ----------
    code : str
        Python code to analyze for syntax errors
        
    Returns
    -------
    dict
        Dictionary containing:
        - "valid": whether code has valid syntax
        - "error": error message if invalid
        - "line": line number where error occurs
        - "offset": character offset of error
        - "suggestions": possible fixes (if available)
        
    Examples
    --------
    >>> analyze_syntax_error("print('hello')")
    {'valid': True}
    
    >>> analyze_syntax_error("print('hello'")  # missing closing quote
    {'valid': False, 'error': 'EOL while scanning string literal', 'line': 1, ...}
    """
    try:
        # Try to compile the code
        compile(code, '<string>', 'exec')
        return {
            "valid": True,
            "message": "Code has valid syntax"
        }
    except SyntaxError as e:
        # Extract detailed syntax error information
        error_info = {
            "valid": False,
            "error": str(e),
            "error_type": "SyntaxError",
            "line": e.lineno,
            "offset": e.offset,
            "text": e.text.strip() if e.text else "",
            "filename": e.filename or "<string>"
        }
        
        # Add some common suggestions based on error type
        suggestions = []
        error_msg = str(e).lower()
        
        if "unexpected eof" in error_msg or "eol while scanning" in error_msg:
            suggestions.append("Check for unclosed quotes, parentheses, or brackets")
        elif "invalid syntax" in error_msg:
            suggestions.append("Check for typos in keywords or operators")
        elif "indentation" in error_msg:
            suggestions.append("Check indentation consistency (spaces vs tabs)")
        elif "unmatched" in error_msg:
            suggestions.append("Check for unmatched parentheses or brackets")
            
        error_info["suggestions"] = suggestions
        return error_info
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "suggestions": ["Unexpected error during syntax analysis"]
        }


# =============================================================================
# CODE QUALITY & FORMATTING TOOLS  
# =============================================================================

@app.tool()
async def check_code_completeness(code: str) -> Dict[str, Any]:
    """Check if code block is complete to help LLM know when to continue vs execute.
    
    This tool determines whether a code block is syntactically complete and ready
    for execution, or if it needs additional lines to be valid.
    
    Parameters
    ----------
    code : str
        Python code to check for completeness
        
    Returns
    -------
    dict
        Dictionary containing:
        - "status": 'complete', 'incomplete', or 'invalid'
        - "indent": suggested indentation for next line
        - "needs_more": whether more input is needed
        - "reason": explanation of the status
        
    Examples
    --------
    >>> check_code_completeness("print('hello')")
    {'status': 'complete', 'indent': '', 'needs_more': False}
    
    >>> check_code_completeness("if True:")
    {'status': 'incomplete', 'indent': '    ', 'needs_more': True}
    """
    try:
        status, indent = _SHELL.check_complete(code)
        
        needs_more = status == 'incomplete'
        
        # Provide explanations for different statuses
        reasons = {
            'complete': 'Code block is syntactically complete and ready for execution',
            'incomplete': 'Code block needs additional lines to be complete',
            'invalid': 'Code contains syntax errors and cannot be completed'
        }
        
        return {
            "status": status,
            "indent": indent,
            "needs_more": needs_more,
            "reason": reasons.get(status, "Unknown status"),
            "suggested_indent_length": len(indent) if indent else 0
        }
    except Exception as e:
        logger.error(f"Error checking code completeness: {e}")
        return {
            "status": "error",
            "indent": "",
            "needs_more": False,
            "reason": f"Error analyzing code: {str(e)}",
            "error": str(e)
        }


# =============================================================================
# ENHANCED MAGIC DISCOVERY TOOLS
# =============================================================================

@app.tool()
async def list_available_magics() -> Dict[str, Any]:
    """List all available magic commands to help LLM discover IPython capabilities.
    
    This tool provides a comprehensive list of available IPython magic commands,
    both line magics (%) and cell magics (%%).
    
    Returns
    -------
    dict
        Dictionary containing:
        - "line_magics": list of available line magic names
        - "cell_magics": list of available cell magic names
        - "total_line_magics": count of line magics
        - "total_cell_magics": count of cell magics
        
    Examples
    --------
    >>> list_available_magics()
    {'line_magics': ['cd', 'ls', 'pwd', 'time', ...], 'cell_magics': ['timeit', 'writefile', ...]}
    """
    try:
        line_magics = sorted(_SHELL.magics_manager.magics['line'].keys())
        cell_magics = sorted(_SHELL.magics_manager.magics['cell'].keys())
        
        return {
            "line_magics": line_magics,
            "cell_magics": cell_magics,
            "total_line_magics": len(line_magics),
            "total_cell_magics": len(cell_magics),
            "total_magics": len(line_magics) + len(cell_magics)
        }
    except Exception as e:
        logger.error(f"Error listing available magics: {e}")
        return {"error": str(e)}


@app.tool()
async def get_magic_help(magic_name: str, magic_type: str = "line") -> Dict[str, Any]:
    """Get help for specific magic command to help LLM use magics correctly.
    
    This tool provides detailed documentation for specific magic commands,
    including usage examples and parameter descriptions.
    
    Parameters
    ----------
    magic_name : str
        Name of the magic command (without % prefix)
    magic_type : str, optional
        Type of magic: "line" or "cell" (default: "line")
        
    Returns
    -------
    dict
        Dictionary containing:
        - "help_text": detailed help documentation
        - "exists": whether the magic command exists
        - "magic_type": type of magic (line or cell)
        - "summary": brief description
        
    Examples
    --------
    >>> get_magic_help("timeit")
    {'help_text': 'Time execution of a Python statement...', 'exists': True, ...}
    """
    try:
        # Find the magic function
        if magic_type == "line":
            magic_func = _SHELL.find_line_magic(magic_name)
        elif magic_type == "cell":
            magic_func = _SHELL.find_cell_magic(magic_name)
        else:
            magic_func = _SHELL.find_magic(magic_name)
        
        if not magic_func:
            return {
                "exists": False,
                "error": f"Magic '{magic_name}' not found",
                "magic_type": magic_type
            }
        
        # Get the docstring
        help_text = magic_func.__doc__ if magic_func.__doc__ else "No documentation available"
        summary = help_text.split('\n')[0] if help_text else ""
        
        return {
            "exists": True,
            "help_text": help_text,
            "summary": summary,
            "magic_type": magic_type,
            "magic_name": magic_name
        }
    except Exception as e:
        logger.error(f"Error getting magic help for {magic_name}: {e}")
        return {
            "exists": False,
            "error": str(e),
            "magic_type": magic_type,
            "magic_name": magic_name
        }
